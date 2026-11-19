# OM06 accidental evidence and frozen classifier

The allowed development score now yields 62 raw-image/head-adjacent candidates covering all 36 visually read local accidentals, including the explicit natural after the bottom-system B-sharp. The CNN accepts all 36 with the correct shape; it also accepts four key-signature sharps, which require musical-context filtering. It rejects all 22 non-accidental candidates on this page. This is a **development-page diagnostic**, not an independent score-accuracy claim. On the newly held-out Eugene font stress test the conservative classifier has only **64.0% positive recall**, alongside **99.886% negative rejection** and **99.600% accepted precision**. Raw staff-crossed crops are mostly rejected; use the supplied staff-removal extractor.

## Actual evidence came first

Only the explicitly authorized source `dev-samples/independent-eval/validated-v2/dev-sharp-syncopation/input-1.png` and current prediction `dev-samples/diagnosis/native-v3-geometry-cnn/dev-sharp-syncopation.musicxml` were read. No reference MusicXML, score holdout, error-list labels, or metrics files were opened. The source PNG was manually inspected to record 36 local accidental positions before model training; labels were not obtained from predicted pitches. Additional shape/context labels distinguish four key-signature proposals from 22 non-accidental proposals. These source images/labels were never consumed by the synthetic trainer.

Directly calling the installed, unmodified **homr 0.7.1** base detector produced seven staffs and 174 segmented heads. Its `Staff.symbols` contained 174 `Note` objects and **zero `Accidental` objects**. A source search found no `Accidental(...)` construction outside the model class itself. The `symbols` segmentation mask had four foreground pixels; the actual accidental ink was in the `clefs_keys` mask (class 3). Therefore the existence of an Accidental class did not establish that typed or untyped accidental objects were available.

Head-left-neighbor connected components from actual `clefs_keys` yielded 40 untyped proposals, covering 34/36 visually read local signs under a source-point inclusion criterion (3 px tolerance). They missed the flat near (1096,195) and the natural near (226,1227). Several other components were truncated or split; point coverage alone does not establish a complete glyph. The bottom-system sharp and following natural appear before two B4 heads; the current prediction explicitly retained alter=1 on the latter (`n176-p0-243-1228`). This is observed source/prediction disagreement, not a pitch target used for training.

The raw-pixel complement uses actual segmented head centers mapped to original input pixels, removes long horizontal staff ink before a 3x1 vertical close, obtains connected components, and filters by local staff-unit size and a right-hand head. It does not use transformer attention coordinates. On this page:

| Evidence path | Local-sign coverage / 36 | Correct local types | Other candidates |
|---|---:|---:|---|
| homr Accidental objects | 0 / 36 | unavailable | objects are never constructed |
| Segnet clefs_keys components | 34 / 36 | untyped | 40 total components; some truncated/split |
| Raw-pixel CC + segmented-head neighborhood | 36 / 36 | untyped | 62 total components |
| Fixed template baseline on raw CC | 36 / 36 | 35 / 36 accepted | 3 accepted key-signature sharps, no accepted non-sign shapes |
| Frozen CNN on raw CC | 36 / 36 | 36 / 36 accepted | 4 accepted key-signature sharps, 22 / 22 non-sign shapes rejected |

The fixed template baseline used max cosine over the four train fonts and all five accidental kinds, minimum cosine .85 and class margin .10. Its one local rejection was a flat (cv024; best cosine .824). It made no local wrong-class assertion. The CNN improves that one rejection on this development page; this small observation does not establish an overall advantage over templates on external scores.

## Runtime interface and integration contract

```python
from accidental_glyphs import read_accidentals, classify_accidental
marks = read_accidentals(image, staff_boxes, heads)
```

- `image`: original input image, gray or BGR.
- `staff_boxes`: `[left, top_line, right, bottom_line, ...]`, all in original image pixels. The array index is the `staff` identifier.
- `heads`: dictionaries `{staff, center: [x,y], position, id?}`. Centers must be the **segmented noteheads mapped by homr to_input**, not attention coordinates. `position` is the detector staff position. Optional `id` is carried through; assigning a score-note ID safely remains the caller's job.
- Each result is JSON-safe: `staff`, `box: [left,top,right,bottom]`, `center`, `head_index` (index into the exact supplied heads list), `head_id`, `position`, `kind`, `unknown`, `score`, `margin`, and per-kind `scores`. `kind` is natural/sharp/flat/double-sharp/double-flat or None. Unknown candidates remain available for auditing.
- `classify_accidental(ink)` accepts a tight 2D foreground crop (0..1 or 0..255). Scores are **raw logits**, not calibrated probabilities. Margin includes the unknown class. Do not reuse cosine thresholds.
- `accidental_candidates(...)` exposes the same untyped candidates with isolated cleaned `ink` arrays for diagnostics.
- Browser worker must inject `accidental_glyphs.py` and `accidental_classifier.json` together. No new runtime package is needed beyond existing NumPy/cv2.

**Lead integration still owns:** key-signature/header context, unique head-to-note mapping, octave-sensitive per-measure accidental state, key changes, chord/voice ambiguities, ties and cautionary signs. An isolated key-signature sharp/flat is visually identical to a local accidental and is deliberately classified by shape. The component never changes score pitch or XML. Prefer explicit natural/sharp/flat evidence first; double-sharp recall is weak. Ambiguous, fragmented or merged candidates should remain unknown. True end-to-end pitch-state and polyphonic safety validation are outside this component.

## Predeclared synthetic experiment

- Train fonts: Bravura, Leipzig, Leland, Sebastian. Newly held-out font: Eugene; this is a new accidental-classification experiment and does not reuse the prior Sebastian tuplet test as an overall independence claim. Eugene advertises Bravura fallback designs, so a separate font file does not establish independence of every outline.
- Counts: train 27,000 (2,400 per positive kind plus 15,000 negatives), dev 7,500 (500 per kind plus 5,000 negatives), test 10,500 (700 per kind plus 7,000 negatives). Split seeds 906410 / 906411 / 906412.
- Positive kinds: natural E261, sharp E262, flat E260, double-sharp E263, double-flat E264. Four equally weighted conditions: clean, staff lines added then removed, raw crossing staff lines, thin horizontal dropout/closing. Heights 14..62px, width perturbation, small rotation, anti-aliasing/blur/threshold variation.
- Negatives: real font noteheads, clefs, rests, tuplet digits and dynamics; NotoSans alphanumeric text; procedural noteheads/stems; same-ink accidental + attached notehead; multi-glyph clusters (including key-like repeated signs); and large glyph fragments. Isolated key-signature signs cannot truthfully be labeled shape negatives, so they are not.
- CNN: Conv(1,8,3), ReLU/pool2, Conv(8,16,3), ReLU/pool2, Linear(768,32), ReLU, Linear(32,6); 26,054 parameters. Weights float16/base64, accumulation float32; model 70,428 bytes.
- AdamW lr .0015, weight decay .0003, batch256, 24epochs, torch seed906400, four CPU threads; weighted CE unknown=.65/others=1. Training48.3s, excluding raster construction. Environment Python3.13 / torch2.15.0 / NumPy2.5.5 / cv2 5.0.0 / Pillow13.0.0.
- Dev-only gate grid maximizes correct accepts while keeping dev-negative false accepts <=.1% per kind and accepted wrong-class counts <=.5% per kind. No gate/weight adjustment followed the first Eugene test. The high-rejection setting is a deliberate safety/recall tradeoff, not a calibrated probability threshold.

## Frozen results

| Split | Positive recall | Negative rejection | Accepted precision |
|---|---:|---:|---:|
| Dev | 61.800% | 99.940% | 99.806% |
| Eugene test | 64.000% | 99.886% | 99.600% |

| Eugene condition | Correct / n | Recall |
|---|---:|---:|
| clean | 760 / 875 | 86.857% |
| dropout | 729 / 875 | 83.314% |
| staff-raw | 17 / 875 | 1.943% |
| staff-removed | 734 / 875 | 83.886% |

**Raw crossing staff lines are not a supported direct input path:** 17/875 were accepted correctly. The supplied extraction performs whole-staff line removal before tight glyph normalization. Even after removal, held-font recall is 83.886%; source-domain coverage and classification must continue to be audited.

| Kind | Test recall | Accepted precision | Min logit | Min margin |
|---|---:|---:|---:|---:|
| natural | 64.143% | 99.557% | 0 | 5 |
| sharp | 71.857% | 100.000% | 8 | 4 |
| flat | 73.714% | 99.231% | 0 | 5 |
| double-sharp | 37.000% | 98.855% | 0 | 5 |
| double-flat | 73.286% | 100.000% | 0 | 5 |

Test confusion matrix, rows expected / columns predicted. Unknown includes abstentions. Of the 3,500 positive glyphs, one natural was asserted as flat; the other unsuccessful positives were rejected. Eight of 7,000 negatives were accepted.

| Expected / predicted | unknown | natural | sharp | flat | double-sharp | double-flat |
|---|---:|---:|---:|---:|---:|---:|
| unknown | 6992 | 2 | 0 | 3 | 3 | 0 |
| natural | 250 | 449 | 0 | 1 | 0 | 0 |
| sharp | 197 | 0 | 503 | 0 | 0 | 0 |
| flat | 184 | 0 | 0 | 516 | 0 | 0 |
| double-sharp | 441 | 0 | 0 | 0 | 259 | 0 |
| double-flat | 187 | 0 | 0 | 0 | 0 | 513 |

| Negative family | Rejected / n | False accepts |
|---|---:|---:|
| fragment | 998 / 1000 | 2 |
| merged | 1000 / 1000 | 0 |
| multi-glyph | 997 / 1000 | 3 |
| music | 997 / 1000 | 3 |
| primitive | 2000 / 2000 | 0 |
| text | 1000 / 1000 | 0 |

## Runtime verification

- Four tests passed: byte/unit normalization and float32 overshoot, invalid inputs, blank rejection, and a staff-crossed synthetic natural candidate associated with a segmented head.
- 128 fixed synthetic-dev crops: CPython NumPy vs frozen float16 torch max logit error 0.00001812, argmax100% agreement.
- Actual HeadlessChrome157 / Pyodide314.0.7: same128crops, max logit error 0.00001478, argmax100%, 0.681ms/crop. Local WASM NumPy/OpenCV only; no torch/ONNX inference dependency.
- Browser parity verifies the classifier arithmetic, not full-page extraction or accidental-state pitch repair. The actual source candidate test used native cv2 4.14.0; full browser-source extraction remains a lead integration check.

## Reproduce

From the Sheetscan repository root:

```sh
../.venv/bin/python bench/probe_accidentals.py --image dev-samples/independent-eval/validated-v2/dev-sharp-syncopation/input-1.png --prediction dev-samples/diagnosis/native-v3-geometry-cnn/dev-sharp-syncopation.musicxml --out /tmp/accidental-probe
../.copisteria-venv/bin/python bench/train_accidental_glyphs.py prepare --fonts /tmp/accidental-fonts --out /tmp/accidental-glyph-run
../.copisteria-venv/bin/python bench/train_accidental_glyphs.py train --fonts /tmp/accidental-fonts --out /tmp/accidental-glyph-run --epochs 24
../.copisteria-venv/bin/python bench/train_accidental_glyphs.py test --fonts /tmp/accidental-fonts --out /tmp/accidental-glyph-run
../.venv/bin/python bench/probe_accidentals.py --image dev-samples/independent-eval/validated-v2/dev-sharp-syncopation/input-1.png --prediction dev-samples/diagnosis/native-v3-geometry-cnn/dev-sharp-syncopation.musicxml --out /tmp/accidental-probe --raw-cv --labels /tmp/accidental-probe/visual-labels.json --classify
../.copisteria-venv/bin/python bench/test_accidental_glyphs.py --run /tmp/accidental-glyph-run
```

The probe snapshots the installed homr Python source before detection and records all source/model/image/prediction hashes. The active pipeline is never imported. `train` writes a freeze receipt before test generation; `test` refuses changed model bytes. `prepare` verifies exact OFL font byte hashes. Raster-library versions can change dataset hashes.

For browser parity, cache the exact NumPy/OpenCV wheels named in `web/node_modules/pyodide/pyodide-lock.json` under `/tmp/accidental-glyph-run/pyodide/` from `https://cdn.jsdelivr.net/pyodide/v314.0.7/full/`, then:

```sh
../.copisteria-venv/bin/python bench/test_accidental_glyphs.py --run /tmp/accidental-glyph-run --browser
```

This starts a localhost server and uses installed Playwright plus `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`. Images and tensor archives remain outside git. No shared pipeline/worker files are part of this change.

## Source visual point inventory

The inventory below was independently read from the allowed source PNG. It is a development-only coverage annotation, not score ground truth used for training. To reproduce coverage, encode each row as `{staff, kind, point:[x,y]}` in `/tmp/accidental-probe/visual-labels.json`; optional provenance text does not affect matching. Boxes cover a point with a3px tolerance. This criterion cannot by itself prove that the entire sign survived segmentation.

| Staff index | Source point | Shape |
|---|---|---|
| 0 | 417, 195 | flat |
| 0 | 466, 195 | natural |
| 0 | 527, 181 | natural |
| 0 | 604, 167 | flat |
| 0 | 732, 174 | flat |
| 0 | 906, 174 | natural |
| 0 | 1096, 195 | flat |
| 0 | 1301, 195 | natural |
| 0 | 1511, 202 | flat |
| 1 | 207, 365 | sharp |
| 1 | 270, 359 | flat |
| 1 | 839, 323 | sharp |
| 2 | 207, 484 | sharp |
| 2 | 338, 484 | natural |
| 2 | 420, 484 | flat |
| 2 | 520, 506 | flat |
| 2 | 1319, 526 | natural |
| 3 | 249, 675 | flat |
| 3 | 514, 669 | sharp |
| 3 | 554, 669 | natural |
| 3 | 927, 683 | natural |
| 3 | 1070, 704 | sharp |
| 3 | 1110, 704 | natural |
| 3 | 1371, 676 | sharp |
| 3 | 1448, 676 | natural |
| 4 | 223, 888 | flat |
| 4 | 357, 874 | sharp |
| 4 | 767, 837 | sharp |
| 5 | 254, 1044 | flat |
| 5 | 332, 1044 | natural |
| 5 | 681, 1015 | sharp |
| 5 | 1222, 1015 | sharp |
| 5 | 1371, 1022 | flat |
| 6 | 188, 1227 | sharp |
| 6 | 226, 1227 | natural |
| 6 | 328, 1236 | sharp |

## Hashes and licenses

All input fonts are OFL-1.1. Original notices and reserved names are preserved in [bench/accidental-fonts](bench/accidental-fonts), with exact URLs, SHA256 and split roles in [manifest.json](bench/accidental-fonts/manifest.json). New source/model artifacts use OFL-1.1 and the new model name AccidentalGlyphCNN. [Eugene source/license](https://github.com/mikkopatama/eugenefont) documents its original engraving style and Bravura fallbacks. No font outline or score image is bundled in the model runtime.

| Artifact | SHA256 |
|---|---|
| Allowed source PNG | `ea1960c580f0c8ea80362abc04b92a37fca8d828f9f49bf405d64c2c758a2af6` |
| Current prediction MusicXML | `1ee729f403d51ace6242d16a27de8aaea773e8ee9d6228296480e27f7bea1e16` |
| Segnet308 fp32 model | `6ed36640db4ef5d223098b6d5efe4eda97c66b24a2c72faab8a018c749003a8d` |
| Aggregate of sorted homr source-file SHA mapping | `05110ecc9f47f656e97cbdd094fbe749f54991d21c3f7ac5fa97072a7c862e02` |
| Accidental model | `c25ace36b2073aac2750dfad832aeb4b564527ff7db2e4b23459001f15411fe6` |
| Train tensor/labels/groups | `44ee1fe2d349cb9c307349fd184fca123fe6b5c4373f3e923812fe733bd4b9d8` |
| Dev tensor/labels/groups | `2cbb965765c63638d5d5b7502d3b4e6b8e319e7fcc07e5542ab260a0e067859f` |
| Eugene test tensor/labels/groups | `2e453d7b0032602b3d3349b02281e6ccd025b1c718d8930e3262476e6403f356` |
| Bravura font | `cdf0f893ee1fdb64b7f6713d71ee0dcfc349c0ac01429a8e451b01a9e79f5f3b` |
| Leipzig font | `ee0457af412610b58f7f47ebc7584e6a15fd1f752c399597e063a550959d0b31` |
| Leland font | `293788a40584b1908e3a0f219833f6a13e9a1aaf671e08fd26ad18fad2631b35` |
| Sebastian font | `661ff0227af5816ffba947e432365d7c3d42a23a28793a70b3db1eda6a3d027b` |
| NotoSans font | `bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d` |
| Eugene font | `2f969fe9788592a712be35e53783cd9443eef70a3c93174fb1d11f99ed146b92` |
| `/tmp/accidental-probe/probe.json` | `1ccce9d010903c2dfb6e836459d5dde4312ee7feb9b06956b4fe6d348e66d951` |
| `/tmp/accidental-probe/visual-labels.json` | `a498f738f05532e86138961abd867fe2c756d375eabcf5d9cb3fceaa0557e342` |
| `/tmp/accidental-probe/candidate-visual-labels.json` | `f8bb912f29f39f3f873f479e8fa118b74c3fbaef6120dba2152b2d86f8e47549` |
| `/tmp/accidental-probe/raw-cv-probe.json` | `763595861409a4675ddb92bf0be4c7c54c9321322c62fd16fa25fc5a4c2ac92a` |
| `/tmp/accidental-glyph-run/freeze.json` | `14d11c5c575fd942ce73c8fe080e2edfab926f58e19cf654c359ae316e12cc24` |
| `/tmp/accidental-glyph-run/unseen-font-test.json` | `a98682c15c6543af544731783ea2b3a2e8617d696274c06ec18ef3ad7b9ab23a` |
| `/tmp/accidental-glyph-run/runtime-parity.json` | `105c0e85952013c56ff1526238e1c04fe6f5ba2dc675330e9580bc9fa8d6df10` |
| `/tmp/accidental-glyph-run/browser-parity.json` | `2b05d739f2db691fd882d9953bf55c22e6dc5ea431c7f27ef0abe08d6561618f` |

The full receipts, contact sheets, source snapshot and detector masks remain under `/tmp/accidental-probe/`; frozen training/test/runtime receipts remain under `/tmp/accidental-glyph-run/`. Their substantive results, confusion matrix, visual inventory and hashes are preserved here. One held-out font and one allowed development score do not establish general score accuracy. Phone captures, handwriting, heavy damage, unsupported cautionary marks, double-sign recall, state propagation and polyphonic repairs remain limitations.
