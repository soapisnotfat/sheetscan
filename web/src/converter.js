// Local-only conversion API. Importing this module never installs a service
// worker, navigates, reloads, or edits the host application's project.
import { loadPages } from './input.js'
import { createOCR } from './ocr.js'
import { createResourceClient } from './resources.js'
import { annotate, tokens } from './annotate.js'
import { prepareMetadata } from './metadata.js'

export const RECOGNIZER_VERSION = 'v19-source-curves'
export const SDK_VERSION = 'v19-source-curves'

export function capabilities() {
  const jspi = typeof WebAssembly.Suspending === 'function'
  const sharedMemory = globalThis.crossOriginIsolated && typeof SharedArrayBuffer === 'function'
  return { jspi, sharedMemory: !!sharedMemory, supported: jspi || !!sharedMemory }
}

/** Raster-only preview: no recognition worker, runtime, network or OCR models. */
export async function renderPreview(files, { signal, onProgress = () => {}, onPage = () => {}, maxWidth = 1400 } = {}) {
  const pages = await loadPages(files, count => onProgress({ phase: 'preview', page: count }), {
    signal, maxWidth,
    onPage: ({ png, width, height, fileIndex, page, pageCount }) => onPage({ png, width, height, fileIndex, page, pageCount }),
  })
  try {
    return { pages: pages.map(({ png, width, height, fileIndex, page, pageCount }) => ({ png, width, height, fileIndex, page, pageCount })) }
  } finally { pages.forEach(page => URL.revokeObjectURL(page.url)) }
}

/** One conversion at a time; cancel leaves the caller's source/project intact. */
export function createScoreConverter(defaults = {}) {
  let active = null
  return {
    async convert(files, options = {}) {
      if (active) throw new Error('A score conversion is already running')
      const controller = new AbortController()
      active = controller
      const external = options.signal ?? defaults.signal
      const relay = () => controller.abort(external.reason)
      if (external?.aborted) relay()
      external?.addEventListener('abort', relay, { once: true })
      try {
        return await convertScore(files, { ...defaults, ...options, signal: controller.signal })
      } finally {
        external?.removeEventListener('abort', relay)
        active = null
      }
    },
    cancel() { active?.abort(new DOMException('Score conversion cancelled', 'AbortError')) },
    close() { active?.abort(new DOMException('Score conversion cancelled', 'AbortError')) },
  }
}

export async function convertScore(files, { signal, onProgress = () => {}, printedTuplets = true, forceSharedMemory = false, modelBase } = {}) {
  const moduleDirectory = new URL('.', import.meta.url)
  const packageBase = /\/(?:src|assets)\/$/.test(moduleDirectory.pathname) ? new URL('..', moduleDirectory).href : moduleDirectory.href
  const textOCR = createOCR(createResourceClient(packageBase, { signal, onProgress }))
  const supported = capabilities()
  const abortError = () => signal?.reason?.name === 'AbortError' ? signal.reason : new DOMException('Score conversion cancelled', 'AbortError')
  const checkAbort = () => { if (signal?.aborted) throw abortError() }
  checkAbort()
  if (!supported.supported || forceSharedMemory && !supported.sharedMemory) {
    const error = new Error('Score conversion requires WebAssembly JSPI or a cross-origin isolated page with shared memory')
    error.code = 'UNSUPPORTED_BROWSER'
    throw error
  }
  files = Array.from(files)
  if (!files.length) throw new Error('Choose at least one score PDF or image')
  const started = performance.now(), urls = []
  let worker, networkWorker, pending, rejectAbort, rendering
  const aborted = new Promise((_, reject) => { rejectAbort = reject })
  // The abort may occur during page rendering, before an inference request.
  aborted.catch(() => {})
  const cancel = () => {
    const error = abortError()
    worker?.terminate()
    networkWorker?.terminate()
    textOCR.close()
    pending?.reject(error)
    rejectAbort(error)
  }
  signal?.addEventListener('abort', cancel, { once: true })
  const wait = promise => Promise.race([promise, aborted])
  try {
    onProgress({ phase: 'rendering', text: 'Preparing score pages…' })
    checkAbort()
    rendering = loadPages(files, n => onProgress({ phase: 'rendering', page: n }), { signal })
    rendering.then(pages => {
      if (signal?.aborted) pages.forEach(p => URL.revokeObjectURL(p.url))
    }).catch(() => {})
    const pages = await wait(rendering)
    urls.push(...pages.map(p => p.url))
    checkAbort()
    const words = Promise.all(pages.map(p => p.text.length ? p.text : textOCR.ocr(p)))
    words.catch(() => {})
    worker = new Worker(new URL('./omr.worker.js', import.meta.url), { type: 'module' })
    const send = (message, transfer = []) => new Promise((resolve, reject) => {
      pending = { resolve, reject }
      worker.postMessage(message, transfer)
    })
    worker.onmessage = ({ data }) => {
      if (data.type === 'error') pending?.reject(Object.assign(new Error(data.text), { code: data.code, resourceURL: data.resourceURL, attempts: data.attempts }))
      else if (data.type === 'result' || data.type === 'rests-repaired') pending?.resolve(data)
      else onProgress({ phase: 'recognizing', ...data })
    }
    worker.onerror = event => pending?.reject(new Error(event.message || 'Score recognition worker failed'))
    let port = null
    if (!supported.jspi || forceSharedMemory) {
      const channel = new MessageChannel()
      networkWorker = new Worker(new URL('./ort.worker.js', import.meta.url), { type: 'module' })
      networkWorker.onerror = event => pending?.reject(new Error(event.message || 'Recognition network worker failed'))
      networkWorker.postMessage({ port: channel.port1 }, [channel.port1])
      port = channel.port2
    }
    onProgress({ phase: 'recognizing', text: 'Reading score…' })
    checkAbort()
    let result = await wait(send({ pages: pages.map(p => p.png), printedTuplets, port, modelBase }, port ? [port] : []))
    let doc = new DOMParser().parseFromString(result.xml, 'application/xml')
    if (doc.querySelector('parsererror')) throw new Error('Recognition returned invalid MusicXML')
    const sources = JSON.parse(doc.querySelector('miscellaneous-field[name="numeric-sources"]')?.textContent ?? '[]')
    const changes = []
    for (const source of sources) {
      if (!source.numberBox || !pages[source.page]) continue
      const reading = await wait(textOCR.readNumber(pages[source.page], source.numberBox))
      if (reading && reading.value !== source.count) changes.push({ sourceId: source.sourceId, count: reading.value, reading })
    }
    if (changes.length) {
      result = { ...result, ...await wait(send({ op: 'repair-rests', xml: result.xml, changes })) }
      doc = new DOMParser().parseFromString(result.xml, 'application/xml')
    }
    onProgress({ phase: 'text', text: 'Reading printed text…' })
    const prepared = await wait(prepareMetadata(pages, await wait(words), doc, { readTempoNumber: textOCR.readNumber }))
    annotate(doc, prepared.text.map(tokens), prepared)
    checkAbort()
    const audit = JSON.parse(doc.querySelector('miscellaneous-field[name="conversion-audit"]')?.textContent ?? '{}')
    audit.metadata = JSON.parse(doc.querySelector('miscellaneous-field[name="metadata-audit"]')?.textContent ?? '[]')
    return {
      musicxml: new XMLSerializer().serializeToString(doc), audit,
      rasters: pages.map(({ png, width, height }) => ({ png, width, height })),
      recognizerVersion: RECOGNIZER_VERSION, bridge: result.bridge,
      milliseconds: performance.now()-started,
    }
  } finally {
    if (signal?.aborted) await rendering?.catch(() => {})
    signal?.removeEventListener('abort', cancel)
    worker?.terminate()
    networkWorker?.terminate()
    textOCR.close()
    urls.forEach(url => URL.revokeObjectURL(url))
  }
}
