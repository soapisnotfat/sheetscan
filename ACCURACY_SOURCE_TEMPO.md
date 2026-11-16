# Source tempo coverage

`v12-source-tempo` keeps a metronome note, its separate augmentation dot and
equality together before generic PDF text joining discards isolated music glyphs.
Unit evidence is tracked at the individual mark's character position. Production
preprocessing requires a source music glyph or verified local image geometry;
ordinary `q`, `h`, `e`, numbers and equations cannot establish the unit. One
readable glyph on a page no longer disables image fallback for another mark.
Old-style descending digits remain inside the local number crop. No confidence
threshold or page search extent was relaxed.

Explicit text glyphs cover whole through 64th, including down-stem SMuFL forms;
image geometry covers upright half, quarter and eighth. Other image-only beat
shapes remain outside this geometry reader's supported scope. The source mapping
follows the [SMuFL metronome table](https://smufl.formats.music/latest/tables/metronome-marks.html).
`sound@tempo` uses the exact quarter equivalent, including fractional dotted units.
No BPM is inferred from a tempo word, and no default 120 is added. Existing
transpose, concert-score, for-part, instrument conflict and unique-part guards
are unchanged. The model, Python recognition code and Worker are unchanged from
the parent base; this package makes no core note-accuracy claim.

Verification commands (private inputs are supplied only in local CLI JSON):

```sh
node --test web/tools/annotation.test.mjs web/tools/metadata.test.mjs
node bench/test_metadata_browser.mjs OUT [LOCAL_OCR_EVIDENCE] --cases=LOCAL_CASES
node web/tools/build-public.mjs
node web/tools/build-public.mjs --sdk
node bench/test_tempo_production.mjs --app=APP_DIST --sdk=SDK_DIST --cases=LOCAL_INPUTS --base-results=BASE_RUNS --out=OUT
```

The browser suite retains all 24 prior fixtures and adds 39 CC0 source-authored
cases: separated units and dots, seven explicit units, three image units, two
digit fonts/DPI scales, mixed text/image marks on one line, 11 entirely negative
cases and a mixed glyph/plain-letter counterexample. Every expected value and
actual PNG hash is written before recognition. The 13 Node tests include the
original ten. Three authorized local source-score regressions are also retained.
Browser and production receipts, private rasters, input hashes and exact output
metadata remain in the local evidence directory and are never public assets.

`bench/repair_tempo_render.py` is a test-input preflight/repair tool, not runtime
inference. It accepts original PDF/SVG provenance and an OFL fallback font. It
requires genuinely empty source-font slots and explicit original SVG unit
codepoints, preserves original drawing operators, and appends only fallback ink.
It never reads MusicXML or a target BPM/measure. Original files are never
overwritten. Render repairs have separate versioned hashes and are evaluated on
both the actual immutable old dist and the new dist. Recovery caused by repairing
a missing test glyph is reported separately from software improvements; historical
core failures remain valid. Poppler pixel differences must stay inside the glyph
masks. Browser antialias differences are recorded separately rather than called
exact pixel identity.

The production runner waits for the completed app view, runs printed-symbol
recognition, then checks SDK cancellation/retry, retained host state, no new service
worker and static GET-only local serving. It compares written pitch (including
alter), key, voice, duration, meter, staff and form against the same parent base.
The app editor's existing redundant accidental-display normalization is recorded
separately from pitch semantics. Production qualification requires the sealed
receipt, not a helper-only pass.
