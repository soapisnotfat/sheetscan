// A distributable never copies arbitrary files from local public/.
// Only these reviewed tracked assets and pinned recognition assets are staged.
import { build } from 'vite'
import { copyFile, mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { tmpdir } from 'node:os'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const sdk = process.argv.includes('--sdk')
const out = join(root, sdk ? 'dist-sdk' : 'dist-public')
const expectedPath = process.argv.find(arg => arg.startsWith('--expected-manifest='))?.slice(20)
const tracked = ['sample.png', 'coi-serviceworker.min.js', 'Bravura-LICENSE.txt', 'Leipzig-LICENSE.txt']
const runtime = ['homr.zip', 'models/segnet.onnx', 'models/encoder.onnx', 'models/decoder.onnx']
const repository = resolve(root, '..')
const gitFiles = new Set(execFileSync('git', ['ls-files', '-z', '--', 'web/public', 'LICENSE', 'bench/tuplet-fonts', 'bench/accidental-fonts'], { cwd: repository, encoding: 'utf8' }).split('\0'))
const notices = ['LICENSE', ...[...gitFiles].filter(name => /^bench\/(?:tuplet|accidental)-fonts\/(?:[\w-]+-LICENSE\.txt|manifest\.json)$/.test(name))]
const staged = await mkdtemp(join(tmpdir(), 'sheetscan-public-'))
try {
  for (const name of [...tracked, ...runtime]) {
    if (tracked.includes(name) && !gitFiles.has(`web/public/${name}`)) throw new Error(`Untracked public asset refused: ${name}`)
    await mkdir(dirname(join(staged, name)), { recursive: true })
    await copyFile(join(root, 'public', name), join(staged, name))
  }
  for (const name of notices) {
    const destination = join(staged, name === 'LICENSE' ? name : `licenses/${name.slice(6)}`)
    await mkdir(dirname(destination), { recursive: true })
    await copyFile(join(repository, name), destination)
  }
  const sourceCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim()
  await writeFile(join(staged, 'SOURCE.txt'), `Source: https://github.com/soapisnotfat/sheetscan/tree/${sourceCommit}\nRecognition engine: https://github.com/liebharc/homr\nFork license: AGPL-3.0 (see LICENSE). Glyph artifacts and font notices: see licenses/.\n`)
  await build({ root, configFile: join(root, sdk ? 'vite.sdk.config.js' : 'vite.config.js'), publicDir: staged,
    build: { outDir: out, emptyOutDir: true } })
  const files = {}
  async function inventory(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name)
      if (entry.isDirectory()) await inventory(path)
      else {
        const name = relative(out, path)
        if (name.split('/').some(part => part.startsWith('.')) || /(?:private|dev-samples)|\.pdf$/i.test(name)) throw new Error(`Private/development asset refused: ${name}`)
        files[name] = createHash('sha256').update(await readFile(path)).digest('hex')
      }
    }
  }
  await inventory(out)
  if (expectedPath) {
    const expected = JSON.parse(await readFile(resolve(expectedPath), 'utf8'))
    for (const name of runtime) if (files[name] !== expected.browser[name]) throw new Error(`Runtime hash changed: ${name}`)
    const worker = Object.keys(files).find(name => /omr\.worker-.*\.js$/.test(name))
    const frozenWorker = Object.keys(expected.browser).find(name => /omr\.worker-.*\.js$/.test(name))
    if (!worker || files[worker] !== expected.browser[frozenWorker]) throw new Error('Recognition worker changed from frozen candidate')
  }
  await writeFile(join(out, 'public-build.json'), JSON.stringify({
    kind: sdk ? 'browser-sdk' : 'browser-app', recognizerVersion: 'v9-source-coverage',
    sourceCommit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
    stagedPublicAllowlist: [...tracked, ...runtime], trackedNotices: notices, files,
  }, null, 2)+'\n')
  console.log(`Safe ${sdk ? 'SDK' : 'app'} build: ${Object.keys(files).length} files; no local regression PDFs copied`)
} finally {
  await rm(staged, { recursive: true, force: true })
}
