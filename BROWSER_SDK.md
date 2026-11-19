# Browser converter dependency

The SDK wraps the `v11-natural-binding` recognition policy, PDF rendering, local text OCR, multirest counts and MusicXML annotation. The main homr recognizer weights were not fine-tuned; this fork trains small glyph classifiers and improves the recognition pipeline. Independent varied-cohort qualification is required before claiming the user's 99% target. Development scores and isolated glyph scores are not population accuracy.

Build a distributable from the explicit public allowlist:

```sh
cd web
npm run build:sdk -- --expected-manifest=../dev-samples/candidates/v11-natural-binding/manifest.json
```

The ignored local manifest is a verification input; it is not copied into the package. `dist-sdk/` contains only built code, the three recognition ONNX models, `homr.zip`, and the reviewed tracked public assets. Local regression PDFs, `dev-samples/`, local manifests and source score files are excluded. `public-build.json` records distributable file hashes; the build checks its model/archive and recognition-worker hashes against the frozen candidate when `--expected-manifest` is supplied. `build:public` provides the same allowlist for the standalone app; deployment uses that output rather than arbitrary local `dist/` contents.

Natural cancellation uses an intact source glyph bound to an unambiguous segmented notehead. A connected or partial glyph near a later head can stop a carried natural while preserving the model's pitch; it cannot assert a new accidental. Slur/beam ink entirely above or below the head does not meet this blocker rule. Unresolved head provenance also stops carry. The existing simple single-voice policy and bar reset remain in effect.

The fork is AGPL-3.0; glyph artifacts retain their OFL notices. The package includes `LICENSE`, exact source links in `SOURCE.txt`, and the tracked font licenses/manifests under `licenses/`.

The `v16-source-grace-slurs` SDK checks a decoded same-pitch grace-to-principal curve against the original page before the exporter classifies it as a tie. A clearly separated arc anchored to both noteheads preserves the slur. Both anchors must come from an unambiguous source-note match. The normal tie rule handles pairs with unsupported or ambiguous geometry. `result.audit.graceSlurChanges` identifies each retained slur by its note IDs, page, and source box. The 111 cropped controls in `bench/fixtures/grace-curves.*` include printed ties and absent curves.

The `v17-source-beams` SDK writes numbered MusicXML beams when a visible stem-to-stem stroke has unique matches in the same measure, voice and staff and agrees with the written durations. The source bindings cover secondary levels, supported short hooks, grace groups and rests inside a continuous beam. `result.audit.sourceBeamChanges` records the contributing connections and hooks. This pass derives engraving from the source image. It leaves pitch, onset, duration and playback semantics in the original recognition path.

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


## Static runtime and preview

The `v14-static-runtime` SDK retains the accepted `v13-woodwind-pdf` recognizer, ONNX bytes and postprocessing. Its required ORT 1.31.1, Pyodide 314.0.7, Python wheels and Tesseract 7.0.0/English/German assets are served from the SDK's own `runtime/` directory. No browser-side external CDN is required. `web/runtime-lock.json` records each exact public download URL, size and SHA-256. The full original runtime and wheel license texts are retained in `web/runtime-notices.txt`; their separate licenses also remain inside the shipped wheel archives. Binary runtime files stay out of Git. Pass a content-addressed verified cache using `--runtime-cache=/path/to/cache` when building the SDK.

`renderPreview(files, {signal, onProgress, onPage, maxWidth: 1400})` streams each rendered page through `onPage` and resolves `{pages}`. Each page contains `{png, width, height, fileIndex, page, pageCount}`; file indices start at zero and page numbers at one. This only uses PDF.js and never starts recognition, OCR or model downloads. The host can render those PNG bytes on its own canvas. Its packaging must externalize the embedded PDF.js worker to a same-origin file when its CSP excludes executable data URLs.

`createScoreConverter({modelBase, onProgress}).convert(files, {signal})` accepts an optional absolute `modelBase` whose `models/{segnet,encoder,decoder}.onnx` URLs contain the same pinned weights. A host can retain a stable model-set URL when updating SDK code, so cached weights are reused. Each conversion owns its OCR worker and downloads; cancelling an earlier conversion cannot terminate a later one.

Download progress is per resource: `{phase: 'downloading', resourceURL, resource, done, total, attempt, maxAttempts}`. `total` describes that file, not total conversion completion. `retrying` and cache `warning` fields describe recovery. Resource errors retain `code`, `resourceURL` and `attempts`. Downloads retry at most three times, reset a 45-second idle timer after each received chunk and retain a separate 30-minute cap; manual cancellation remains available. Successful bytes are SHA-256 verified before being cached. Unavailable or full browser caches do not discard otherwise usable downloads.
