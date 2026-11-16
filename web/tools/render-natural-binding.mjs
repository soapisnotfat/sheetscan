// SPDX-License-Identifier: CC0-1.0
// Render only the original, hash-frozen bench/natural_binding_cases.py exercises.
import { readFile, writeFile } from 'node:fs/promises'
import { resolve, join } from 'node:path'
import { createHash } from 'node:crypto'
import createVerovioModule from 'verovio/wasm'
import { VerovioToolkit } from 'verovio/esm'
import { chromium } from 'playwright'

const out = resolve(process.argv[2]), freeze = JSON.parse(await readFile(join(out,'truth-freeze.json')))
const digest = data => createHash('sha256').update(data).digest('hex')
const browser = await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL || undefined})
const rows = []
try {
 const page = await browser.newPage({viewport:{width:1653,height:2339}})
 const module = await createVerovioModule()
 for(const row of freeze.cases) {
  const folder=join(out,row.id), truth=await readFile(join(folder,'truth.musicxml'))
  if(digest(truth)!==row.truthSHA256)throw Error('Changed frozen truth: '+row.id)
  const toolkit = new VerovioToolkit(module)
  toolkit.setOptions({pageWidth:2100,pageHeight:2970,scale:45,breaks:'auto',adjustPageHeight:false,font:row.font})
  toolkit.loadData(truth.toString())
  if(toolkit.getPageCount()!==1)throw Error('Expected one page')
  const svg=toolkit.renderToSVG(1)
  await writeFile(join(folder,'source.svg'),svg)
  await page.setContent(`<style>body{margin:0;background:white}svg{display:block;width:1653px;height:2339px}</style>${svg}`)
  await page.screenshot({path:join(folder,'source.png')})
  await page.setContent(`<style>@page{size:A4;margin:0}body{margin:0}svg{display:block;width:210mm;height:297mm}</style>${svg}`)
  await page.pdf({path:join(folder,'source.pdf'),preferCSSPageSize:true,printBackground:true})
  rows.push({...row,sourcePNG: digest(await readFile(join(folder,'source.png'))),sourcePDF:digest(await readFile(join(folder,'source.pdf')))})
  toolkit.destroy()
 }
 await writeFile(join(out,'raster-freeze.json'),JSON.stringify({truthFreezeSHA256:digest(await readFile(join(out,'truth-freeze.json'))),browser:browser.version(),cases:rows},null,2)+'\n')
 console.log(JSON.stringify(rows))
} finally {await browser.close()}
