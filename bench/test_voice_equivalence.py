"""Independent semantic counterexamples for MusicXML voice-label normalization."""
import copy
import itertools
import random
import unittest
import xml.etree.ElementTree as ET

from practice_metrics import compare, passes, _maximum_assignment


def duet():
    root = ET.Element('score-partwise')
    part = ET.SubElement(root, 'part', id='P1')
    for number in range(1, 3):
        measure = ET.SubElement(part, 'measure', number=str(number))
        if number == 1:
            attrs = ET.SubElement(measure, 'attributes')
            ET.SubElement(attrs, 'divisions').text = '1'
            time = ET.SubElement(attrs, 'time')
            ET.SubElement(time, 'beats').text = '4'; ET.SubElement(time, 'beat-type').text = '4'
        for voice, step, octave in [('1', 'C', '5'), ('2', 'G', '4')]:
            if voice == '2':
                ET.SubElement(ET.SubElement(measure, 'backup'), 'duration').text = '4'
            for _ in range(4):
                note = ET.SubElement(measure, 'note'); pitch = ET.SubElement(note, 'pitch')
                ET.SubElement(pitch, 'step').text = step; ET.SubElement(pitch, 'octave').text = octave
                ET.SubElement(note, 'duration').text = '1'; ET.SubElement(note, 'voice').text = voice
                ET.SubElement(note, 'staff').text = '1'
    return root


class VoiceEquivalenceTests(unittest.TestCase):
    def test_consistent_arbitrary_labels_are_not_musical_errors(self):
        truth, reading = duet(), duet()
        for node in reading.findall('.//voice'):
            node.text = {'1': 'soprano', '2': '05'}[node.text]
        report = compare(truth, reading)
        self.assertEqual(report['rawVoiceLabelEvents']['correct'], 0)
        self.assertEqual(report['events']['correct'], 16)
        self.assertTrue(passes(report, 1))

    def test_midpiece_voice_swap_cannot_be_aligned_away(self):
        truth, reading = duet(), duet()
        for node in reading.findall('part/measure')[1].findall('note/voice'):
            node.text = {'1': '2', '2': '1'}[node.text]
        report = compare(truth, reading)
        self.assertEqual(report['events']['correct'], 8)
        self.assertFalse(passes(report, .995))

    def test_voice_collapse_does_not_merge_streams_for_scoring(self):
        truth, reading = duet(), duet()
        for node in reading.findall('.//voice'):
            node.text = 'combined'
        report = compare(truth, reading)
        self.assertEqual(report['events']['correct'], 8)
        self.assertFalse(report['voiceNormalization']['labelCardinalityMatches'])
        self.assertFalse(passes(report, .995))

    def test_wrong_staff_or_pitch_or_duration_remains_wrong(self):
        for tag, replacement in [('staff', '2'), ('duration', '2'), ('pitch/step', 'D')]:
            truth, reading = duet(), duet()
            reading.find('part/measure/note/'+tag).text = replacement
            self.assertLess(compare(truth, reading)['events']['correct'], 16)

    def test_parts_are_not_reordered_to_raise_the_score(self):
        truth = duet(); other = copy.deepcopy(truth.find('part')); other.set('id', 'P2')
        for pitch in other.findall('.//pitch/step'):
            pitch.text = 'E'
        truth.append(other)
        reading = copy.deepcopy(truth); reading[:] = list(reversed(list(reading)))
        self.assertLess(compare(truth, reading)['events']['correct'], 32)

    def test_resource_limit_is_explicit_and_cannot_qualify(self):
        truth, reading = duet(), duet()
        for i in range(17):
            note = copy.deepcopy(truth.find('.//note')); note.find('voice').text = str(i+10)
            truth.find('part/measure').append(note)
            reading.find('part/measure').append(copy.deepcopy(note))
        report = compare(truth, reading)
        self.assertFalse(report['voiceNormalization']['supported'])
        self.assertIsNone(report['canonicalVoiceEvents'])
        self.assertFalse(passes(report, .995))

    def test_assignment_matches_exhaustive_small_problem(self):
        weights = [[8, 1, 2], [2, 4, 8], [4, 9, 1]]
        actual = _maximum_assignment(weights)
        value = sum(weights[i][actual[i]] for i in range(3))
        expected = max(sum(weights[i][perm[i]] for i in range(3)) for perm in itertools.permutations(range(3)))
        self.assertEqual(value, expected)

    def test_assignment_handles_ties_and_dummy_voices_against_brute_force(self):
        rng = random.Random(20261115)
        for size in range(1, 6):
            for _ in range(6):
                weights = [[rng.randrange(6) for _ in range(size)] for _ in range(size)]
                actual = _maximum_assignment(weights)
                self.assertEqual(len(set(actual)), size)
                expected = max(sum(weights[i][perm[i]] for i in range(size))
                               for perm in itertools.permutations(range(size)))
                self.assertEqual(sum(weights[i][actual[i]] for i in range(size)), expected)


if __name__ == '__main__':
    unittest.main()
