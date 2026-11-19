# Source geometry regressions

These fixtures come from self-authored CC0 development scores, not user PDFs.

- `compound-attention-regression.json`: observed homr 0.7.1 geometry from the Bravura 6/8 score (seed 41053), preserving a wrong pair-selection regression without original score pixels. The printed figure is transformed from input-image coordinates to homr's fixed 1920-pixel working width.
- `tuplet-five-beam-fragment.png`: a 150×150 grayscale crop of the Bravura piano development score (seed 41113), rendered by PDF.js at 200 dpi. It contains the fragmented 5 and adjacent staff/beam; a global 3×1 close joined them into an invalid large component. The test also removes the 5 to verify that the remaining staff/beam/stems do not manufacture a digit.

Bravura glyph notices remain in `web/public/Bravura-LICENSE.txt` and the tracked font-license directories. No private score image, audio or independent holdout item is included here.
