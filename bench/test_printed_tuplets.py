import copy
from fractions import Fraction
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web/src/py'))
from printed_tuplets import _templates, read_tuplet_marks, tuplet_candidates, apply_tuplet


def sample():
    root = ET.fromstring('<score-partwise><part-list><score-part id="P1"><part-name>Fixture</part-name></score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>4</divisions><time><beats>6</beats><beat-type>8</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes></measure><measure number="2"><note><rest measure="yes"/><duration>12</duration></note></measure></part></score-partwise>')
    measure = root.find('part/measure')
    for i, (duration, kind, x) in enumerate(((2, 'eighth', 100), (1, '16th', 150), (1, '16th', 200), (1, '16th', 250), (6, 'quarter', 300))):
        note = ET.SubElement(measure, 'note', id=f'n{i}-p0-{x}-120')
        pitch = ET.SubElement(note, 'pitch')
        ET.SubElement(pitch, 'step').text = 'CDEFG'[i]
        ET.SubElement(pitch, 'octave').text = '5'
        ET.SubElement(note, 'duration').text = str(duration)
        ET.SubElement(note, 'voice').text = '1'
        ET.SubElement(note, 'type').text = kind
        if duration == 6:
            ET.SubElement(note, 'dot')
        ET.SubElement(note, 'staff').text = '1'
    return root


def page(number=2):
    image = np.full((260, 400), 255, np.uint8)
    glyph = [value for digit, value in _templates() if digit == number][-1]
    glyph = cv2.resize(glyph, (16, 22), interpolation=cv2.INTER_AREA)
    image[180:202, 167:183] = np.rint((1-glyph)*255).astype(np.uint8)
    boxes = [[0, 100, 399, 160, 0]]
    return image, boxes


def sources(number=2):
    image, boxes = page(number)
    return [{'page': 0, 'layout': boxes, 'tuplets': read_tuplet_marks(image, boxes)}]


class PrintedTupletTests(unittest.TestCase):
    def test_candidate_uses_printed_digit_and_does_not_edit(self):
        root = sample()
        before = ET.tostring(root)
        found = tuplet_candidates(root, sources())
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['notes'], ['n1-p0-150-120', 'n2-p0-200-120'])
        self.assertEqual(found[0]['options'], ['tuplet-2-3', 'keep-and-review'])
        self.assertEqual(before, ET.tostring(root))

    def test_choice_refines_units_but_preserves_other_music(self):
        root = sample()
        candidate = tuplet_candidates(root, sources())[0]
        pitches = [ET.tostring(n) for n in root.findall('.//pitch')]
        apply_tuplet(root, candidate)
        self.assertEqual([ET.tostring(n) for n in root.findall('.//pitch')], pitches)
        divisions = int(root.findtext('.//divisions'))
        notes = root.findall('part/measure')[0].findall('note')
        self.assertEqual([Fraction(int(n.findtext('duration')), divisions) for n in notes], [Fraction(1, 2), Fraction(3, 8), Fraction(3, 8), Fraction(1, 4), Fraction(3, 2)])
        self.assertEqual(Fraction(int(root.findall('part/measure')[1].findtext('note/duration')), divisions), 3)
        self.assertEqual(len(root.findall('.//time-modification')), 2)
        self.assertEqual(len(root.findall('.//tuplet')), 2)
        with self.assertRaises(ValueError):
            apply_tuplet(root, candidate)

    def test_no_digit_no_guess_and_wrong_digit_no_guess(self):
        for reading in ([], sources(3)):
            self.assertEqual(tuplet_candidates(sample(), reading), [])

    def test_inside_staff_digit_is_not_used(self):
        image, boxes = page()
        image[115:137] = image[180:202]
        image[180:202] = 255
        self.assertEqual(read_tuplet_marks(image, boxes), [])

    def test_correct_bar_polyphony_pickup_and_existing_tuplet_are_left_alone(self):
        for change in ('correct', 'backup', 'chord', 'pickup', 'tuplet'):
            with self.subTest(change=change):
                root = sample()
                measure = root.find('part/measure')
                if change == 'correct':
                    measure.findall('note')[0].find('duration').text = '3'
                elif change == 'pickup':
                    measure.set('implicit', 'yes')
                elif change == 'backup':
                    ET.SubElement(measure, 'backup')
                elif change == 'chord':
                    ET.SubElement(measure.findall('note')[1], 'chord')
                else:
                    ET.SubElement(measure.findall('note')[1], 'time-modification')
                self.assertEqual(tuplet_candidates(root, sources()), [])

    def test_stale_note_or_meter_cannot_be_applied(self):
        for path, value in (('.//beats', '4'), ('.//note/duration', '3')):
            root = sample()
            candidate = tuplet_candidates(root, sources())[0]
            root.find(path).text = value
            before = ET.tostring(root)
            with self.assertRaisesRegex(ValueError, 'changed|stale'):
                apply_tuplet(root, candidate)
            self.assertEqual(before, ET.tostring(root))

    def test_decimal_offsets_are_rescaled_exactly(self):
        root = sample()
        candidate = tuplet_candidates(root, sources())[0]
        direction = ET.SubElement(root.findall('part/measure')[1], 'direction')
        offset = ET.SubElement(direction, 'offset')
        offset.text = '0.75'
        apply_tuplet(root, candidate)
        self.assertEqual(Fraction(offset.text), Fraction(3, 2))

    def test_model_triplet_guess_is_replaced_only_with_complete_group_evidence(self):
        root = sample()
        part = root.find('part')
        # Refine units, then mimic the model guessing three sixteenths as a triplet.
        for node in part.iter():
            if node.tag in ('divisions', 'duration'):
                node.text = str(int(node.text)*3)
        notes = root.find('part/measure').findall('note')
        for index, note in enumerate(notes[1:4]):
            note.find('duration').text = '2'
            tm = ET.SubElement(note, 'time-modification')
            ET.SubElement(tm, 'actual-notes').text = '3'
            ET.SubElement(tm, 'normal-notes').text = '2'
            if index != 1:
                ET.SubElement(ET.SubElement(note, 'notations'), 'tuplet', type='start' if index == 0 else 'stop')
        candidate = tuplet_candidates(root, sources())
        self.assertEqual(len(candidate), 1)
        self.assertEqual(len(candidate[0]['edits']), 3)
        apply_tuplet(root, candidate[0])
        self.assertIsNone(notes[3].find('time-modification'))
        divisions = int(root.findtext('.//divisions'))
        self.assertEqual(sum(Fraction(int(note.findtext('duration')), divisions) for note in notes), 3)

    def test_printed_five_recovers_quintuplet_and_integral_xml_units(self):
        root = sample()
        measure = root.find('part/measure')
        measure.find('attributes/time/beats').text = '2'
        measure.find('attributes/time/beat-type').text = '4'
        notes = measure.findall('note')
        for note in notes:
            note.find('duration').text = '2'
            note.find('type').text = 'eighth'
            for dot in list(note.findall('dot')):
                note.remove(dot)
        candidate = tuplet_candidates(root, sources(5))
        self.assertEqual(len(candidate), 1)
        self.assertEqual((candidate[0]['actual'], candidate[0]['normal']), (5, 4))
        apply_tuplet(root, candidate[0])
        divisions = int(root.findtext('.//divisions'))
        self.assertEqual([Fraction(int(note.findtext('duration')), divisions) for note in notes], [Fraction(2, 5)]*5)
        self.assertEqual(len(root.findall('.//tuplet')), 2)

    def test_ambiguous_printed_evidence_does_not_pick_a_winner(self):
        evidence = sources()
        evidence[0]['tuplets'].append(copy.deepcopy(evidence[0]['tuplets'][0]))
        self.assertEqual(tuplet_candidates(sample(), evidence), [])


if __name__ == '__main__':
    unittest.main()
