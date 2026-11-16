# Source coverage candidate v9

This is a quantified intermediate research candidate, not certification that
arbitrary real scores achieve 99%. The main homr weights are unchanged. Candidate
v8 remains immutable; v9 changes crop coverage and symbolic multirest binding.

## Staff crop evidence

`staff_coverage.py` sees only source pixels, the five/ten-line grid and all raw
segmented heads, including unassigned heads. A head touching/beyond the existing
crop must have plausible head dimensions and at least two short ledger lines.
The current staff must be nearer than every other staff by more than half a line
space. Ties/ambiguous ownership abstain. Expansion is bounded to 2.5 line spaces,
protects the neighbouring staff core, and retains every original crop pixel.
The recognizer still receives its fixed 256×1280 tensor; weights are identical.
No pitch, reference score, filename or expected measure content selects a crop.

On the same original browser raster of the 36-bar flat-range regression, frozen
v8 read 176/204 strict events; conditional v9 reads 204/204 natively and through
complete PDF import in Chrome. Meter, bar structure and form match. The existing
missed mid-score printed tempo remains: only initial 93 is exported, while the
source also prints 104. Thus the complete score does not yet pass metadata
qualification. This is a previous test converted to development, not blind data.

Six new source-authored CC0 full-score range regressions use Bravura/Leipzig and
160–240 dpi, with all rendered systems geometrically within page bounds. Paired
native runs use identical PNG bytes and isolated source snapshots:

| Case | Frozen v8 correct/GT | Crop-only v9 correct/GT |
|---|---:|---:|
| Monophonic high | 29/32 | 32/32 |
| Monophonic low | 31/32 | 32/32 |
| Monophonic mixed high/low | 28/32 | 32/32 |
| Grand staff inward ledger notes | 64/64 | 64/64 |
| Grand staff extreme outer range | 57/64 | 57/64 |
| Grand staff mixed extreme range | 54/64 | 54/64 |

No new errors appeared in these paired runs. The last two cases retain 17 errors
and are not successful quality results. Their crop rule abstains; actual raw
heads and source crop show the low C1 heads already fit inside the original
crop. Decoder C1→E1 errors therefore need separate model/input-context coverage,
not arbitrary crop expansion. Training-set exposure is unknown.

Artifacts: `dev-samples/diagnosis/staff-coverage-v9-prototype/` and
`dev-samples/diagnosis/staff-coverage-fresh/paired-results.json`. Each run records
source files, weights, input hashes, output hashes and strict metrics. These
ignored local paths are not included in a distributable.

## Symbolic long rests

The source-only regions implemented in `score_numbers.py` are documented in
`ACCURACY_MULTIRESTS.md`. Their geometry establishes eligibility, never a count.
A unique ordinary whole-rest decoder record can bind to a verified source region
by horizontal position and nearest physical staff. It remains one ordinary rest
until the existing local numeric OCR accepts a printed count. Only then does the
pipeline mark and expand it. Ambiguous, partial, sounding or unsupported records
abstain. Existing H-shaped model multirests retain their original path and count
when OCR rejects a reading. Key, repeat and print records are not duplicated into
inserted empty bars.

The corrected valid rests-v3 PDF was independently re-rendered to expose the
previously hidden key signature; that input correction is not a model gain. On
this same valid input frozen v8 emitted 77/80 bars and 92/316 strict events. Full
Chrome v9 import accepts source counts 4/8/17, preserves 80 bars and reads 316/316,
with meter/form/tempo all matching. The source 4 is accepted from three OCR
observations (confidence 82/82/90), not inferred from the longa glyph.

Native Tesseract and browser Tesseract.js differ: native rejected the tight
printed 4 in this input. Region coverage and accepted-count accuracy are separate;
six of 28 fresh legal rest-family browser numbers were rejected and none were
wrongly accepted. Those counts remain unknown rather than being shape-filled.

## Complete browser regressions

The four existing development PDFs run through PDF.js rasterization, Python
worker, numeric OCR and text annotation: correct/GT/predicted are
178/179/179, 166/166/166, 180/180/181 and 375/375/375. Total 899/900/901; every case
retains exact bar/meter/form and printed tempos. The extra event and isolated
pitch error remain visible. Actual PDF/raster/output hashes and qualification
reports are in `dev-samples/diagnosis/browser-v9-coverage/`.

108 Python tests pass, including source-ledger ownership at a staff midpoint,
the nearer preceding-staff low-note case, high/low source expansion, and safe
symbolic-rest binding/expansion around key and repeat changes. Default multirest
font sweeps explicitly skip if development fonts are unavailable; the documented
full sweep is opt-in. Public app/SDK builds use the reviewed asset allowlist and
exclude private PDFs, hidden local regressions and all development inputs.

New independent whole-piece testing and remaining metadata/rare-range errors
remain required. Reused tests are labelled regressions, not fresh blind evidence.
