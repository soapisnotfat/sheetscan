# Opening-clef initialization regression

This is a bounded reproduction for [Dripping issue #41](https://github.com/soapisnotfat/dripping/issues/41). The input is the self-authored CC0 MusicXML fixture `opening-clef-split-attributes.musicxml`, not a private PDF or a screenshot-derived transcription.

## First diverging stage

The first measure is a one-quarter pickup. Its divisions, key and meter are in one opening `attributes` element; the treble clef is in another `attributes` element before the first note. A later system repeats the treble clef, followed by a real bass-clef change in the next measure. Tempo changes from quarter = 96 to quarter = 120.

The existing `_give_every_staff_a_clef` postprocessor inspected only the first opening `attributes` element. It found no clef there, copied the already-present opening clef into that element, and left the source clef in place. The duplicate is therefore introduced during clef initialization on this fixture, before annotation or rendering.

| Item | Input fixture | Pinned baseline `9649164` | Candidate |
| --- | ---: | ---: | ---: |
| Opening pickup clefs | 1 | 2 | 1 |
| Later system courtesy clefs | 1 | 1 | 1 |
| Later genuine bass-clef changes | 1 | 1 | 1 |
| Notes | 3 | 3 | 3 |
| Tempo directions | 2 | 2 | 2 |

The repair recognizes clefs in all opening attribute elements before the first note, backup or forward. It leaves those source elements unchanged. It does not remove repeated courtesy clefs, suppress later clef changes, alter tempo marks, or disable the existing behavior that initializes a staff which first appears later in the piece.

## Regression checks

`bench/test_import_integrity.py` exercises the real pipeline helper. It verifies byte-for-byte XML preservation on the fixture, numbered staff identity, a later-entering second staff, idempotence, and conservative behavior once a musical event has begun. Run in the repository's native homr test environment:

```sh
python -m unittest discover -s bench -p 'test_import_integrity.py'
node --test web/tools/annotation.test.mjs web/tools/metadata.test.mjs
```

## Evidence boundary

This establishes a pipeline-level cause for one duplicate-opening-clef shape. It does not establish that the private screenshot follows the same path. No claim is made that a new PDF has been recognized end to end, that the duplicate-tempo report is reproduced or fixed, or that broader recognition accuracy improved. Native imported MusicXML is outside this PDF postprocessing path. Model weights and `homr.zip` do not need to change; a new browser SDK build and host pin update are required to ship the changed pipeline.
