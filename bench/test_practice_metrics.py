import copy
import unittest
import xml.etree.ElementTree as ET

from practice_metrics import compare, passes


def score():
    return ET.fromstring('''<score-partwise><part id="truth"><measure number="1">
      <attributes><divisions>4</divisions><time><beats>6</beats><beat-type>8</beat-type></time></attributes>
      <direction><direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>90</per-minute></metronome></direction-type><sound tempo="90"/></direction>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>6</duration><voice>1</voice><type>quarter</type><dot/></note>
      <note><rest/><duration>6</duration><voice>1</voice><type>quarter</type><dot/></note>
      </measure><measure number="2"><note><rest measure="yes"/><duration>12</duration></note></measure></part></score-partwise>''')


class PracticeMetricTests(unittest.TestCase):
    def test_units_ids_and_printed_numbers_do_not_change_music(self):
        a, b = score(), score()
        for element in b.iter():
            if element.tag in ('duration', 'divisions'):
                element.text = str(int(element.text)*2)
            element.attrib.pop('id', None)
        b.find('part/measure').set('number', '0')
        self.assertTrue(passes(compare(a, b), 1))

    def test_right_pitch_wrong_length_is_not_a_correct_event(self):
        a, b = score(), score()
        b.find('.//note/duration').text = '3'
        report = compare(a, b)
        self.assertEqual(report['attackPitchDiagnostic']['f1'], 1)
        self.assertLess(report['events']['f1'], 1)
        self.assertFalse(passes(report, .995))

    def test_deleted_silent_bar_is_not_aligned_away(self):
        a, b = score(), score()
        b.find('part').remove(b.findall('part/measure')[1])
        report = compare(a, b)
        self.assertFalse(report['structureMatches'])
        self.assertEqual(report['rests']['missing'], 1)

    def test_wrong_tie_and_tuplet_are_counted(self):
        for decoration in ('<tie type="start"/>', '<time-modification><actual-notes>2</actual-notes><normal-notes>3</normal-notes></time-modification>'):
            with self.subTest(decoration=decoration):
                a, b = score(), score()
                b.find('.//note').append(ET.fromstring(decoration))
                self.assertLess(compare(a, b)['events']['f1'], 1)

    def test_wrong_meter_or_tempo_fails_even_with_correct_notes(self):
        for path, value in (('.//beats', '3'), ('.//beat-type', '4')):
            a, b = score(), score()
            b.find(path).text = value
            self.assertFalse(passes(compare(a, b), .995))
        a, b = score(), score()
        b.find('.//sound').set('tempo', '120')
        self.assertFalse(passes(compare(a, b), .995))

    def test_deleted_or_added_grace_is_visible(self):
        a, b = score(), score()
        grace = copy.deepcopy(b.find('.//note'))
        grace.insert(0, ET.Element('grace'))
        grace.remove(grace.find('duration'))
        b.find('part/measure').append(grace)
        report = compare(a, b)
        self.assertEqual(report['graces']['extra'], 1)
        self.assertFalse(passes(report, .995))

    def test_invisible_padding_and_playback_only_tempo_are_not_pdf_errors(self):
        a, b = score(), score()
        padding = ET.SubElement(a.findall('part/measure')[-1], 'note', {'print-object': 'no'})
        ET.SubElement(padding, 'rest')
        ET.SubElement(padding, 'duration').text = '4'
        direction = a.find('part/measure/direction')
        direction.remove(direction.find('direction-type'))
        b.find('part/measure').remove(b.find('part/measure/direction'))
        report = compare(a, b)
        self.assertTrue(passes(report, 1))
        self.assertFalse(report['truthHasTempo'])
        self.assertEqual(report['unobservableInPdf']['truthHiddenEvents'], 1)

    def test_missing_repeat_fails_even_when_written_notes_match(self):
        a, b = score(), score()
        bar = ET.SubElement(a.findall('part/measure')[-1], 'barline', location='right')
        ET.SubElement(bar, 'repeat', direction='backward')
        report = compare(a, b)
        self.assertEqual(report['events']['f1'], 1)
        self.assertFalse(report['formMatches'])
        self.assertFalse(passes(report, .995))

    def test_empty_or_unsupported_scores_cannot_pass(self):
        for xml in ('<score-partwise/>', '<score-timewise/>', '<not-music/>'):
            with self.assertRaises(ValueError):
                compare(ET.fromstring(xml), ET.fromstring(xml))
        empty = ET.fromstring('<score-partwise><part id="P1"><measure/></part></score-partwise>')
        self.assertFalse(passes(compare(empty, empty), .995))


if __name__ == '__main__':
    unittest.main()
