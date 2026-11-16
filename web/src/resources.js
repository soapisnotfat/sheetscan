// Verified static assets only. The host serves these files from its own origin;
// no browser-side CDN fallback, inference API or user content leaves the device.
import assets from './runtime-assets.json'

const models = {
  'segnet.onnx': '6ed36640db4ef5d223098b6d5efe4eda97c66b24a2c72faab8a018c749003a8d',
  'encoder.onnx': 'ee5767286c60dc3d567fe72b6560e7285261ede1535b4215153c199ab3057559',
  'decoder.onnx': '99a6ac39770616bc1a20d6c409bb85fbbe21ba47f972984f9ef834fb5741b96f',
  'homr.zip': '349b6b37ef35cea68cdeee820ca5b084cf50870073190675cfc2d6e1f384b709',
}
const modelBytes = { 'segnet.onnx': 57311361, 'encoder.onnx': 52861122, 'decoder.onnx': 47356003 }
const nativeFetch = globalThis.fetch.bind(globalThis)
let base, progress = () => {}, activeSignal, hooked = false
const inFlight = new Map()
const hash = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), n => n.toString(16).padStart(2, '0')).join('')
const aborted = signal => { if (signal?.aborted) throw signal.reason ?? new DOMException('Download cancelled', 'AbortError') }
const mime = url => /\.wasm$/.test(url) ? 'application/wasm' : /\.m?js$/.test(url) ? 'text/javascript' : /\.json$/.test(url) ? 'application/json' : 'application/octet-stream'

export function resourceError(url, message, code = 'RESOURCE_DOWNLOAD_FAILED', attempts = 1) {
  const error = new Error(`${message}: ${new URL(url).pathname}`)
  Object.assign(error, { code, resourceURL: String(url), attempts })
  return error
}

export function configureResources(packageBase, { signal, onProgress = () => {} } = {}) {
  base = packageBase
  activeSignal = signal
  progress = onProgress
}

export const runtimeURL = path => new URL('runtime/' + path, base).href

function metadata(url) {
  const relative = new URL(url).pathname.split('/runtime/')[1]
  if (relative && assets[relative]) return assets[relative]
  const name = new URL(url).pathname.split('/').at(-1)
  return models[name] ? { sha256: models[name], bytes: modelBytes[name] } : null
}

/** Complete, verified downloads are cached. Quota errors affect offline reuse only. */
export async function assetBytes(url, { signal = activeSignal, onBytes = () => {} } = {}) {
  url = new URL(url, base).href
  const expected = metadata(url)
  if (!expected) throw resourceError(url, 'Unpinned recognition resource', 'UNPINNED_RESOURCE')
  aborted(signal)
  let cache
  try { cache = await caches.open('omr-assets-v1') } catch (error) {
    progress({ phase: 'downloading', resourceURL: url, warning: 'CACHE_UNAVAILABLE', text: 'Browser cache unavailable; downloading this resource for the current attempt.' })
  }
  if (cache) {
    let cached
    try { cached = await cache.match(url) } catch { /* Fetch remains available when cache reads fail. */ }
    if (cached) {
      const bytes = await cached.arrayBuffer()
      if ((!expected.bytes || bytes.byteLength === expected.bytes) && await hash(bytes) === expected.sha256) {
        onBytes(bytes.byteLength, bytes.byteLength)
        progress({ phase: 'downloading', resourceURL: url, resource: new URL(url).pathname, done: bytes.byteLength, total: bytes.byteLength, cached: true, text: 'Using downloaded resource.' })
        return bytes
      }
      await cache.delete(url).catch(() => {})
      progress({ phase: 'downloading', resourceURL: url, warning: 'CACHE_CHECKSUM_MISMATCH', text: 'A cached resource is incomplete or damaged; downloading it again.' })
    }
  }
  let failure
  for (let attempt = 1; attempt <= 3; attempt++) {
    aborted(signal)
    const controller = new AbortController(), relay = () => controller.abort(signal.reason)
    signal?.addEventListener('abort', relay, { once: true })
    const timeout = setTimeout(() => controller.abort(new Error('Resource download timed out')), 90000)
    try {
      const response = await nativeFetch(url, { signal: controller.signal, cache: 'no-cache' })
      if (!response.ok) throw resourceError(url, `HTTP ${response.status}`, 'RESOURCE_HTTP_ERROR', attempt)
      const reader = response.body.getReader(), chunks = []
      const total = expected.bytes || Number(response.headers.get('content-length')) || 0
      let done = 0
      for (;;) {
        const { value, done: end } = await reader.read()
        if (end) break
        chunks.push(value)
        done += value.length
        onBytes(done, total)
        progress({ phase: 'downloading', resourceURL: url, resource: new URL(url).pathname, done, total, attempt, maxAttempts: 3, text: `Downloading ${new URL(url).pathname.split('/').at(-1)}…` })
      }
      const bytes = await new Blob(chunks).arrayBuffer()
      if (expected.bytes && bytes.byteLength !== expected.bytes || await hash(bytes) !== expected.sha256) throw resourceError(url, 'Downloaded resource checksum mismatch', 'RESOURCE_CHECKSUM_MISMATCH', attempt)
      aborted(signal)
      if (cache) try {
        await cache.put(url, new Response(bytes, { headers: { 'Content-Type': mime(url), 'Content-Length': String(bytes.byteLength), 'X-Content-SHA256': expected.sha256 } }))
      } catch {
        progress({ phase: 'downloading', resourceURL: url, warning: 'CACHE_WRITE_FAILED', text: 'Resource is ready. Browser storage could not keep an offline copy.' })
      }
      return bytes
    } catch (error) {
      aborted(signal)
      failure = error?.resourceURL ? error : resourceError(url, error?.message || 'Network request failed', 'RESOURCE_DOWNLOAD_FAILED', attempt)
      if (attempt < 3) progress({ phase: 'downloading', resourceURL: url, resource: new URL(url).pathname, attempt, maxAttempts: 3, retrying: true, text: `Download interrupted. Retrying ${new URL(url).pathname.split('/').at(-1)} (${attempt + 1}/3)…` })
    } finally {
      clearTimeout(timeout)
      signal?.removeEventListener('abort', relay)
    }
  }
  throw failure
}

export async function prepareResources(group) {
  const paths = Object.entries(assets).filter(([, value]) => value.group === group).map(([path]) => path)
  // Bound simultaneous large responses and expose real per-resource byte progress.
  for (let index = 0; index < paths.length; index += 2) await Promise.all(paths.slice(index, index + 2).map(path => assetBytes(runtimeURL(path))))
}

/** Handles fetches made by Pyodide/ORT themselves, including their WASM/wheels. */
export function installResourceFetch() {
  if (hooked) return
  hooked = true
  globalThis.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (!metadata(url)) return nativeFetch(input, init)
    const key = new URL(url, base).href
    // The engines occasionally request the same runtime concurrently.
    let pending = inFlight.get(key)
    if (!pending) { pending = assetBytes(key, { signal: init?.signal ?? activeSignal }); inFlight.set(key, pending); pending.finally(() => inFlight.delete(key)).catch(() => {}) }
    const bytes = await pending
    return new Response(bytes, { headers: { 'Content-Type': mime(url), 'Content-Length': String(bytes.byteLength) } })
  }
}

export async function importResource(path) {
  const url = runtimeURL(path)
  await assetBytes(url)
  let failure
  for (let attempt = 1; attempt <= 3; attempt++) {
    aborted(activeSignal)
    try { return await import(/* @vite-ignore */ url + (attempt === 1 ? '' : `?retry=${attempt}`)) }
    catch (error) { failure = resourceError(url, error.message || 'Module loading failed', 'RESOURCE_MODULE_FAILED', attempt) }
  }
  throw failure
}
