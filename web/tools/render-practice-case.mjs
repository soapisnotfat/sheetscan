// Render a ground-truth MusicXML to PDF and page PNGs with existing dependencies.
//   cd web && node tools/render-practice-case.mjs ../dev-samples/accuracy/challenge/truth.musicxml
import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve, join } from 'node:path'
import createVerovioModule from 'verovio/wasm'
import { VerovioToolkit } from 'verovio/esm'
import { chromium } from 'playwright'

const input = resolve(process.argv[2]), out = dirname(input)
await mkdir(out, { recursive: true })
const toolkit = new VerovioToolkit(await createVerovioModule())
toolkit.setOptions({ pageWidth: 2100, pageHeight: 2970, scale: 45, breaks: 'auto', adjustPageHeight: false, font: 'Bravura' })
toolkit.loadData(await readFile(input, 'utf8'))
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || undefined })
try {
  const page = await browser.newPage({ viewport: { width: 1653, height: 2339 } })
  const svgs = []
  for (let i = 1; i <= toolkit.getPageCount(); i++) {
    const svg = toolkit.renderToSVG(i)
    svgs.push(svg)
    await writeFile(join(out, `p${i}.svg`), svg)
    await page.setContent(`<style>body{margin:0;background:white}svg{display:block;width:1653px;height:2339px}</style>${svg}`)
    await page.screenshot({ path: join(out, `p${i}.png`) })
  }
  await page.setContent(`<style>@page{size:A4;margin:0}body{margin:0}.page{page-break-after:always}.page:last-child{page-break-after:auto}svg{display:block;width:210mm;height:297mm}</style>${svgs.map(svg => `<div class="page">${svg}</div>`).join('')}`)
  await page.pdf({ path: join(out, 'score.pdf'), preferCSSPageSize: true, printBackground: true })
  console.log(`${toolkit.getPageCount()} page(s): ${out}`)
} finally {
  await browser.close()
}
