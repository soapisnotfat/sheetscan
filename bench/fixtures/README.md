# Source geometry regressions

These fixtures come from self-authored CC0 development scores, not user PDFs.

- `opening-clef-split-attributes.musicxml`: a self-authored pipeline-level regression with split opening attributes, a pickup, a repeated system-opening clef and a genuine later clef/tempo change. It isolates the clef-initialization stage of Dripping issue #41; it does not claim to reproduce the private screenshot's PDF recognition or duplicate-tempo cause.

- `compound-attention-regression.json`: observed homr 0.7.1 geometry from the Bravura 6/8 score (seed 41053), preserving a wrong pair-selection regression without original score pixels. The printed figure is transformed from input-image coordinates to homr's fixed 1920-pixel working width.
- `tuplet-five-beam-fragment.png`: a 150×150 grayscale crop of the Bravura piano development score (seed 41113), rendered by PDF.js at 200 dpi. It contains the fragmented 5 and adjacent staff/beam; a global 3×1 close joined them into an invalid large component. The test also removes the 5 to verify that the remaining staff/beam/stems do not manufacture a digit.
- `grace-curves.png` and `grace-curves.json` contain 111 cropped engravings and source labels for single-note grace-to-principal pairs. They include same-pitch slurs, genuine grace ties and pairs with neither mark. The CC0 exercises come from the natural-carry flute fixture with changed stem directions, pitches, grace slashes and curve types. Verovio 6.4.1 engraved them in Leipzig, Bravura and Leland. The crops come from clean Chromium SVG rasters at nominal 144, 200 and 300 dpi and include six slightly blurred copies. Anchor positions come from the rendered noteheads. See the `tuplet-fonts/` directory for the engraving font notices.

Bravura glyph notices remain in `web/public/Bravura-LICENSE.txt` and the tracked font-license directories. No private score image, audio or independent holdout item is included here.
