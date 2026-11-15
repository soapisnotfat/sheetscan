"""Generate a self-authored notation challenge with exact, non-OMR ground truth.

    python bench/make_practice_case.py [output-directory]

Not a representative accuracy corpus. All melody content here is newly generated
and dedicated to CC0; code remains under the repository's AGPL-3.0 license.
Render this XML to PDF with web/tools/render-practice-case.mjs, then recognize the
PDF raster. Never use a recognizer output as its own ground truth.
"""
from fractions import Fraction
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

D = 120


def el(parent, name, text=None, **attributes):
    node = ET.SubElement(parent, name, attributes)
    if text is not None:
        node.text = str(text)
    return node


def note(measure, step, duration, kind, *, alter=None, dot=False, grace=False, ratio=None, mark=None, tie=None):
    n = el(measure, 'note')
    if grace:
        el(n, 'grace', slash='yes')
    if step is None:
        el(n, 'rest')
    else:
        p = el(n, 'pitch')
        el(p, 'step', step)
        if alter is not None:
            el(p, 'alter', alter)
        el(p, 'octave', 5)
    if not grace:
        units = Fraction(duration)*D
        assert units.denominator == 1
        el(n, 'duration', units.numerator)
    if tie:
        el(n, 'tie', type=tie)
    el(n, 'voice', 1)
    el(n, 'type', kind)
    if dot:
        el(n, 'dot')
    if alter is not None:
        el(n, 'accidental', {0: 'natural', 1: 'sharp', -1: 'flat'}[alter])
    if ratio:
        tm = el(n, 'time-modification')
        el(tm, 'actual-notes', ratio[0])
        el(tm, 'normal-notes', ratio[1])
    if tie or mark:
        ns = el(n, 'notations')
        if tie:
            el(ns, 'tied', type=tie)
        if mark:
            el(ns, 'tuplet', type=mark, number='1')
    return n


def fixture():
    root = ET.Element('score-partwise', version='4.0')
    el(el(root, 'work'), 'work-title', 'Practice recognition challenge')
    el(el(root, 'identification'), 'rights', 'Self-authored test melody, CC0')
    p = el(el(root, 'part-list'), 'score-part', id='P1')
    el(p, 'part-name', 'Saxophone')
    part = el(root, 'part', id='P1')

    def bar(number, meter=None, tempo=None):
        m = el(part, 'measure', number=str(number))
        if meter:
            a = el(m, 'attributes')
            if number == 1:
                el(a, 'divisions', D)
                el(el(a, 'key'), 'fifths', 0)
            t = el(a, 'time'); el(t, 'beats', meter[0]); el(t, 'beat-type', meter[1])
            if number == 1:
                c = el(a, 'clef'); el(c, 'sign', 'G'); el(c, 'line', 2)
        if tempo:
            direction = el(m, 'direction', placement='above')
            met = el(el(direction, 'direction-type'), 'metronome')
            el(met, 'beat-unit', 'quarter'); el(met, 'per-minute', tempo)
            el(direction, 'sound', tempo=str(tempo))
        return m

    m = bar(1, (6, 8), 88)
    note(m, 'C', '3/2', 'quarter', dot=True)
    for pitch in 'DEF': note(m, pitch, '1/2', 'eighth')
    m = bar(2)
    note(m, 'G', '1/2', 'eighth')
    note(m, 'A', 0, 'eighth', grace=True)
    note(m, 'B', '3/8', '16th', ratio=(2, 3), mark='start')
    note(m, 'A', '3/8', '16th', ratio=(2, 3), mark='stop')
    note(m, 'G', '1/4', '16th')
    note(m, 'F', '3/2', 'quarter', dot=True)
    m = bar(3)
    for i, pitch in enumerate('CDE'):
        note(m, pitch, '1/3', 'eighth', ratio=(3, 2), mark='start' if i == 0 else 'stop' if i == 2 else None)
    for pitch in 'FGAB': note(m, pitch, '1/2', 'eighth')
    m = bar(4)
    note(m, 'A', '3/2', 'quarter', dot=True)
    note(m, 'G', '3/2', 'quarter', dot=True, tie='start')
    m = bar(5, (2, 4), 104)
    note(m, 'G', 1, 'quarter', tie='stop')
    note(m, 'F', '1/2', 'eighth', alter=1)
    note(m, 'F', '1/2', 'eighth', alter=0)
    m = bar(6, (4, 4))
    note(m, None, 1, 'quarter'); note(m, 'E', 3, 'half', dot=True)
    for number in range(7, 18):
        m = bar(number)
        if number == 7:
            el(el(el(m, 'attributes'), 'measure-style'), 'multiple-rest', 11)
        n = el(m, 'note'); el(n, 'rest', measure='yes'); el(n, 'duration', D*4)
    m = bar(18, (3, 8))
    for pitch in 'CDEFGA': note(m, pitch, '1/4', '16th')
    m = bar(19, (2, 4))
    for i, pitch in enumerate('GAFED'):
        note(m, pitch, '2/5', 'eighth', ratio=(5, 4), mark='start' if i == 0 else 'stop' if i == 4 else None)
    m = bar(20, (4, 4))
    el(el(m, 'barline', location='left'), 'repeat', direction='forward')
    for pitch in 'CDEG': note(m, pitch, 1, 'quarter')
    m = bar(21)
    note(m, 'C', 4, 'whole')
    el(el(m, 'barline', location='right'), 'repeat', direction='backward', times='2')
    return root


if __name__ == '__main__':
    output = Path(sys.argv[1] if len(sys.argv) > 1 else 'dev-samples/accuracy/challenge')
    output.mkdir(parents=True, exist_ok=True)
    path = output/'truth.musicxml'
    ET.ElementTree(fixture()).write(path, encoding='utf-8', xml_declaration=True)
    (output/'case.json').write_text(json.dumps({'id': 'practice-challenge', 'truth': 'truth.musicxml',
        'origin': 'self-authored-CC0', 'features': ['6/8', 'duplet-2:3', 'triplet-3:2', 'quintuplet-5:4',
        'grace', 'tie', 'accidental-reset', 'meter-change', 'tempo-change', '11-bar-rest', 'repeat'],
        'role': 'development challenge, not a held-out accuracy corpus'}, indent=2)+'\n')
    print(path)
