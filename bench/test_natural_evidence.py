from pathlib import Path
import json
import sys
import unittest
import xml.etree.ElementTree as ET
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'web/src/py'))
from pipeline import _repair_natural_cancellations
from accidental_glyphs import read_accidentals


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

    def test_grace_natural_carries_to_bare_main_and_stops_at_any_explicit_sign(self):
        for kind in ('sharp', 'flat', 'double-sharp', 'double-flat', None):
            root = score()
            ET.SubElement(root.findall('.//note')[1], 'grace')
            changes = _repair_natural_cancellations(root, source([mark(), mark('n3-p0-400-80', kind)]))
            self.assertEqual([c['note'] for c in changes], ['n1-p0-200-80'])
        root = score()
        ET.SubElement(root.findall('.//note')[1], 'grace')
        changes = _repair_natural_cancellations(root, source([mark()]))
        self.assertEqual([c['note'] for c in changes], ['n1-p0-200-80', 'n3-p0-400-80'])

    def test_musicxml_accidental_ends_carry_without_reclassifying_the_pitch(self):
        root = score()
        ET.SubElement(root.findall('.//note')[3], 'accidental').text = 'sharp'
        _repair_natural_cancellations(root, source([mark()]))
        self.assertEqual(root.findall('.//note')[3].findtext('pitch/alter'), '1')

    def test_unknown_between_natural_and_head_prevents_activation(self):
        root = score()
        closer = {**mark(kind=None), 'box': [192,65,198,95], 'center': [195,80]}
        before = ET.tostring(root)
        self.assertEqual(_repair_natural_cancellations(root, source([mark(), closer])), [])
        self.assertEqual(ET.tostring(root), before)

    def test_unknown_left_of_intact_natural_does_not_hide_it(self):
        root = score()
        bar = {**mark(kind=None), 'box': [166,60,169,100], 'center': [167.5,80]}
        changes = _repair_natural_cancellations(root, source([mark(), bar]))
        self.assertEqual(len(changes), 2)

    def test_unresolved_source_head_ends_carry_and_preserves_full_output(self):
        root = score()
        inputs = source([mark()])
        inputs[0]['noteheads'] = [{'id': 'n1-p0-200-80'}]
        _repair_natural_cancellations(root, inputs)
        self.assertEqual(len(root.findall('.//note')), 5)
        self.assertEqual(root.findall('.//note')[3].findtext('pitch/alter'), '1')

    def test_other_voice_or_staff_is_not_given_another_notes_natural(self):
        for child in ('staff', 'voice'):
            root = score()
            ET.SubElement(root.findall('.//note')[3], child).text = '2'
            before = ET.tostring(root)
            self.assertEqual(_repair_natural_cancellations(root, source([mark()])), [])
            self.assertEqual(ET.tostring(root), before)

    def test_other_octave_and_another_heads_sign_are_not_borrowed(self):
        root = score()
        root.findall('.//note')[3].find('pitch/octave').text = '5'
        _repair_natural_cancellations(root, source([mark()]))
        self.assertEqual(root.findall('.//note')[3].findtext('pitch/alter'), '1')
        root = score()
        before = ET.tostring(root)
        self.assertEqual(_repair_natural_cancellations(root, source([mark('unbound-head')])), [])
        self.assertEqual(ET.tostring(root), before)

    def test_source_connected_sharp_is_unknown_blocker_but_slur_or_beam_alone_is_not(self):
        # Original CC0 line drawing. This exercises pixels -> CC extraction ->
        # bound unknown evidence -> XML, without relying on classifier labels.
        for symbol in ('sharp', 'slur-only', 'beam-only'):
            image = np.full((110,230),255,np.uint8)
            for y in (30,40,50,60,70):
                cv2.line(image,(0,y),(229,y),0,1)
            heads = [{'staff':0, 'center':[60,55], 'position':3, 'id':'grace'},
                     {'staff':0, 'center':[115,55], 'position':3, 'id':'main'}]
            for head in heads:
                cv2.ellipse(image,tuple(head['center']),(6,3),-20,0,360,0,-1)
            if symbol != 'beam-only':
                cv2.polylines(image,[np.array([[60,68],[77,77],[98,77],[112,68]])],False,0,2)
            if symbol == 'sharp':
                cv2.line(image,(91,36),(91,76),0,2)
                cv2.line(image,(99,32),(99,72),0,2)
                cv2.line(image,(86,49),(103,44),0,3)
                cv2.line(image,(86,63),(103,58),0,3)
            if symbol == 'beam-only':
                cv2.rectangle(image,(61,31),(112,36),0,-1)
            evidence = read_accidentals(image, [[0,30,230,70]], heads)
            blockers = [e for e in evidence if e.get('partial') and e['head_id']=='main']
            if symbol == 'sharp':
                self.assertTrue(blockers, evidence)
                self.assertTrue(all(e['unknown'] and e['kind'] is None for e in blockers))
                root = score()
                changes = _repair_natural_cancellations(root, source([mark(),
                    {**blockers[0], 'head_id':'n3-p0-400-80'}]))
                self.assertEqual([c['note'] for c in changes], ['n1-p0-200-80'])
            else:
                self.assertFalse(blockers, evidence)

    def test_dense_head_attribution_cannot_assert_a_borrowed_natural(self):
        image = np.full((90,120),255,np.uint8)
        for y in (20,30,40,50,60):
            cv2.line(image,(0,y),(119,y),0,1)
        cv2.line(image,(44,29),(44,62),0,2)
        cv2.line(image,(53,37),(53,70),0,2)
        cv2.line(image,(44,45),(53,41),0,3)
        cv2.line(image,(44,58),(53,54),0,3)
        heads = [{'staff':0,'center':[71,52],'position':4,'id':'a'},
                 {'staff':0,'center':[72,53],'position':4,'id':'b'}]
        evidence = read_accidentals(image,[[0,20,120,60]],heads)
        json.dumps(evidence)  # NumPy comparison booleans must not leak to the Worker audit.
        self.assertTrue(evidence)
        self.assertTrue(all(e['unknown'] and e['kind'] is None for e in evidence))


if __name__ == '__main__':
    unittest.main()
