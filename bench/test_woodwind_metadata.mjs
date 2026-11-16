// Deterministic source-text/XML controls in a real browser; no model inference.
// PLAYWRIGHT_EXECUTABLE_PATH=/usr/bin/chromium node bench/test_woodwind_metadata.mjs
import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from '../web/node_modules/vite/dist/node/index.js'
import { chromium } from '../web/node_modules/playwright/index.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'),
  fixturePath = path.join(root, 'bench/fixtures/woodwind-metadata-matrix.json'),
  bytes = await readFile(fixturePath), matrix = JSON.parse(bytes),
  sourceHash = createHash('sha256').update(await readFile(path.join(root, 'web/src/metadata.js'))).digest('hex'),
  html = `<!doctype html><script type="module">
import { runWoodwindMetadataMatrix } from '/@fs/${root}/bench/woodwind_metadata_fixtures.mjs';
try { window.result = runWoodwindMetadataMatrix(await (await fetch('/woodwind-matrix.json')).json()); }
catch (error) { window.error = String(error.stack || error); }
</script>`
const server = await createServer({ root: path.join(root, 'web'), configFile: false,
  plugins: [{ name: 'woodwind-metadata-test', configureServer(server) {
    server.middlewares.use((req, res, next) => {
      if (req.url === '/woodwind-metadata') { res.setHeader('Content-Type', 'text/html'); res.end(html); return }
      if (req.url === '/woodwind-matrix.json') { res.setHeader('Content-Type', 'application/json'); res.end(bytes); return }
      next()
    })
  } }], server: { port: 0, host: '127.0.0.1', fs: { allow: [root] } } })
await server.listen()
let browser
try {
  browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || undefined })
  const page = await browser.newPage(), errors = []
  page.on('pageerror', error => errors.push(String(error)))
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/woodwind-metadata`)
  await page.waitForFunction(() => window.result || window.error, null, { timeout: 30000 })
  const outcome = await page.evaluate(() => ({ result: window.result, error: window.error }))
  if (outcome.error) throw Error(outcome.error)
  assert.deepEqual(errors, [])
  assert.equal(outcome.result.length, matrix.instrumentCases.length + matrix.tempoCases.length + 1)
  const report = { browser: browser.version(), fixtureSHA256: createHash('sha256').update(bytes).digest('hex'),
    metadataSourceSHA256: sourceHash, instrumentCases: matrix.instrumentCases.length, tempoCases: matrix.tempoCases.length,
    passed: outcome.result.length, scope: matrix.scope, results: outcome.result }
  const output = process.argv.find(arg => arg.startsWith('--output='))?.slice(9)
  if (output) await writeFile(path.resolve(output), JSON.stringify(report, null, 2) + '\n')
  console.log(JSON.stringify({ ...report, results: undefined }, null, 2))
} finally {
  await browser?.close()
  await server.close()
}
