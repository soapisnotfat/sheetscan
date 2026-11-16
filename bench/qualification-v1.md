# Qualification v1

This layer supplements `practice-v2-voice-bijection`; it does not change its event
counts or redefine prior model improvement. Reports call the previous gate the
**core gate**. `performanceGateV1Passes` adds the checks below. Neither gate alone
establishes population accuracy or complete notation fidelity.

## Musical context

Compare effective key, clef and transposition at original part/bar/staff/onset.
Declarations are inherited and redundant repeats are ignored. Key signatures are
canonical step-to-alteration maps, so traditional fifths and equivalent explicit
step/alter encodings agree; major/minor prose and the visual octave placement of
traditional signatures do not change those alterations. Clef sign, line and
clef-octave-change remain significant. Transposition compares chromatic semitones
including octave-change; optional diatonic spelling does not change sounding
pitch. No part/bar/staff rearrangement is permitted to improve the score.

Missing initial key/clef context remains unknown: this conservative layer does
not infer an agreement with a printed header. Unknown GT context cannot qualify.
Octave-specific nontraditional keys, doubled transpositions and malformed or
ambiguous context are explicitly unsupported. Missing/extra bars are separately
identified as unmatched context locations, rather than described as wrong key
values in existing bars.

## Navigation and octaves

Compare a control graph at exact musical positions for DC, DS, segno, coda,
To Coda, Fine and implied forward repeats. Explicit MusicXML sound attributes
and the bounded conventional words DC/Da Capo, DS/Dal Segno, To/Al Coda, Fine,
Segno and Coda are read. Segno/coda target tokens and XML IDs are arbitrary:
tokens resolve to their target's musical location. Consistently renaming tokens
is equivalent; a broken explicit reference is unsupported. Multiple ambiguous
targets and unfamiliar navigation wording cannot qualify. Jump iterations
(`time-only`) and numeric Fine duration are significant. Standard default jump
iterations follow MusicXML: DC/DS first pass, To Coda second pass.

Octave-shift spans compare direction, size, staff and start/end position. Their
`number` labels are only local links; consistent renaming is equivalent.
Unclosed, orphan or overlapping conflicting links are unsupported. This v1
checks the control graph; it is not a general renderer or an exhaustive nested
repeat playback simulator. Existing repeat/ending and meter comparisons remain
in the frozen core layer.

## Notation fidelity

Explicit beam elements are a separate diagnostic with the core's stable
whole-part voice-label mapping. A missing beam does not itself prove a wrong
rhythm: MusicXML permits automatic beaming, and equivalent engravings may group
beams differently. The report distinguishes explicit match, explicit difference
and omitted explicit beams with automatic beaming possible. Beams do not enter
the performance gate. Other engraving details, slurs, articulations, dynamics,
expressive playback and arbitrary prose are outside this v1 scope.

## Validation

`test_qualification_v1.py` includes the four original core blind spots (wrong
key, wrong clef, missing DC and missing beams), plus inherited/redundant context,
mid-bar changes, equivalent signature/transposition encodings, arbitrary voice
and target-label changes, broken references, repeat iteration, Fine duration,
and octave-span equivalence versus direction errors. Run with:

```
PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -m unittest discover -s bench -p 'test_qualification_v1.py'
```

These tests are authored semantic counterexamples, not recognizer training data
or evidence of a 99.5% success rate.

References: [MusicXML sound semantics](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/sound/),
[key signatures](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/key/),
[octave shifts](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/octave-shift/).
