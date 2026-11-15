// Text on pages which have no text layer (scans, photos), for title, lyrics and chord
// symbols. Tesseract loads on first use: its code and language data come from the CDN.
const TESSERACT = 'https://cdn.jsdelivr.net/npm/tesseract.js@7.0.0/dist/tesseract.esm.min.js'

let worker

async function start() {
  const tesseract = await import(/* @vite-ignore */ TESSERACT)
  const made = await (tesseract.default ?? tesseract).createWorker(['eng', 'deu'])
  // "Sparse text": words scattered over the page. The default layout analysis looks for
  // columns of prose and loses most of the text between staves.
  await made.setParameters({ tessedit_pageseg_mode: '11' })
  return made
}

let last = Promise.resolve()

/** Words on a page image as the tokens annotate.js takes: [{str, x, y, h, w}]. */
export function ocr(page) {
  return (last = last.catch(() => {}).then(() => read(page))) // the worker takes one page at a time
}

/** Read the printed count above a model-detected multirest; stays on this device. */
export function readNumber(page, box) {
  return (last = last.catch(() => {}).then(() => readDigits(page, box)))
}

async function readDigits(page, [left, top, right, bottom]) {
  if (right <= left || bottom <= top) return null
  const made = await (worker ??= start())
  const bitmap = await createImageBitmap(new Blob([page.png], { type: 'image/png' }))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round((right - left) * 4) + 48
  canvas.height = Math.round((bottom - top) * 4) + 48
  const context = canvas.getContext('2d', { willReadFrequently: true })
  context.fillStyle = '#fff'
  context.fillRect(0, 0, canvas.width, canvas.height)
  context.drawImage(bitmap, left, top, right - left, bottom - top, 24, 24, canvas.width - 48, canvas.height - 48)
  bitmap.close()
  const original = context.getImageData(0, 0, canvas.width, canvas.height)
  // Whole-word OCR can collapse adjacent narrow digits (e.g. "11" -> "1").
  // Their serifs can overlap in x, so use connected ink rather than column gaps.
  const labels = new Int32Array(canvas.width * canvas.height), components = []
  const ink = index => {
    const i = index * 4
    return (original.data[i] + original.data[i + 1] + original.data[i + 2]) / 3 < 160
  }
  for (let seed = 0; seed < labels.length; seed++) {
    if (labels[seed] || !ink(seed)) continue
    const id = components.length + 1, pending = [seed], glyph = { id, left: canvas.width, right: 0, top: canvas.height, bottom: 0, area: 0 }
    labels[seed] = id
    while (pending.length) {
      const index = pending.pop(), x = index % canvas.width, y = Math.floor(index / canvas.width)
      glyph.left = Math.min(glyph.left, x); glyph.right = Math.max(glyph.right, x + 1)
      glyph.top = Math.min(glyph.top, y); glyph.bottom = Math.max(glyph.bottom, y + 1); glyph.area++
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
        const nx = x + dx, ny = y + dy, next = ny * canvas.width + nx
        if (nx >= 0 && nx < canvas.width && ny >= 0 && ny < canvas.height && !labels[next] && ink(next)) { labels[next] = id; pending.push(next) }
      }
    }
    components.push(glyph)
  }
  const glyphs = components.filter(g => g.area >= 20 && g.bottom - g.top >= (canvas.height - 48) * .25).sort((a, b) => a.left - b.left)
  const separate = glyphs.length >= 2 && glyphs.length <= 3 && glyphs.every(g => g.right - g.left >= 4 && g.bottom - g.top >= (canvas.height - 48) * .25)
  const readings = []
  try {
    for (const [mode, binary] of [[7, false], [7, true], [13, true]]) {
      const pixels = new ImageData(new Uint8ClampedArray(original.data), original.width, original.height)
      if (binary) for (let i = 0; i < pixels.data.length; i += 4) {
        const value = (pixels.data[i] + pixels.data[i + 1] + pixels.data[i + 2]) / 3 >= 160 ? 255 : 0
        pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = value
      }
      context.putImageData(pixels, 0, 0)
      await made.setParameters({ tessedit_pageseg_mode: String(mode), tessedit_char_whitelist: '0123456789' })
      const { data } = await made.recognize(canvas)
      const text = data.text.replace(/\s/g, '')
      if (/^\d{1,3}$/.test(text) && +text >= 2 && +text <= 256 && data.confidence >= 55)
        readings.push({ value: +text, score: data.confidence, mode })
    }
    if (separate) for (const binary of [false, true]) {
      const digits = [], scores = []
      for (const glyph of glyphs) {
        const part = document.createElement('canvas')
        part.width = glyph.right - glyph.left + 48; part.height = glyph.bottom - glyph.top + 48
        const target = part.getContext('2d', { willReadFrequently: true })
        target.fillStyle = '#fff'; target.fillRect(0, 0, part.width, part.height)
        const isolated = target.getImageData(0, 0, part.width, part.height)
        for (let y = glyph.top; y < glyph.bottom; y++) for (let x = glyph.left; x < glyph.right; x++) {
          const index = y * canvas.width + x
          if (labels[index] !== glyph.id) continue
          const dest = ((y - glyph.top + 24) * part.width + x - glyph.left + 24) * 4
          isolated.data.set(original.data.subarray(index * 4, index * 4 + 4), dest)
        }
        target.putImageData(isolated, 0, 0)
        if (binary) {
          const pixels = target.getImageData(0, 0, part.width, part.height)
          for (let i = 0; i < pixels.data.length; i += 4) {
            const value = (pixels.data[i] + pixels.data[i + 1] + pixels.data[i + 2]) / 3 >= 160 ? 255 : 0
            pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = value
          }
          target.putImageData(pixels, 0, 0)
        }
        await made.setParameters({ tessedit_pageseg_mode: '10', tessedit_char_whitelist: '0123456789' })
        const { data } = await made.recognize(part)
        digits.push(data.text.trim()); scores.push(data.confidence)
      }
      const text = digits.join(''), score = Math.min(...scores)
      if (digits.every(digit => /^\d$/.test(digit)) && +text >= 2 && +text <= 256 && score >= 55)
        readings.push({ value: +text, score, mode: 'separate-glyphs' })
    }
  } finally {
    await made.setParameters({ tessedit_pageseg_mode: '11', tessedit_char_whitelist: '' })
  }
  const counts = new Map()
  for (const r of readings) counts.set(r.value, (counts.get(r.value) ?? 0) + 1)
  const best = [...counts].sort((a, b) => b[1] - a[1])[0]
  return best && best[1] >= 2 ? { value: best[0], agreement: best[1], observations: readings } : null
}

async function read(page) {
  const { data } = await (await (worker ??= start())).recognize(page.url, {}, { blocks: true })
  return (data.blocks ?? [])
    .flatMap((block) => block.paragraphs)
    .flatMap((paragraph) => paragraph.lines)
    .flatMap((line) => line.words)
    // Notes and beams come out as low-confidence scraps. Besides words, keep the hyphens
    // between syllables and the "= 120" of a metronome mark.
    .filter((word) => word.confidence > 55 && /\p{L}|^-+$|=|^\d{2,3}\)?$/u.test(word.text))
    .map(({ text, bbox }) => ({ str: text, x: bbox.x0, w: bbox.x1 - bbox.x0, y: bbox.y1, h: bbox.y1 - bbox.y0 }))
}
