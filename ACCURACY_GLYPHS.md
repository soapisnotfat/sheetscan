# TupletGlyphCNN: frozen synthetic-font experiment

A 70,592-byte CNN now recognizes printed tuplet digits 2, 3, 5, 6, 7 and 9 using NumPy/cv2 in the browser. On the first frozen unseen-font test it retained 98.857% of positive glyphs, rejected 99.738% of negatives, and achieved 99.688% precision among accepted detections. These are **isolated synthetic glyph results**, not score transcription accuracy. It is a candidate classifier and requires score geometry and rhythm checks.

## Interface and integration

`from tuplet_glyphs import classify_glyph` accepts a finite 2D foreground-ink crop (0..1 or 0..255), matching the tight 32x24 connected-component crop in `printed_tuplets.py`. It returns `number` (2/3/5/6/7/9 or None), `unknown`, raw-logit `score`, raw-logit `margin`, and per-class `scores`. The margin includes the learned unknown class. Scores are not calibrated probabilities; the old cosine-template threshold must not be applied to them. Runtime needs only the NumPy/cv2 packages already loaded by the worker, plus `tuplet_glyphs.py` and `tuplet_classifier.json` copied into the same Pyodide directory.

**Integration remains for the lead agent:** worker file injection, `read_tuplet_marks` wiring, true source-image candidate extraction tests, and end-to-end error/repair evaluation. The current extractor can split a staff-overlapped digit or merge it with a stem. Good scores on complete crops do not prove the extractor will produce those crops. Retain geometric uniqueness, voice, meter and exact-duration checks before automatic repair. I did not edit the pipeline, extractor, worker, or independent holdout evaluation.

## Frozen design and provenance

- Train: 23,200 samples, seed 405132; dev: 6,000 samples, seed 405133. Both use Bravura, Leipzig and Leland. 2,200 train and 500 dev samples per positive class; 10,000/3,000 negatives.
- Frozen unseen-font test: 8,400 samples, seed 405134; 700 per positive class plus 4,200 negatives. Sebastian positive glyphs and music-symbol negatives are unseen font files. NotoSans text negatives and procedural noteheads/stems use independent draws from the same source distribution, so those negative families are not an unseen-font claim.
- The split and seeds were specified in code before training. Sebastian font availability/bounding boxes were probed before training, but its test dataset, scores and metrics were first generated only after model/gates were frozen. No score images, score ground truth, independent-eval source crops, or error lists were used for training or threshold selection. Separately authorized blind human reading of unrelated source excerpts did not enter this model.
- Font input height 10..36 px, small rotation, width perturbation, sampling/blur/threshold variation. Exactly half of positive examples have staff lines added before the production-like horizontal opening and vertical closing, so coincident glyph strokes really can be erased. Other samples include limited ink dropout. Negatives include noteheads, rests, accidentals, articulations, dynamics, time digits, unsupported tuplet digits, ordinary alphanumeric text, stems/beams and primitives.
- Network: Conv(1,8,3,pad1), ReLU, maxpool2, Conv(8,16,3,pad1), ReLU, maxpool2, Linear(768,32), ReLU, Linear(32,7). 26,087 parameters stored as float16/base64; inference accumulates float32. AdamW lr .0015, weight decay .0003; batch 256, 22 epochs, weighted cross-entropy unknown=.55/others=1; torch seed 78124, 4 CPU threads. Actual training time 49.6 seconds.
- Gates were selected using dev only: maximize retained correct positives with <=0.1% dev-negative false positives per digit and <=0.5% accepted wrong-class rate per digit. This is finite-grid development selection, not a probabilistic confidence calibration. No test-based threshold changes followed.

Source and generated classifier artifacts are distributed under OFL-1.1 for this experiment; preserve the original copyright/reserved-font-name notices in [bench/tuplet-fonts](bench/tuplet-fonts). `TupletGlyphCNN` is a new model name and does not rename an upstream font. The exact font bytes, source URLs, license hashes and split roles are in [manifest.json](bench/tuplet-fonts/manifest.json). [Leland](https://github.com/MuseScoreFonts/Leland), [Leipzig](https://github.com/rism-digital/leipzig), and [Sebastian](https://github.com/fkretlow/sebastian) publish their OFL provenance. Sebastian notes that some of its glyphs derive from Bravura, so a different font file is not proof that every glyph design is independent.

## Results

| Split | Positive correct / n | Recall | Negative rejected / n | Rejection | Accepted precision |
|---|---:|---:|---:|---:|---:|
| Dev | 2992 / 3000 | 99.733% | 2997 / 3000 | 99.900% | 99.866% |
| Unseen-font test | 4152 / 4200 | 98.857% | 4189 / 4200 | 99.738% | 99.688% |

| Unseen positive condition | Correct / n | Recall |
|---|---:|---:|
| Clean | 2095 / 2100 | 99.762% |
| Staff-overlapped then line-removed | 2057 / 2100 | 97.952% |

| Negative family | Rejected / n | False accepts |
|---|---:|---:|
| Font noteheads | 537 / 537 | 0 |
| Notehead/stem primitives | 1047 / 1050 | 3 |
| Other musical symbols | 1555 / 1563 | 8 |
| Ordinary text | 1050 / 1050 | 0 |

| Digit | Test recall | Test precision | Gate minimum logit | Gate minimum margin |
|---|---:|---:|---:|---:|
| 2 | 98.286% | 100.000% | 0.0 | 4.0 |
| 3 | 97.000% | 99.853% | 0.0 | 3.0 |
| 5 | 99.857% | 99.149% | 0.0 | 0.5 |
| 6 | 99.571% | 99.429% | 0.0 | 0.5 |
| 7 | 99.000% | 100.000% | 0.0 | 0.5 |
| 9 | 99.429% | 99.713% | 0.0 | 1.5 |

Full frozen test confusion matrix, rows expected / columns predicted. Rejected detections appear in `unknown`; the matrix includes 11 accepted negatives and two accepted wrong digits.

| Expected \ predicted | unknown | 2 | 3 | 5 | 6 | 7 | 9 |
|---|---:|---:|---:|---:|---:|---:|---:|
| unknown | 4189 | 0 | 0 | 5 | 4 | 0 | 2 |
| 2 | 12 | 688 | 0 | 0 | 0 | 0 | 0 |
| 3 | 21 | 0 | 679 | 0 | 0 | 0 | 0 |
| 5 | 0 | 0 | 1 | 699 | 0 | 0 | 0 |
| 6 | 3 | 0 | 0 | 0 | 697 | 0 | 0 |
| 7 | 7 | 0 | 0 | 0 | 0 | 693 | 0 |
| 9 | 3 | 0 | 0 | 1 | 0 | 0 | 696 |

An additional comparison on the same frozen crops used the existing template bank and its original digit-2/5 thresholds: 897/1,400 correct 2/5 positives (64.071%), versus 1,387/1,400 (99.071%) with the CNN. The template bank rejected 4,197/4,200 negatives (99.929%), versus CNN 4,189/4,200 across all six positive classes. Thus the larger vocabulary and better recall have a modest measured false-positive tradeoff; the comparison does not establish end-to-end repair accuracy. The template files were not changed by this task. Reproduce this post-freeze comparison with `bench/test_tuplet_glyphs.py --run /tmp/tuplet-glyph-run --template-baseline`; the output records the exact bank SHA256.

## Actual runtime verification

- Four runtime tests passed: ink normalization including float32 one-ulp overshoot, invalid-input rejection, empty/notehead rejection, and convolution/pooling reference values.
- CPython vs the frozen torch float16 roundtrip: 128 fixed synthetic dev crops, argmax agreement 100%, max absolute logit difference 0.00002480; 0.264 ms/crop on this machine.
- **Actual headless Chrome 157 / Pyodide 314.0.7 WASM execution:** 128 identical crops, argmax agreement 100%, max absolute logit difference 0.00002289; 0.659 ms/crop. NumPy and OpenCV wheels were served locally; torch/ONNX were absent from the browser inference path.
- An initial parity test exposed a normalization bug: OpenCV area-resize sometimes produced 1+1 float32 ulp, which was incorrectly treated as byte ink. The runtime now distinguishes byte-scale input at >1.5 and clips unit ink; a regression assertion covers the case. Model weights/gates did not change.

## Reproduce

Working directory: `work/omr-research/sheetscan`. The recorded environment was Python 3.13, torch 2.15.0, NumPy 2.5.5, cv2 5.0.0, Pillow 13.0.0. Rasterization/library version differences can change dataset hashes; the run refuses font-byte drift. Development packages are not runtime dependencies.

```sh
../.copisteria-venv/bin/python bench/train_tuplet_glyphs.py prepare --fonts /tmp/tuplet-glyph-fonts --out /tmp/tuplet-glyph-run
../.copisteria-venv/bin/python bench/train_tuplet_glyphs.py train --fonts /tmp/tuplet-glyph-fonts --out /tmp/tuplet-glyph-run --epochs 22
../.copisteria-venv/bin/python bench/train_tuplet_glyphs.py test --fonts /tmp/tuplet-glyph-fonts --out /tmp/tuplet-glyph-run
../.copisteria-venv/bin/python bench/test_tuplet_glyphs.py --run /tmp/tuplet-glyph-run
```

`train` writes model JSON and `freeze.json` before any unseen test generation. `test` refuses any model whose bytes differ from the freeze receipt, and records font/data hashes and complete confusion matrices. Training tensors and optimizer-era weights are intentionally outside git.

For browser verification, place the `numpy` and `opencv-python` wheel filenames from `web/node_modules/pyodide/pyodide-lock.json` under `/tmp/tuplet-glyph-run/pyodide/`, downloaded from `https://cdn.jsdelivr.net/pyodide/v314.0.7/full/`, then run:

```sh
../.copisteria-venv/bin/python bench/test_tuplet_glyphs.py --run /tmp/tuplet-glyph-run --browser
```

This uses the installed Playwright package and `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`, starts a localhost server, and writes `browser-parity.json`. It accesses only local runtime files and the synthetic dev archive.

## Frozen evidence

| Artifact | SHA256 |
|---|---|
| Model JSON | `de92fb01f4ae749d7f9a675f1fd2228427cddb643b3f61ca96531ca40bf093b5` |
| Train tensor/labels/groups | `2aebbf2a920a0bf1888011eebb40608dd3c628c1e0c5c6478d77ce3829f15da9` |
| Dev tensor/labels/groups | `244ab95baf160e88bac4fb5c8e56901cf53c80466c844f7d0307294063bf8178` |
| Unseen-font test tensor/labels/groups | `d781839d7f1ac6070aefaa2abbda4bcf4ba1051c40f9f5582664cfc52f15050d` |
| Bravura font | `cdf0f893ee1fdb64b7f6713d71ee0dcfc349c0ac01429a8e451b01a9e79f5f3b` |
| Leipzig font | `ee0457af412610b58f7f47ebc7584e6a15fd1f752c399597e063a550959d0b31` |
| Leland font | `293788a40584b1908e3a0f219833f6a13e9a1aaf671e08fd26ad18fad2631b35` |
| Sebastian font | `661ff0227af5816ffba947e432365d7c3d42a23a28793a70b3db1eda6a3d027b` |
| NotoSans font | `bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d` |
| `/tmp/tuplet-glyph-run/freeze.json` | `beaa560de33b06cb268b633e39eda802028c9eb7cb267a4a3c9ab2caa3b7f95c` |
| `/tmp/tuplet-glyph-run/unseen-font-test.json` | `f1baebca402c91f048b5cf9bf10d1b8f379f56242cb8f966112b9a1174724534` |
| `/tmp/tuplet-glyph-run/runtime-parity.json` | `357bd56e6494fc9ac66de7ca48705183a7a11f16d23a7a7b0d44badd10f2b29f` |
| `/tmp/tuplet-glyph-run/browser-parity.json` | `3192aad28793562943b7e183e4326bb268cd25682abf794636c2a584a7ff1461` |

The full metric receipts remain at `/tmp/tuplet-glyph-run/` for this workspace; their substantive results, confusion matrix and hashes are preserved above. No source score data were copied into this experiment.

## Remaining limits

One held-out printed font is a useful stress test, not a broad repertoire benchmark. Printed/textual digits can be shape-identical; glyph classification cannot determine their musical role. Synthetic noise does not establish phone-camera, photocopy, handwritten, merged-component or badly fragmented-component performance. The browser parity test verifies classifier execution and numerical agreement, not source-image extraction. Real candidate-crop recall, false tuplet repairs, polyphonic safety and full-score pitch/rhythm fidelity remain unmeasured by this component.
