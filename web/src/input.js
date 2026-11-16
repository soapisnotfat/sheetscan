// Files (PDFs, photos) -> page images for the recogniser, plus any text a PDF carries.
import * as pdfjs from 'pdfjs-dist'
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorker

const DPI = 200 // what the recogniser was benchmarked at
const MAX_SIDE = 2600 // photos larger than this gain nothing

async function finish(canvas, text = []) {
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
  return { png: await blob.arrayBuffer(), url: URL.createObjectURL(blob), width: canvas.width, height: canvas.height, text }
}

function abortError(signal) {
  return signal?.reason?.name === 'AbortError' ? signal.reason : new DOMException('Page preparation cancelled', 'AbortError')
}

function checkAbort(signal) {
  if (signal?.aborted) throw abortError(signal)
}

async function* pdfPages(file, signal) {
  checkAbort(signal)
  const data = await file.arrayBuffer()
  checkAbort(signal)
  const loadingTask = pdfjs.getDocument({ data })
  let renderTask, destroying, failed = false
  const destroy = () => destroying ??= loadingTask.destroy()
  const cancel = () => {
    renderTask?.cancel()
    // The finally block awaits this same cleanup. Attach a handler immediately
    // since abort can fire while a different PDF.js promise is still pending.
    destroy().catch(() => {})
  }
  signal?.addEventListener('abort', cancel, { once: true })
  if (signal?.aborted) cancel()
  try {
    checkAbort(signal)
    const pdf = await loadingTask.promise
    for (let n = 1; n <= pdf.numPages; n++) {
      checkAbort(signal)
      const page = await pdf.getPage(n)
      checkAbort(signal)
      const viewport = page.getViewport({ scale: DPI / 72 })
      const canvas = Object.assign(document.createElement('canvas'), { width: viewport.width, height: viewport.height })
      const context = canvas.getContext('2d')
      context.fillStyle = '#fff'
      context.fillRect(0, 0, canvas.width, canvas.height)
      // "print" renders without waiting for animation frames, which stop in a background tab.
      renderTask = page.render({ canvasContext: context, canvas, viewport, intent: 'print' })
      try { await renderTask.promise } finally { renderTask = null }
      checkAbort(signal)
      // Text items in page-image pixels: x/y is the start of the baseline, h the font height.
      const { items, styles } = await page.getTextContent()
      checkAbort(signal)
      const text = items
        .filter((item) => item.str?.trim())
        .map((item) => {
          const t = pdfjs.Util.transform(viewport.transform, item.transform)
          return { str: item.str, x: t[4], y: t[5], h: Math.hypot(t[2], t[3]), w: item.width * viewport.scale,
            source: 'pdf-text', fontName: item.fontName, fontFamily: styles[item.fontName]?.fontFamily,
            raw: { str: item.str, transform: [...item.transform], width: item.width, height: item.height } }
        })
      const result = await finish(canvas, text)
      if (signal?.aborted) URL.revokeObjectURL(result.url)
      checkAbort(signal)
      yield result
    }
  } catch (error) {
    failed = true
    throw signal?.aborted ? abortError(signal) : error
  } finally {
    signal?.removeEventListener('abort', cancel)
    try { await destroy() } catch (error) { if (!failed && !signal?.aborted) throw error }
  }
}

async function imagePage(file) {
  const bitmap = await createImageBitmap(file) // applies the photo's EXIF rotation
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
  const canvas = Object.assign(document.createElement('canvas'), { width: bitmap.width * scale, height: bitmap.height * scale })
  canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  return finish(canvas)
}

/** All pages in order. Optional third argument: {signal}; returned URLs belong to the caller. */
export async function loadPages(files, onProgress = () => {}, { signal } = {}) {
  const pages = []
  try {
    for (const file of files) {
      checkAbort(signal)
      const isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name)
      if (isPdf) for await (const page of pdfPages(file, signal)) onProgress(pages.push(page))
      else {
        const page = await imagePage(file)
        pages.push(page)
        checkAbort(signal)
        onProgress(pages.length)
      }
    }
    checkAbort(signal)
    return pages
  } catch (error) {
    pages.forEach(page => URL.revokeObjectURL(page.url))
    throw signal?.aborted ? abortError(signal) : error
  }
}
