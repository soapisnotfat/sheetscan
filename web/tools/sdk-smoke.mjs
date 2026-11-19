// Exercise the shipped SDK in isolated Chrome, including cancel/retry and host safety.
// PLAYWRIGHT_CHANNEL=chrome node tools/sdk-smoke.mjs URL INPUT.pdf OUTDIR [--shared]
import { chromium } from 'playwright'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { basename, join, resolve } from 'node:path'
import { createHash } from 'node:crypto'

const [url, inputArg, outArg] = process.argv.slice(2)
const input = resolve(inputArg), out = resolve(outArg)
await mkdir(out, { recursive: true })
const bytes = await readFile(input)
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || undefined })
try {
  const page = await browser.newPage()
  await page.route(url, route => route.fulfill({
    contentType: 'text/html', body: '<!doctype html><title>SDK host fixture</title>',
    headers: { 'Cross-Origin-Opener-Policy': 'same-origin', 'Cross-Origin-Embedder-Policy': 'require-corp' },
  }))
  page.on('console', message => { if (message.text().startsWith('SDK ')) console.log(message.text()) })
  await page.goto(url)
  const result = await page.evaluate(async ({ data, name, forceSharedMemory }) => {
    const { createScoreConverter, capabilities } = await import(new URL('sheetscan.js', location.href).href)
    const file = new File([Uint8Array.from(atob(data), c => c.charCodeAt(0))], name, { type: 'application/pdf' })
    const before = location.href
    const registrationsBefore = (await navigator.serviceWorker.getRegistrations()).length
    window.hostProject = { id: 'existing-project', unchanged: true }
    const converter = createScoreConverter()
    let cancelled = false
    try {
      await converter.convert([file], { onProgress: event => { if (event.phase === 'recognizing') converter.cancel() } })
    } catch (error) { cancelled = error.name === 'AbortError' }
    if (!cancelled) throw new Error('SDK cancellation did not reject with AbortError')
    const phases = []
    const converted = await converter.convert([file], { forceSharedMemory, onProgress: event => {
      if (phases.at(-1) !== event.phase) { phases.push(event.phase); console.log(`SDK ${event.phase}`) }
    } })
    converter.close()
    if (location.href !== before || window.hostProject.id !== 'existing-project' || !window.hostProject.unchanged) throw new Error('SDK changed its host page or project')
    const registrationsAfter = (await navigator.serviceWorker.getRegistrations()).length
    if (registrationsAfter !== registrationsBefore) throw new Error('SDK installed a service worker')
    return { ...converted, audit: converted.audit, capabilities: capabilities(), cancelledAndRetried: cancelled,
      hostUnchanged: true, serviceWorkersAdded: registrationsAfter-registrationsBefore, phases,
      rasters: converted.rasters.map(p => ({ width: p.width, height: p.height, bytes: [...new Uint8Array(p.png)] })) }
  }, { data: bytes.toString('base64'), name: basename(input), forceSharedMemory: process.argv.includes('--shared') })
  await writeFile(join(out, 'score.musicxml'), result.musicxml)
  const rasters = []
  for (let i = 0; i < result.rasters.length; i++) {
    const page = result.rasters[i], png = Buffer.from(page.bytes)
    await writeFile(join(out, `page-${i+1}.png`), png)
    rasters.push({ page: i+1, width: page.width, height: page.height, sha256: createHash('sha256').update(png).digest('hex') })
  }
  const { musicxml, audit, rasters: unused, ...metadata } = result
  await writeFile(join(out, 'run.json'), JSON.stringify({ ...metadata, browser: browser.version(), rasters,
    inputSha256: createHash('sha256').update(bytes).digest('hex'), outputSha256: createHash('sha256').update(musicxml).digest('hex'),
  }, null, 2)+'\n')
  console.log(JSON.stringify({ bridge: result.bridge, milliseconds: result.milliseconds, cancelledAndRetried: result.cancelledAndRetried,
    hostUnchanged: result.hostUnchanged, serviceWorkersAdded: result.serviceWorkersAdded, pages: rasters.length }))
} finally {
  await browser.close()
}
