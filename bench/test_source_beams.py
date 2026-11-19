from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web/src/py'))
from source_beams import apply_source_beams


def fixture(rest_at=40):
    return ET.fromstring(f"""
        <score-partwise><part id="P1"><measure number="1">
          <note id="n1-p0-20-40"><pitch/><duration>1</duration><type>eighth</type></note>
          <note id="n2-p0-{rest_at}-40"><rest/><duration>1</duration><type>eighth</type></note>
          <note id="n3-p0-60-40"><pitch/><duration>1</duration><type>eighth</type></note>
        </measure></part></score-partwise>
    """)


def observations():
    stems = [dict(x=x, tip=64, direction='down', heads=[dict(center=[x, 40])]) for x in (20, 60)]
    return [dict(staff=0, stems=stems, connections=[
        dict(count=1, bands=[[0, 3]], **{'from': [20, 64], 'to': [60, 64]}),
    ])]


class SourceBeamExportTests(unittest.TestCase):
    def qualify(self, score):
        return apply_source_beams(score, 0, observations(), [[0, 20, 80, 60, 0]],
                                  np.zeros((80, 80), dtype=bool))

    def test_binds_only_a_rest_under_the_source_connection(self):
        truth = fixture()
        score = fixture()
        self.assertEqual(len(self.qualify(score)), 1)
        self.assertEqual([beam.text for beam in score.findall('.//beam')], ['begin', 'continue', 'end'])
        for note in score.findall('.//note'):
            note.remove(note.find('beam'))
        self.assertEqual(ET.tostring(score), ET.tostring(truth))
        outside = fixture(16)
        self.assertEqual(self.qualify(outside), [])
        self.assertEqual(outside.findall('.//beam'), [])

    def test_preserves_explicit_beams_and_rejects_cross_voice_and_ambiguous_heads(self):
        for kind in ('explicit', 'other voice', 'two heads'):
            with self.subTest(kind=kind):
                score = fixture()
                first, last = score.findall('.//note')[::2]
                if kind == 'explicit':
                    ET.SubElement(first, 'beam', number='1').text = 'forward hook'
                elif kind == 'other voice':
                    ET.SubElement(last, 'voice').text = '2'
                else:
                    ET.SubElement(score.find('.//measure'), 'note', id='n4-p0-60-40').append(ET.Element('pitch'))
                before = ET.tostring(score)
                self.assertEqual(self.qualify(score), [])
                self.assertEqual(ET.tostring(score), before)


if __name__ == '__main__':
    unittest.main()
