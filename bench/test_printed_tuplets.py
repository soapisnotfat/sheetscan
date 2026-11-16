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

    def test_inside_staff_digit_is_read_across_a_staff_line(self):
        image, boxes = page()
        # A complete Bravura figure remains supported after line removal.
        glyph = next(value for digit, value in _templates() if digit == 2)
        image[180:202, 167:183] = np.rint((1-cv2.resize(glyph, (16, 22), interpolation=cv2.INTER_AREA))*255).astype(np.uint8)
        image[115:137] = image[180:202]
        image[180:202] = 255
        for y in (100, 115, 130, 145, 160):
            image[y:y+1, :] = 0
        self.assertEqual([mark['number'] for mark in read_tuplet_marks(image, boxes)], [2])

    def test_ambiguous_small_line_erased_digit_is_rejected(self):
        # The frozen model abstains on this damaged small Leipzig 2. Do not
        # lower its gate merely because a fixture supplies the expected label.
        image, boxes = page()
        image[115:137] = image[180:202]
        image[180:202] = 255
        for y in (100, 115, 130, 145, 160):
            image[y:y+1, :] = 0
        self.assertEqual(read_tuplet_marks(image, boxes), [])

    def test_notehead_with_stem_is_not_a_numeric_figure(self):
        image = np.full((260, 400), 255, np.uint8)
        cv2.ellipse(image, (175, 126), (9, 6), -20, 0, 360, 0, -1)
        cv2.line(image, (183, 125), (183, 102), 0, 2)
        for y in (100, 115, 130, 145, 160):
            image[y:y+1, :] = 0
        self.assertEqual(read_tuplet_marks(image, [[0, 100, 399, 160, 0]]), [])

    def test_digit_inside_a_multidigit_tempo_is_not_a_tuplet_figure(self):
        image, boxes = page(3)
        # A separate 1 and 0 flank the music-font 3, as in tempo 130. They are
        # raw ink neighbours even though neither is an accepted tuplet class.
        cv2.line(image, (160, 180), (160, 201), 0, 5)
        cv2.ellipse(image, (196, 191), (6, 10), 0, 0, 360, 0, 2)
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

    def test_quintuplet_can_be_wrong_even_when_bar_total_is_correct(self):
        root = sample()
        measure = root.find('part/measure')
        measure.find('attributes/divisions').text = '24'
        measure.find('attributes/time/beats').text = '2'
        measure.find('attributes/time/beat-type').text = '4'
        notes = measure.findall('note')
        for i, note in enumerate(notes):
            note.find('duration').text = '12' if i < 2 else '8'
            note.find('type').text = 'eighth'
            for dot in list(note.findall('dot')):
                note.remove(dot)
            if i >= 2:
                tm = ET.SubElement(note, 'time-modification')
                ET.SubElement(tm, 'actual-notes').text = '3'
                ET.SubElement(tm, 'normal-notes').text = '2'
                if i in (2, 4):
                    ET.SubElement(ET.SubElement(note, 'notations'), 'tuplet', type='start' if i == 2 else 'stop')
        found = tuplet_candidates(root, sources(5))
        self.assertEqual(len(found), 1)
        apply_tuplet(root, found[0])
        divisions = int(root.findtext('.//divisions'))
        self.assertEqual([Fraction(int(note.findtext('duration')), divisions) for note in notes], [Fraction(2, 5)]*5)

    def polyphonic_sample(self):
        root = sample()
        measure = root.find('part/measure')
        attrs = measure.find('attributes')
        attrs.find('divisions').text = '12'
        attrs.find('time/beats').text = '4'
        attrs.find('time/beat-type').text = '4'
        right = measure.findall('note')
        for i, note in enumerate(right):
            note.find('duration').text = '4'
            note.find('type').text = 'eighth'
            for dot in list(note.findall('dot')):
                note.remove(dot)
            tm = ET.SubElement(note, 'time-modification')
            ET.SubElement(tm, 'actual-notes').text = '3'
            ET.SubElement(tm, 'normal-notes').text = '2'
            if i in (0, 2, 3, 4):
                ET.SubElement(ET.SubElement(note, 'notations'), 'tuplet', type='start' if i in (0, 3) else 'stop')
        for i, duration in enumerate((12, 4, 6)):
            note = copy.deepcopy(right[4])
            note.set('id', f'tail{i}-p0-{350+i*40}-120')
            note.find('duration').text = str(duration)
            note.find('type').text = 'quarter' if i == 0 else 'eighth'
            note.remove(note.find('time-modification'))
            note.remove(note.find('notations'))
            if i == 1:
                tm = ET.SubElement(note, 'time-modification')
                ET.SubElement(tm, 'actual-notes').text = '3'
                ET.SubElement(tm, 'normal-notes').text = '2'
                notation = ET.SubElement(note, 'notations')
                ET.SubElement(notation, 'tuplet', type='start')
                ET.SubElement(notation, 'tuplet', type='stop')
            right.append(note)
        left = []
        for i in range(4):
            note = copy.deepcopy(right[-1])
            note.set('id', f'bass{i}-p0-{100+i*100}-240')
            note.find('voice').text = '5'
            note.find('staff').text = '2'
            note.find('duration').text = '12'
            note.find('type').text = 'quarter'
            left.append(note)
        # Interleaved export before repair, as emitted by homr.
        measure[:] = [attrs, *left[:1]]
        backup = ET.SubElement(measure, 'backup')
        ET.SubElement(backup, 'duration').text = '12'
        measure.extend([*right[:3], left[1], *right[3:5], left[2]])
        backup = ET.SubElement(measure, 'backup')
        ET.SubElement(backup, 'duration').text = '12'
        measure.extend([right[5], left[3]])
        backup = ET.SubElement(measure, 'backup')
        ET.SubElement(backup, 'duration').text = '12'
        measure.extend(right[6:])
        return root

    def test_polyphonic_printed_group_rebuilds_both_voice_timelines(self):
        from practice_metrics import read
        root = self.polyphonic_sample()
        pitches = [ET.tostring(n) for n in root.findall('.//pitch')]
        found = tuplet_candidates(root, sources(5))
        self.assertEqual(len(found), 1)
        self.assertEqual(len(found[0]['edits']), 6)
        apply_tuplet(root, found[0])
        events = read(root)['events']
        bass = sorted(e[4] for e in events if e[1] == 0 and e[2] == '5')
        self.assertEqual(bass, [0, 1, 2, 3])
        treble = sorted((e[4], e[5]) for e in events if e[1] == 0 and e[2] == '1')
        self.assertEqual(treble, [(Fraction(i*2, 5), Fraction(2, 5)) for i in range(5)]+[(2, 1), (3, Fraction(1, 2)), (Fraction(7, 2), Fraction(1, 2))])
        self.assertCountEqual([ET.tostring(n) for n in root.findall('.//pitch')], pitches)

    def test_polyphonic_ambiguous_or_unsupported_timing_is_not_rebuilt(self):
        for change in ('other-voice-short', 'direction', 'forward', 'chord', 'missing-evidence'):
            root = self.polyphonic_sample()
            measure = root.find('part/measure')
            evidence = sources(5)
            if change == 'other-voice-short':
                measure.find('note/duration').text = '6'
            elif change == 'chord':
                ET.SubElement(measure.find('note'), 'chord')
            elif change == 'missing-evidence':
                evidence = []
            else:
                ET.SubElement(measure, change)
            before = ET.tostring(root)
            self.assertEqual(tuplet_candidates(root, evidence), [], change)
            self.assertEqual(ET.tostring(root), before)

    def test_polyphonic_candidate_rejects_a_changed_voice_before_any_edit(self):
        root = self.polyphonic_sample()
        found = tuplet_candidates(root, sources(5))[0]
        root.find('part/measure/note/voice').text = '9'
        before = ET.tostring(root)
        with self.assertRaisesRegex(ValueError, 'voices have changed'):
            apply_tuplet(root, found)
        self.assertEqual(ET.tostring(root), before)

    def test_printed_triplet_restores_voice_time_without_shifting_bass(self):
        from practice_metrics import read
        root = self.polyphonic_sample()
        measure = root.find('part/measure')
        bass = [n for n in measure.findall('note') if n.findtext('voice') == '5']
        right = [n for n in measure.findall('note') if n.findtext('voice') == '1']
        right = [*right[:3], right[5], right[7]]
        for i, note in enumerate(right):
            note.find('duration').text = str(6 if i < 3 else 12 if i == 3 else 24)
            note.find('type').text = 'eighth' if i < 3 else 'quarter' if i == 3 else 'half'
            for item in list(note.findall('time-modification'))+list(note.findall('notations')):
                note.remove(item)
        measure[:] = [measure.find('attributes'), *right]
        backup = ET.SubElement(measure, 'backup')
        ET.SubElement(backup, 'duration').text = '54'
        measure.extend(bass)
        found = tuplet_candidates(root, sources(3))
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]['actual'], found[0]['normal']), (3, 2))
        apply_tuplet(root, found[0])
        events = read(root)['events']
        self.assertEqual(sorted(e[4] for e in events if e[1] == 0 and e[2] == '5'), [0, 1, 2, 3])
        treble = sorted((e[4], e[5]) for e in events if e[1] == 0 and e[2] == '1')
        self.assertEqual(treble, [(0, Fraction(1, 3)), (Fraction(1, 3), Fraction(1, 3)),
                                 (Fraction(2, 3), Fraction(1, 3)), (1, 1), (2, 2)])


if __name__ == '__main__':
    unittest.main()
