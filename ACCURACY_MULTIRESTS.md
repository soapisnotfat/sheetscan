# OM07 symbolic multirest source evidence

The source-only `read_multirest_regions` API now locates old-style breve/longa/maxima/composite rests and H rests with an above-staff count crop. On the authorized corrected v3 browser source it finds exactly three regions, and the unchanged browser number reader returns **4, 8 and 17**. It does not infer counts from a symbol, filename, expected measure total or reference score. The lead agent owns score-note binding and expansion.

**This is extraction evidence, not an end-to-end accuracy qualification.** The 28 newly authored legal MusicXML renderings have 28/28 linked regions, but only 22/28 counts are accepted by the existing browser OCR: six are rejected, no incorrect count is accepted. Counts 5 and some Bravura 8s remain OCR limitations. Unknown readings must remain unresolved.

## Raw decoder diagnosis before changing the extractor

The probe called the immutable v8 source (`dev-samples/candidates/v8-bounded-fragments/source`, commit2a184348d9a21c6df2f7958e1ea6ea493aa33757) on the **valid corrected v3 browser PNG**. It monkeypatched only diagnostic hooks, saving actual staff pixels, exact encoder input and `ScoreDecoder.generate` output before staff filtering, codec conversion or XML construction. No reference MusicXML was read, no output token was edited, and the old invalid rest13–24 input was not used.

- Source PNG SHA256: `f5814101744b6bed6e997f77e52e0ee14988a9f9ee788af7a4138aebdc08859a`.
- Staff2 (zero-based) contains the complete printed4 and longa; neither is clipped in the saved 256×1280 staff input.
- Its raw decoder rest tokens are `rest_4` (an ordinary quarter rest earlier in the system), **`rest_1` at the visible longa4**, then `rest_8m` at the neighboring H8.
- The later printed17 H rest is raw `rest_10m`.
- Therefore the four-bar source was already decoded as a whole rest. It was not a `rest_4m` that disappeared in expansion. The existing numeric-source hook only captures decoded multirest classes, so this ordinary whole-rest token never acquired a count-reading record. The vocabulary does include `rest_4m`; vocabulary availability does not establish that the decoder selected it.

| Model/input evidence | SHA256 |
|---|---|
| Staff2 raw array | `149138a606d2c0e9b5b4e574fcdbbc46560fc0ebea866a0b84be18818d6b3f0d` |
| Encoder2 float32 [1,1,256,1280] | `da2d8d04e7dbd48e0fedb9ee278df9f520e5ac207fa84ca00e6b55635c1bba79` |
| Staff2 displayed PNG | `cf9c20057bbb09a086c2dc8b0a8db6414cce7b82847f115ebde973d0c4ac3901` |
| segnet_308-3296ccd40960f90ca6ab9c035cca945675d30a0f.onnx | `6ed36640db4ef5d223098b6d5efe4eda97c66b24a2c72faab8a018c749003a8d` |
| encoder_pytorch_model_509-2293bba14bfea47d9d28411339362af15fce4c31.onnx | `ee5767286c60dc3d567fe72b6560e7285261ede1535b4215153c199ab3057559` |
| decoder_pytorch_model_509-2293bba14bfea47d9d28411339362af15fce4c31.onnx | `99a6ac39770616bc1a20d6c409bb85fbbe21ba47f972984f9ef834fb5741b96f` |

Native recognizer version: homr0.7.1. Source-file hashes are preserved in the full receipt; frozen pipeline SHA `6b83e6d4562ae1bfda828493d1115b93c57c0009d56ae6c1b4cbce36a4025fd4` and old score_numbers SHA `8caa7fcd2b3296b3eae2c2ac23cf2b22f0c47551881c345d2844621e0a365aba` match the v8 snapshot.

## API and integration contract

```python
from score_numbers import read_multirest_regions
regions = read_multirest_regions(original_image, staff_boxes)
```

`staff_boxes` uses existing `[left, top_line, right, bottom_line, ...]` layout entries in **original input pixels**. Each region returns:

- `staff`: exact index into the supplied staff-box array.
- `style`: H, longa, breve, maxima, or symbols.
- `shapeBox`: original-pixel rectangle supporting the rest-shape proposal.
- `numberBox`: original-pixel clean above-staff count crop, for the existing native/browser digit reader.
- `center`: proposal center and `evidence: shape-and-above-number`.

No count, score-note ID, meter duration or expansion is invented. `shapeBox` bounds the detected support; for a widely spaced composite it can omit an outer slab. It is not a pixel-perfect group segmentation and must never be used to derive a count or expanded span. The number crop and musical binding are the operative count evidence.

The extractor requires a supported in-staff rest shape **and** compact separated above-staff ink. A lone ordinary whole/half rest is not a symbolic-multirest shape. Narrow longa/breve slabs must have the right size, density and staff-line position. H rests require one thick horizontal body with end caps; parallel secondary beams and substantial interior stems are rejected. Thin anti-aliased staff remnants are removed before symbolic components. Whole-rest pieces may join nearby supported vertical slabs, but cannot seed a group alone.

The existing `read_meters` and `read_forward_repeats` function ASTs remain exactly unchanged. `rest_number_box(image, box, point)` keeps its signature, first tries the new source regions and preserves the old H fallback. The new independent region scan is necessary even when that wrapper abstains: the H8 raw attention is displaced enough that old attention-local lookup can still miss it. Do not enlarge an attention search so far that neighboring4 and8 can be interchanged.

**Required lead integration:** scan regions independently of raw token type; bind a unique region to an existing rest/sourceID with score order and staff/context evidence; create a count1 record for a whole-rest token when appropriate; promote/expand only after an accepted printed count>1; retain unknown OCR readings for review. Check key/time/clef boundaries and all affected voices. The component never edits XML, changes source notation, forces use-symbols=no, fills a target bar count or changes the main recognizer weights.

## Authorized corrected source: actual browser result

| Region | Shape box | Number box | Browser count |
|---|---|---|---:|
| Staff2 longa | [792, 520, 799, 548] | [782, 467, 810, 502] | 4 |
| Staff2 H | [913, 520, 1040, 549] | [963, 467, 990, 502] | 8 |
| Staff5 H | [1468, 1051, 1599, 1080] | [1509, 998, 1557, 1033] | 17 |

The native Tesseract5 callback accepted17 but rejected these tight4/8 crops. The4 glyph could produce a low-confidence44. Actual browser Tesseract7 read all three correctly. A rejected or inconsistent native reading is not authority to replace it with an expected count.

## Independent authored fixture families

New fixtures under `bench/fixtures/multirest-families/` are original CC0 MusicXML sources, with explicit uncollapsed source measures. They are not copies of existing evaluation references. They cover2/3/4/5/8/11/17 with use-symbols=yes and no; 4/4,3/4,6/8,2/2; alternating treble/bass clefs and changing keys. Attributes change only outside each multirest span, so there is no hidden key/meter/clef change inside a collapsed group. Both source files passed the official local MusicXML4 schema. Verovio legitimately switches17 to H notation even under use-symbols=yes; lower values exercise breve, longa and composite3/5/8/11 styles.

| Render family | Regions / expected | Correct accepted counts | Unknown |
|---|---:|---:|---:|
| Bravura-symbols-1 | 7 / 7 | 5 / 7 | 2 |
| Bravura-H-1 | 7 / 7 | 5 / 7 | 2 |
| Leipzig-symbols-1 | 7 / 7 | 6 / 7 | 1 |
| Leipzig-H-1 | 7 / 7 | 6 / 7 | 1 |

All accepted fixture counts are correct. The six unknowns are Bravura symbols/H5 and8, and Leipzig symbols/H5. Generic crop-margin trials of .5,1 and2staff units did not resolve them; no source-specific number fallback was added. Improving that digit OCR is a separate bounded follow-up. These fixtures establish region coverage and abstention behavior, not full-score recognition accuracy.

A second raster sweep uses **actual OFL SMuFL font outlines** drawn independently with Pillow; the runtime has no glyph template bank for rests. Bravura, Leipzig, Leland, Sebastian and Eugene are tested at staff gaps8/12/20/30px with direct and3× anti-aliased sampling. Seven count families plus the actual SMuFL restMaxima variant give **320/320 cases with one linked region**. This metric is region production, not a pixel IoU score or proof of unseen-score generalization. Font outlines can share designs; the sweep is functional coverage.

The72 negative cases (four gaps×two sampling modes×nine families) produce **zero regions**: ordinary whole rest+4, ordinary half rest+4, full barline+measure4, tempo4, number only, longa without count, displaced numeral, ordinary double-beamed notes+4, and one staff's numeral above another staff's longa. These tests exposed a genuine double-beam-as-H false proposal during development; the parallel-beam check fixes it. They also exposed anti-alias staff bridges and low-resolution staff thickness, which the final morphology handles. This finite negative suite does not guarantee rejection of every notation/text collision.

## Actual browser verification

HeadlessChrome157 and Pyodide314.0.7 loaded the exact current Python module and existing NumPy/OpenCV WASM packages. All28 authored regions plus the3 corrected-source regions were extracted in the browser; unchanged `web/src/ocr.js` then performed on-device count OCR. The script records module, OCR and raster hashes. This exercises the real crop-coordinate interface, not just CPython unit tests. It does not validate main-pipeline binding/expansion or certify the score's final bar count.

## Reproduce

From the Sheetscan root, using the existing development environments:

```sh
../.venv/bin/python bench/probe_multirests.py --raw --image dev-samples/independent-eval/validated-v3/browser-v8/rests-v3-render-corrected/input-1.png --out /tmp/multirest-raw-v8-final
../.venv/bin/python bench/test_symbolic_multirests.py --sweep --out /tmp/multirest-sweep
node bench/probe_multirests_browser.mjs /tmp/multirest-browser-release
```

The raw probe defaults to the frozen v8 source and writes staff PNGs, exact encoder arrays, raw tokens, model/source hashes and a diagnostic reading. It does not import the mutable current pipeline. Browser verification uses installed local Verovio/Playwright and Chrome, plus on-device Pyodide/Tesseract dependencies. It serves only whitelisted local fixtures/runtime files and the explicitly authorized corrected source.

For a fresh font cache, run existing `bench/train_accidental_glyphs.py prepare --fonts /tmp/multirest-fonts --out /tmp/multirest-unused`, then pass `--fonts /tmp/multirest-fonts` to the sweep. No accidental training is run. Browser WASM wheels are the exact NumPy/OpenCV filenames in `web/node_modules/pyodide/pyodide-lock.json`, cached under `/tmp/tuplet-glyph-run/pyodide/`; the public package origin is https://cdn.jsdelivr.net/pyodide/v314.0.7/full/. Font licenses/hashes are preserved in existing `bench/accidental-fonts/manifest.json`; no font installation or new runtime dependency is needed.

For an arbitrary source image and existing staff-layout JSON:

```sh
../.venv/bin/python bench/probe_multirests.py --image page.png --boxes staff-boxes.json --out /tmp/multirest-regions --ocr
```

## Frozen hashes and limits

| Artifact | SHA256 |
|---|---|
| Final score_numbers.py | `e4d8b9cab7cbf9e6de305617f4e307f7cfc6a2b3cd86b88e599c3ce544095488` |
| Browser OCR source | `112503857425d9392fe41db69712862d612d9a54a12e467744d083adac24ed5a` |
| Raw decoder receipt | `dadeda9f59f1b563d7cd4ac4e78e338f5768c8438907b54529d25c7b87ceaf44` |
| Raster sweep receipt | `728c39c752c30bbc5694279d1c58c6959607fde019df29111e9900a78e3fe420` |
| Browser receipt | `4b4ad201727f7f85fbf7be768df6b450525c80354aa0368d7f8dbffa1f699217` |
| bench/fixtures/multirest-families/H.musicxml | `e35be0576d958522596d13cf570563a2a7e349283c11181205b85f599a7b69c5` |
| bench/fixtures/multirest-families/symbols.musicxml | `39451e5b13b6afbb8a6abe2b74d08cadf8140c3dc9263b63d3b6610cf27ca54e` |
| Bravura-symbols-1 PNG | `eeb219551ac829fb0ddc4c7c10741dc5bf9256f37013092c7e02ededdcd46449` |
| Bravura-H-1 PNG | `9f14ec96dc7abf28aef39dbaba424f454a3802163e9a991662a13d30217b62d7` |
| Leipzig-symbols-1 PNG | `f2bbee1ae9ba28bdf0216c428d019b408c29390c6b36f56c0844d7d2a0184c29` |
| Leipzig-H-1 PNG | `968022e283ee5516cf3e85a1984936fd2dc33960a37c97e6bfc19f1bf0eaac0a` |
| Bravura font | `cdf0f893ee1fdb64b7f6713d71ee0dcfc349c0ac01429a8e451b01a9e79f5f3b` |
| Leipzig font | `ee0457af412610b58f7f47ebc7584e6a15fd1f752c399597e063a550959d0b31` |
| Leland font | `293788a40584b1908e3a0f219833f6a13e9a1aaf671e08fd26ad18fad2631b35` |
| Sebastian font | `661ff0227af5816ffba947e432365d7c3d42a23a28793a70b3db1eda6a3d027b` |
| Eugene font | `2f969fe9788592a712be35e53783cd9443eef70a3c93174fb1d11f99ed146b92` |

Detailed receipts and raw inputs remain under `/tmp/multirest-raw-v8-final/`, `/tmp/multirest-sweep/` and `/tmp/multirest-browser-release/`. The evidence above preserves the substantive result and exact hashes. Remaining limits include six fixture OCR abstentions, attention-to-source association, pixel-perfect composite support, severe scan damage, visually ambiguous count-vs-measure labels, complex simultaneous voices and staff/group boundary binding. An above-staff ink group is only a digit candidate until OCR validates it. No source outside the authorized corrected v3 materials or the original authored fixtures was used, and no GT, metrics or renderer file was modified.
