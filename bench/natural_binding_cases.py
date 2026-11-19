# SPDX-License-Identifier: CC0-1.0
"""Original short accidental exercises; freeze truth before any recognition.

python bench/natural_binding_cases.py OUTPUT_DIRECTORY
Then: cd web && node tools/render-natural-binding.mjs OUTPUT_DIRECTORY
No reference score, OMR output, or private source is read by this generator.
"""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def note(measure, step, octave, alter=0, accidental=None, grace=False, slur=None):
    n = ET.SubElement(measure, 'note')
    if grace:
        ET.SubElement(n, 'grace', slash='yes')
    p = ET.SubElement(n, 'pitch')
    ET.SubElement(p, 'step').text = step
    if alter:
        ET.SubElement(p, 'alter').text = str(alter)
    ET.SubElement(p, 'octave').text = str(octave)
    if not grace:
        ET.SubElement(n, 'duration').text = '4'
    ET.SubElement(n, 'voice').text = '1'
    ET.SubElement(n, 'type').text = 'eighth' if grace else 'quarter'
    if accidental:
        ET.SubElement(n, 'accidental').text = accidental
    if slur:
        ET.SubElement(ET.SubElement(n, 'notations'), 'slur', type=slur, number='1')


def exercise(name, pitch, fifths, main_alter, grace, ordinary=False):
    step, octave = pitch
    root = ET.Element('score-partwise', version='4.0')
    work = ET.SubElement(root, 'work')
    ET.SubElement(work, 'work-title').text = 'Original accidental exercise '+name
    listing = ET.SubElement(root, 'part-list')
    ET.SubElement(ET.SubElement(listing, 'score-part', id='P1'), 'part-name').text = 'Flute'
    part = ET.SubElement(root, 'part', id='P1')
    for number in range(1, 5):
        measure = ET.SubElement(part, 'measure', number=str(number))
        if number == 1:
            a = ET.SubElement(measure, 'attributes')
            ET.SubElement(a, 'divisions').text = '4'
            ET.SubElement(ET.SubElement(a, 'key'), 'fifths').text = str(fifths)
            t = ET.SubElement(a, 'time')
            ET.SubElement(t, 'beats').text = '4'
            ET.SubElement(t, 'beat-type').text = '4'
            c = ET.SubElement(a, 'clef')
            ET.SubElement(c, 'sign').text = 'G'
            ET.SubElement(c, 'line').text = '2'
        if number in (1, 4):
            # A different pitch establishes context and leaves an ordinary
            # unmarked key-signature pitch at the bar reset.
            note(measure, 'D', 5)
            for _ in range(3):
                note(measure, step, octave, 1 if fifths > 0 else -1)
        elif number == 2:
            if grace:
                note(measure, step, octave, accidental='natural', grace=True, slur='start')
                for i in range(4):
                    note(measure, step, octave, main_alter,
                         {1:'sharp', -1:'flat'}.get(main_alter) if i == 0 else None,
                         slur='stop' if i == 0 else None)
            else:
                note(measure, 'D', 5)
                for i in range(3):
                    note(measure, step, octave, accidental='natural' if i == 0 else None)
        else:
            note(measure, 'D', 5)
            note(measure, step, octave, accidental='natural')
            restore = -1 if ordinary else main_alter
            note(measure, step, octave, restore,
                 {-1:'flat', 1:'sharp'}.get(restore))
            note(measure, step, octave, restore)
    ET.indent(root)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)+b'\n'


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    cases = [
        ('grace-natural-main-sharp', ('C',5), 2, 1, True, False, 'Bravura'),
        ('grace-natural-bare-carry', ('F',4), 1, 0, True, False, 'Leipzig'),
        ('ordinary-natural-flat-reset', ('E',5), -3, 0, False, True, 'Leipzig'),
        ('grace-natural-main-flat', ('B',4), -2, -1, True, False, 'Bravura'),
    ]
    rows = []
    for name, pitch, fifths, main, grace, ordinary, font in cases:
        folder = out/name
        folder.mkdir()
        data = exercise(name, pitch, fifths, main, grace, ordinary)
        (folder/'truth.musicxml').write_bytes(data)
        rows.append({'id':name, 'font':font, 'truthSHA256':hashlib.sha256(data).hexdigest(),
                     'core':16, 'graces':int(grace)})
    frozen = {'license':'CC0-1.0', 'provenance':'original exercises authored independently of private scores',
              'generatorSHA256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'policy':'truth fixed before raster rendering or inference; never edited from output', 'cases':rows}
    (out/'truth-freeze.json').write_text(json.dumps(frozen, indent=2)+'\n')
    print(json.dumps(frozen, indent=2))


if __name__ == '__main__':
    main(sys.argv[1])
