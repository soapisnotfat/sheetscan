# Browser converter dependency

The SDK wraps the `v10-source-metadata` recognition policy, PDF rendering, local text OCR, multirest counts and MusicXML annotation. The main homr recognizer weights were not fine-tuned; this fork trains small glyph classifiers and improves the recognition pipeline. Independent varied-cohort qualification is required before claiming the user's 99% target. Development scores and isolated glyph scores are not population accuracy.

Build a distributable from the explicit public allowlist:

```sh
cd web
npm run build:sdk -- --expected-manifest=../dev-samples/candidates/v10-source-metadata/manifest.json
```

The ignored local manifest is a verification input; it is not copied into the package. `dist-sdk/` contains only built code, the three recognition ONNX models, `homr.zip`, and the reviewed tracked public assets. Local regression PDFs, `dev-samples/`, local manifests and source score files are excluded. `public-build.json` records distributable file hashes; the build checks its model/archive and recognition-worker hashes against the frozen candidate when `--expected-manifest` is supplied. `build:public` provides the same allowlist for the standalone app; deployment uses that output rather than arbitrary local `dist/` contents.

The fork is AGPL-3.0; glyph artifacts retain their OFL notices. The package includes `LICENSE`, exact source links in `SOURCE.txt`, and the tracked font licenses/manifests under `licenses/`.

Host the **whole** SDK directory under the app's origin, preserving `assets/` and `models/`. Recognition workers are module workers. Runtime dependencies download from pinned public CDNs; input scores are processed locally and are not uploaded.

```js
import { createScoreConverter, capabilities } from '/vendor/sheetscan/sheetscan.js'

const converter = createScoreConverter({ onProgress: event => updateImportProgress(event) })
const result = await converter.convert(fileInput.files, { signal: abortController.signal })
// Keep the existing project until conversion and the app's validation succeed.
loadMusicXML(result.musicxml)
// result also includes recognizerVersion, bridge, audit and exact PNG rasters.

converter.cancel() // rejects the active conversion with AbortError
converter.close()
```

One conversion runs at a time per instance; after cancellation or an error the instance can be used again. Each conversion terminates its recognition workers and revokes temporary image URLs. Cancellation interrupts the OMR worker immediately; a shared local text-OCR call already in progress may finish in the background. The API never changes the host project, navigates, reloads, or installs a service worker. The host controls when to replace its project and how to cache SDK/runtime assets in its existing offline service worker.

Source tempo annotation preserves the written beat unit and dot, with the corresponding quarter-note playback tempo. Pixel-only marks require a note glyph, equality sign and accepted local numeric OCR. Explicit Alto Saxophone source evidence can establish the conventional E-flat transposition for one unambiguous part; existing transposition and concert-score declarations are preserved, and written notes and keys stay unchanged. `result.audit.metadata` records the source evidence, applied changes and unknown bindings.

`capabilities()` reports JSPI and shared-memory support. JSPI is preferred; `forceSharedMemory: true` tests the alternate worker bridge. Without JSPI the host must already provide cross-origin isolation and SharedArrayBuffer. Unsupported pages reject with `code === 'UNSUPPORTED_BROWSER'`; the SDK does not register a COI service worker or reload the app. Desktop verification is not a mobile memory/performance guarantee.

Reproduce the actual browser API check, including cancellation, retry, retained host state, no service-worker registration and exact raster capture:

```sh
PLAYWRIGHT_CHANNEL=chrome node tools/sdk-smoke.mjs http://127.0.0.1:5196/ INPUT.pdf OUTDIR --shared
```

Score playback must consume MusicXML meter, tempo, voices, repeats and written pitch. Audio synchronization remains the host application's responsibility; this converter does not infer audio timestamps.
