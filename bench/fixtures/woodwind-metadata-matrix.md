# Source-text woodwind metadata matrix

This matrix is a bounded part of [Dripping issue #36](https://github.com/soapisnotfat/dripping/issues/36). Its MusicXML and source-text coordinates are original fixtures. It is not an independent woodwind recognition benchmark or an image-only tempo-glyph test.

The source annotation stage now supports an exact **Soprano, Alto, Tenor, or Baritone Saxophone** declaration in a `For …` source header or a source part label. Standard written-to-sounding transpositions are respectively `(-1, -2)`, `(-5, -9)`, `(-8, -14)`, and `(-12, -21)` in MusicXML diatonic/chromatic units. It requires one XML part, one compatible instrument record, and consistent source evidence. Written pitches, key signatures, notes and rhythms are unchanged.

The frozen JSON covers 72 instrument cases: headers, split text, part labels, matching XML names, explicit written/sounding declarations, concert-pitch guards, ambiguous and conflicting sources, multiple parts/instrument records, C woodwinds, and A/B-flat clarinets. Unsupported or key-ambiguous names are left for existing manual confirmation; the matrix does not infer their transposition. Existing XML transpose, for-part and concert-score declarations are preserved.

Fourteen explicit MusicXML tempo-unit/dot cases retain the printed beat-unit BPM and the exact quarter-equivalent playback BPM. A combined annotation fixture preserves a pickup and a genuine later tempo change while adding an explicit tenor declaration. These serializer/annotation controls do not expand the image recognizer's supported beat shapes, fonts, or stem directions.

Run from the repository root after `npm ci` in `web/`:

```sh
PLAYWRIGHT_EXECUTABLE_PATH=/usr/bin/chromium node bench/test_woodwind_metadata.mjs --output=/tmp/woodwind-metadata-report.json
node --test web/tools/annotation.test.mjs web/tools/metadata.test.mjs
```

The browser runner uses the actual source annotation module, records browser version, matrix/source hashes, results, and emitted XML. Omit `PLAYWRIGHT_EXECUTABLE_PATH` to use Playwright's installed Chromium. It needs no OCR language data, ONNX models, local Python or private scores. Runtime-model accuracy and the rest of issue #36 remain separate validation work.
