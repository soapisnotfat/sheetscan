// Local-only conversion API. Importing this module never installs a service
// worker, navigates, reloads, or edits the host application's project.
import { loadPages } from './input.js'
import { ocr, readNumber } from './ocr.js'
import { annotate, tokens } from './annotate.js'

export const RECOGNIZER_VERSION = 'v8-bounded-fragments'

export function capabilities() {
  const jspi = typeof WebAssembly.Suspending === 'function'
  const sharedMemory = globalThis.crossOriginIsolated && typeof SharedArrayBuffer === 'function'
  return { jspi, sharedMemory: !!sharedMemory, supported: jspi || !!sharedMemory }
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

export async function convertScore(files, { signal, onProgress = () => {}, printedTuplets = true, forceSharedMemory = false } = {}) {
  const supported = capabilities()
  signal?.throwIfAborted()
  if (!supported.supported || forceSharedMemory && !supported.sharedMemory) {
    const error = new Error('Score conversion requires WebAssembly JSPI or a cross-origin isolated page with shared memory')
    error.code = 'UNSUPPORTED_BROWSER'
    throw error
  }
  files = Array.from(files)
  if (!files.length) throw new Error('Choose at least one score PDF or image')
  const started = performance.now(), urls = []
  let worker, networkWorker, pending, rejectAbort
  const aborted = new Promise((_, reject) => { rejectAbort = reject })
  // The abort may occur during page rendering, before an inference request.
  aborted.catch(() => {})
  const cancel = () => {
    const error = signal.reason ?? new DOMException('Score conversion cancelled', 'AbortError')
    worker?.terminate()
    networkWorker?.terminate()
    pending?.reject(error)
    rejectAbort(error)
  }
  signal?.addEventListener('abort', cancel, { once: true })
  const wait = promise => Promise.race([promise, aborted])
  try {
    onProgress({ phase: 'rendering', text: 'Preparing score pages…' })
    signal?.throwIfAborted()
    const rendering = loadPages(files, n => onProgress({ phase: 'rendering', page: n }))
    rendering.then(pages => {
      if (signal?.aborted) pages.forEach(p => URL.revokeObjectURL(p.url))
    }).catch(() => {})
    const pages = await wait(rendering)
    urls.push(...pages.map(p => p.url))
    signal?.throwIfAborted()
    const words = Promise.all(pages.map(p => p.text.length ? p.text : ocr(p)))
    words.catch(() => {})
    worker = new Worker(new URL('./omr.worker.js', import.meta.url), { type: 'module' })
    const send = (message, transfer = []) => new Promise((resolve, reject) => {
      pending = { resolve, reject }
      worker.postMessage(message, transfer)
    })
    worker.onmessage = ({ data }) => {
      if (data.type === 'error') pending?.reject(new Error(data.text))
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
    signal?.throwIfAborted()
    let result = await wait(send({ pages: pages.map(p => p.png), printedTuplets, port }, port ? [port] : []))
    let doc = new DOMParser().parseFromString(result.xml, 'application/xml')
    if (doc.querySelector('parsererror')) throw new Error('Recognition returned invalid MusicXML')
    const sources = JSON.parse(doc.querySelector('miscellaneous-field[name="numeric-sources"]')?.textContent ?? '[]')
    const changes = []
    for (const source of sources) {
      if (!source.numberBox || !pages[source.page]) continue
      const reading = await wait(readNumber(pages[source.page], source.numberBox))
      if (reading && reading.value !== source.count) changes.push({ sourceId: source.sourceId, count: reading.value, reading })
    }
    if (changes.length) {
      result = { ...result, ...await wait(send({ op: 'repair-rests', xml: result.xml, changes })) }
      doc = new DOMParser().parseFromString(result.xml, 'application/xml')
    }
    onProgress({ phase: 'text', text: 'Reading printed text…' })
    annotate(doc, (await wait(words)).map(tokens))
    signal?.throwIfAborted()
    const audit = JSON.parse(doc.querySelector('miscellaneous-field[name="conversion-audit"]')?.textContent ?? '{}')
    return {
      musicxml: new XMLSerializer().serializeToString(doc), audit,
      rasters: pages.map(({ png, width, height }) => ({ png, width, height })),
      recognizerVersion: RECOGNIZER_VERSION, bridge: result.bridge,
      milliseconds: performance.now()-started,
    }
  } finally {
    signal?.removeEventListener('abort', cancel)
    worker?.terminate()
    networkWorker?.terminate()
    urls.forEach(url => URL.revokeObjectURL(url))
  }
}
