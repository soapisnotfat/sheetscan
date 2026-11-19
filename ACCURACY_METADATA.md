# Source metadata coverage

This stage adds a source-only asynchronous metadata prepass while preserving synchronous annotate. It fixes a printed mid-score tempo that was already present in PDF text but assigned to the previous staff, and recovers scanned metronome marks only after image note-glyph, equality-stroke and digit-crop evidence. No source filename, reference value or target measure number is used by production code.

## Evidence and results

| Local source role | Raw evidence | Verified output |
|---|---|---|
| Controlled PDF | PDF.js already yielded quarter+93 and quarter+104. The latter baseline was760.61; the old font-box center heuristic incorrectly preferred the preceding staff. | quarter93 in measure1 and quarter104 in measure18, bound by source coordinates |
| Local scanned source B | Full-page OCR saw a96 equation at confidence0, so the normal text filter discarded it. | Source glyph+equality+digit crop produced quarter96 with five agreeing OCR readings |
| Local scanned source C | No PDF text layer; OCR read92 but lost its beat glyph/equality. | Source glyph+equality+digit crop produced quarter92 with five agreeing OCR readings |

All three applications preserved every written pitch and key element exactly. Local source B has legacy XML without source note coordinates: only a source-image verified opening mark in the first staff header can bind the first measure. A coordinate-free middle mark remains unknown. No existing measure count or missing-bar issue was repaired or aligned to a reference.

Source B/C headers explicitly say For Alto Saxophone. The controlled PDF has a clear single-part Alto Saxophone label. A unique compatible part gains score-instrument and diatonic=-5/chromatic=-9, using the standard alto-instrument convention; this is an instrument-context inference, not an interval printed numerically in the source. It does not change written notes or key signatures. If a reference omits transpose, report that metadata discrepancy separately instead of altering the reference or counting transposition inference as a core pitch-accuracy gain.

## Interface

```js
import { prepareMetadata } from './metadata.js'
const prepared = await prepareMetadata(pages, await words, doc)
annotate(doc, prepared.text.map(tokens), prepared)
```

The third annotate argument is optional. Existing two-argument synchronous callers remain valid. The prepass returns text/layout/sourceAudit; raw input words remain unchanged, and only the prepared view removes an OCR digit duplicated by a verified image mark. Input PDF records now preserve raw text transforms, font name/family and provenance. The parent owns main/converter integration and SDK audit.metadata exposure.

Numeric tempo needs an explicit supported beat unit or verified image glyph. Bare numbers/equalities and OCR letters do not default to quarter BPM. The direction retains beat-unit and dot; sound uses exact quarter-note BPM (for example dotted eighth61 ->45.75, dotted half61 ->183). No default120 is inserted. Multi-tempo lines retain distinct source tokens and anchors.

Transposition is skipped for explicit concert-score text or existing XML defaults/concert-score, existing attributes/for-part, existing transpose, multiple/ambiguous parts, multiple source instruments, conflicting part names or missing explicit alto evidence. Only a unique generic Voice/Music/Part instrument name is updated in place; its instrument ID is preserved. Explicit real instrument declarations are not overwritten. Every applied/unknown decision is recorded in metadata-audit.

## Validation

- 24 fresh source-authored browser fixtures passed: start/middle and same-line tempos, exact dotted half/eighth conversion, per-staff multipart tempo binding, source-only alto metadata, explicit-transpose and XML concert-score/for-part preservation, concert/multipart/no-source/conflicting-instrument abstention, source image quarter/half/eighth+dot, and hard negatives for bare digits, equality without beat, note without equality, ordinary letter equations and coordinate-free middle placement.
- Ten Node tests passed, including all six existing annotation tests and four new unit/provenance tests.
- All three actual-source output XMLs passed the official local MusicXML4 schema.
- The current full app and converter SDK were exercised end to end on the controlled PDF, not only by applying annotate to cached XML. Both output the two source tempos and preserve the frozen baseline written core. SDK host state/location stays unchanged and adds no service worker. The completed full-chain receipt below records its own pre-guard source hashes. The final XML concert-score/for-part preservation guards are covered by fresh browser counterexamples; the parent runs the final immutable safe-built SDK separately.

The earlier multirest default-test font dependency was independently fixed in commitd2f2306: missing optional development fonts produce explicit skips; the full font sweep remains an explicit command.

## Reproduce without embedding private sources

All public probes accept local CLI configuration. No private source path, title, GT, screenshot or embedded raster is committed. Source configs/words/crops/output XML stay ignored/local.

```sh
node --test web/tools/annotation.test.mjs web/tools/metadata.test.mjs
node bench/probe_metadata.mjs /tmp/metadata-evidence --sources=/tmp/local-sources.json
node bench/test_metadata_browser.mjs /tmp/metadata-output /tmp/metadata-evidence/evidence.json --cases=/tmp/local-cases.json
node bench/probe_metadata_full.mjs /tmp/metadata-full --input=SOURCE_FILE --baseline=PREVIOUS_READING --expected=/tmp/local-expected.json
```

Source config entries are `{name,file}`; application cases add `xml`. Optional expected metadata is supplied externally as `{tempos:[[measure,bpm],...],chromatic:value}`. Without a cases config the browser test runs only its original authored fixtures. OCR/code/model downloads use existing public runtimes; score pixels are processed on device and served only through a whitelisted local probe server.

## Frozen evidence

| Artifact | SHA256 |
|---|---|
| web/src/annotate.js | `5fa4321fa29d6d631dd6d3354af7125ac8f17ae81d4d2f5bc08b096d1f40227b` |
| web/src/input.js | `949638cc75ed9d36ea7c45a4406568fbf45399f954425a104073f060dbc8c958` |
| web/src/metadata.js | `7e7aa9a1a66f6ffa93d7f7e74b3edcc44eb939e82861658e19aa867d496421b7` |
| Original raw-word receipt | `31d0d21bf07fe9591f41b93ba6d1e620108ed5d27640b27a3ca83c9013b7221e` |
| Final source/fixture application receipt | `8ec7344fed1b81d8021292f28658290c587a0b6c4a2054b03529ba42f7b83930` |
| Completed pre-preservation-guard full app/SDK receipt | `38965ae5fe6b13a7c4fb9f1c926656c99318c02c155a610e0256416f867959b7` |
| Source A | `a1e7c6c8dfabb3207c61ec5cd35c6cfd7924c75fcad08a60969bb8dfa84522a7` |
| Source B | `7980c3afdabba6cc919eecb038005c851669f1df8258e12ab6bf859c169ae476` |
| Source C | `acb3a6c7e0f78641303c080d848a5b555a183854343052eab9e35a90d16224d1` |

Raw PDF/OCR word boxes and source raster captures: `/tmp/metadata-evidence-v9/`. Final three-source/fresh-fixture applications: `/tmp/metadata-final/`. Full current app/SDK results: `/tmp/metadata-final-full/`.

Remaining limits: the image-glyph path is bounded to upright quarter/half/eighth shapes, horizontal printed staves and the existing digit OCR range. Unsupported, damaged, ambiguous or unanchored marks are not qualified. The source-image header fallback is conservative and does not recover middle-measure timing without coordinates. Source C title OCR remains imperfect; this stage does not claim to repair titles, core note recognition, missing bars or overall OMR accuracy.
