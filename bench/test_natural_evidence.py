from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'web/src/py'))
from pipeline import _repair_natural_cancellations


def score():
    return ET.fromstring('<score-partwise><part id="P1"><measure number="1"><attributes><key><fifths>2</fifths></key></attributes>'
        '<note id="n0-p0-100-80"><pitch><step>B</step><alter>1</alter><octave>4</octave></pitch></note>'
        '<note id="n1-p0-200-80"><pitch><step>B</step><alter>1</alter><octave>4</octave></pitch></note>'
        '<note id="n2-p0-300-80"><pitch><step>C</step><alter>1</alter><octave>5</octave></pitch></note>'
        '<note id="n3-p0-400-80"><pitch><step>B</step><alter>1</alter><octave>4</octave></pitch></note></measure>'
        '<measure number="2"><note id="n4-p0-500-80"><pitch><step>B</step><alter>1</alter><octave>4</octave></pitch></note></measure></part></score-partwise>')


def mark(note='n1-p0-200-80', kind='natural', y=80):
    return {'head_id': note, 'staff': 0, 'center': [185, y], 'kind': kind,
            'unknown': kind is None, 'margin': 12, 'score': 30, 'box': [180, 65, 190, 95]}


def source(marks):
    return [{'page': 0, 'layout': [[0, 60, 600, 100]], 'accidentals': marks}]


class NaturalEvidenceTests(unittest.TestCase):
    def test_explicit_natural_updates_same_octave_carry_only_within_measure(self):
        root = score()
        changes = _repair_natural_cancellations(root, source([mark()]))
        self.assertEqual([c['note'] for c in changes], ['n1-p0-200-80', 'n3-p0-400-80'])
        self.assertEqual([n.findtext('pitch/alter', '0') for n in root.findall('.//note')], ['1', '0', '1', '0', '1'])
        self.assertEqual(root.findall('.//note')[1].findtext('accidental'), 'natural')

    def test_other_sign_or_unknown_nearby_ink_stops_carry(self):
        for kind in ('sharp', None):
            root = score()
            changes = _repair_natural_cancellations(root, source([mark(), mark('n3-p0-400-80', kind)]))
            self.assertEqual([c['note'] for c in changes], ['n1-p0-200-80'])
            self.assertEqual(root.findall('.//note')[3].findtext('pitch/alter'), '1')

    def test_unknown_wrong_vertical_position_or_key_header_never_changes_pitch(self):
        for evidence in ([], [mark(kind=None)], [mark(y=65)], [mark('n0-p0-100-80')]):
            root = score()
            before = ET.tostring(root)
            self.assertEqual(_repair_natural_cancellations(root, source(evidence)), [])
            self.assertEqual(ET.tostring(root), before)

    def test_polyphony_is_not_reinterpreted_by_single_voice_policy(self):
        root = score()
        ET.SubElement(root.find('part/measure'), 'backup')
        before = ET.tostring(root)
        self.assertEqual(_repair_natural_cancellations(root, source([mark()])), [])
        self.assertEqual(ET.tostring(root), before)


if __name__ == '__main__':
    unittest.main()
