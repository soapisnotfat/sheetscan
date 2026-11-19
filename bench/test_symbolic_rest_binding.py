"""Whole-rest promotion requires source geometry plus an actual number reading."""
from pathlib import Path
import json
import sys
import unittest
import xml.etree.ElementTree as E
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web/src/py'))
import pipeline


def score():
    return E.fromstring('''<score-partwise><identification><miscellaneous><miscellaneous-field name="numeric-sources">[]</miscellaneous-field><miscellaneous-field name="conversion-audit">{}</miscellaneous-field></miscellaneous></identification><part id="P1"><measure number="1"><attributes><divisions>60</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes><note id="r-p0-200-80"><rest/><duration>240</duration><voice>1</voice><type>whole</type><staff>1</staff></note></measure><measure number="2"><attributes><key><fifths>1</fifths></key></attributes><barline location="left"><repeat direction="forward"/></barline><note id="n-p0-300-120"><pitch><step>C</step><octave>5</octave></pitch><duration>240</duration><type>whole</type></note></measure></part></score-partwise>''')


def bind(root):
    return pipeline._bind_symbolic_rest_sources(root,[[10,100,390,140]],
        [{'staff':0,'shapeBox':[196,110,204,130],'style':'longa','numberBox':[190,65,210,90]}],[],0)


class SymbolicRestBindingTests(unittest.TestCase):
    def test_count_is_not_inferred_from_longa_shape(self):
        root=score();before=E.tostring(root)
        sources=bind(root)
        self.assertEqual(sources[0]['count'],1)
        self.assertEqual(E.tostring(root),before)
        self.assertIsNone(root.find('.//multiple-rest'))

    def test_read_number_expands_before_key_and_repeat_without_duplicating_them(self):
        root=score();sources=bind(root)
        root.find('.//miscellaneous-field[@name="numeric-sources"]').text=json.dumps(sources)
        result=E.fromstring(pipeline.repair_rest_counts_xml(E.tostring(root),json.dumps([{'sourceId':'r-p0-200-80','count':4,'reading':{'value':4}}])))
        bars=result.findall('part/measure')
        self.assertEqual(len(bars),5)
        self.assertEqual([m.get('number') for m in bars],['1','2','3','4','5'])
        self.assertTrue(all(m.find('note/rest').get('measure')=='yes' for m in bars[:4]))
        self.assertEqual(bars[-1].findtext('attributes/key/fifths'),'1')
        self.assertEqual(len(result.findall('.//repeat')),1)
        self.assertIsNotNone(bars[-1].find('barline/repeat'))
        self.assertEqual(result.findtext('.//multiple-rest'),'4')
        self.assertEqual(len(result.findall('.//note[@id]')),2)

    def test_no_source_evidence_cannot_promote(self):
        root=score()
        with self.assertRaises(ValueError):pipeline.repair_rest_counts_xml(E.tostring(root),'[{"sourceId":"r-p0-200-80","count":4}]')

    def test_sounding_or_partial_rest_cannot_bind(self):
        root=score();note=root.find('part/measure/note');note.find('type').text='quarter'
        self.assertEqual(bind(root),[])
        note.find('type').text='whole';E.SubElement(root.find('part/measure'),'note').append(E.Element('pitch'))
        self.assertEqual(bind(root),[])

    def test_ambiguous_two_whole_rests_cannot_bind(self):
        root=score();root.find('part').append(E.fromstring('<measure><note id="other-p0-201-80"><rest/><duration>240</duration><type>whole</type></note></measure>'))
        self.assertEqual(bind(root),[])


if __name__=='__main__':unittest.main()
