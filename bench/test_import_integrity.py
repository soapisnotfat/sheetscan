import sys
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from types import SimpleNamespace as Obj
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web/src/py'))
import pipeline
from audit_score import audit
from unittest.mock import patch


def score(parts=1, notes=1):
    root = ET.fromstring('<score-partwise><part-list/></score-partwise>')
    for i in range(parts):
        part = ET.SubElement(root, 'part', id=f'P{i+1}')
        measure = ET.SubElement(part, 'measure', number='1')
        for _ in range(notes):
            ET.SubElement(ET.SubElement(measure, 'note'), 'rest')
    return root


class IntegrityTests(unittest.TestCase):
    def test_octave_clef_ignores_the_measure_number_at_system_start(self):
        staff = Obj(grid=[Obj(x=24, y=[64, 80, 96, 112, 128])])
        for name, x, expected in (('measure number', 30, 'C4'), ('clef digit', 67, 'C5')):
            with self.subTest(name=name):
                image = np.full((144, 128), 255, dtype=np.uint8)
                # Two counters in one printed digit. The measure number has the
                # same shape and height as the digit over the upper clef loop.
                image[25:47, x-5:x+6] = 0
                image[28:33, x-2:x+3] = 255
                image[37:43, x-3:x+4] = 255
                clef = Obj(rhythm='clef_G2', position='upper')
                note = Obj(rhythm='note_quarter', pitch='C4', position='upper')
                pipeline._mark_octave_clefs(image, staff, [clef, note], {})
                self.assertEqual(note.pitch, expected)

    def test_split_opening_attributes_do_not_duplicate_the_clef(self):
        fixture = Path(__file__).parent / 'fixtures/opening-clef-split-attributes.musicxml'
        root = ET.parse(fixture).getroot()
        before = ET.tostring(root)
        pipeline._give_every_staff_a_clef(root)
        self.assertEqual(ET.tostring(root), before)
        self.assertEqual(len(root.find('part/measure').findall('attributes/clef')), 1)
        self.assertEqual(len(root.findall('.//clef')), 3)
        self.assertEqual([node.get('tempo') for node in root.findall('.//sound')], ['96', '120'])
        self.assertIsNotNone(root.find('part/measure[@number="1"]/print'))

    def test_numbered_opening_clef_in_later_attributes_is_already_present(self):
        root = ET.fromstring('<score-partwise><part><measure><attributes><divisions>1</divisions></attributes>'
          '<direction><direction-type><words>Andante</words></direction-type></direction>'
          '<attributes><clef number="1"><sign>G</sign><line>2</line></clef></attributes>'
          '<note><rest/><duration>1</duration></note></measure></part></score-partwise>')
        before = ET.tostring(root)
        pipeline._give_every_staff_a_clef(root)
        self.assertEqual(ET.tostring(root), before)

    def test_later_entering_staff_still_gets_an_initial_clef_without_removing_source(self):
        root = ET.fromstring('<score-partwise><part><measure number="1"><attributes><divisions>1</divisions>'
          '<staves>2</staves><clef number="1"><sign>G</sign><line>2</line></clef></attributes>'
          '<note><rest/><duration>4</duration><staff>1</staff></note></measure>'
          '<measure number="2"><print new-system="yes"/><attributes><clef number="2"><sign>F</sign>'
          '<line>4</line></clef></attributes><note><rest/><duration>4</duration><staff>2</staff></note>'
          '</measure></part></score-partwise>')
        source_clef = ET.tostring(root.find('part/measure[@number="2"]/attributes/clef'))
        pipeline._give_every_staff_a_clef(root)
        first = root.find('part/measure/attributes')
        self.assertEqual([clef.get('number') for clef in first.findall('clef')], ['1', '2'])
        self.assertEqual(ET.tostring(root.find('part/measure[@number="2"]/attributes/clef')), source_clef)
        self.assertEqual(len(root.findall('.//clef')), 3)
        before = ET.tostring(root)
        pipeline._give_every_staff_a_clef(root)
        self.assertEqual(ET.tostring(root), before)

    def test_clef_after_a_musical_event_keeps_the_existing_initialization_behavior(self):
        root = ET.fromstring('<score-partwise><part><measure><attributes><divisions>1</divisions></attributes>'
          '<note><rest/><duration>1</duration></note><attributes><clef><sign>F</sign><line>4</line></clef>'
          '</attributes><note><rest/><duration>1</duration></note></measure></part></score-partwise>')
        pipeline._give_every_staff_a_clef(root)
        self.assertEqual(len(root.findall('.//clef')), 2)
        self.assertEqual(root.findtext('part/measure/attributes/clef/sign'), 'F')

    def test_repeat_line_break_does_not_create_a_musical_bar(self):
        root = ET.fromstring('<score-partwise><part id="P1"><measure number="1"><note><rest/></note></measure>'
          '<measure number="2"><print new-system="yes"/><attributes><time><beats>3</beats><beat-type>8</beat-type></time></attributes></measure>'
          '<measure number="3"><barline location="left"><repeat direction="forward"/></barline><note><rest/></note></measure></part></score-partwise>')
        self.assertEqual(len(pipeline._remove_repeat_layout_placeholders(root)), 1)
        measures = root.findall('part/measure')
        self.assertEqual([m.get('number') for m in measures], ['1', '2'])
        self.assertEqual(measures[1].findtext('attributes/time/beats'), '3')
        self.assertIsNotNone(measures[1].find('print'))
        self.assertEqual(len(root.findall('.//note')), 2)

    def test_page_opening_repeat_keeps_the_header_in_the_first_musical_bar(self):
        header = ('<attributes><divisions>4</divisions><time><beats>2</beats>'
                  '<beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line>'
                  '</clef></attributes>')
        opening = '<barline location="left"><repeat direction="forward"/></barline>'
        notes = '<note><rest/><duration>8</duration></note>'
        for name, first_contents, musical_bar, removed in (
            ('layout', '', opening + notes, True),
            ('rest', notes, opening + notes, False),
            ('late repeat', '', notes + opening, False),
        ):
            with self.subTest(name=name):
                root = ET.fromstring('<score-partwise><part id="P1"><measure number="1">'
                    + header + first_contents + '</measure><measure number="2">'
                    + musical_bar + '</measure></part></score-partwise>')
                before = ET.tostring(root)
                changes = pipeline._remove_repeat_layout_placeholders(root)
                if not removed:
                    self.assertEqual(changes, [])
                    self.assertEqual(ET.tostring(root), before)
                    continue
                self.assertEqual(len(changes), 1)
                self.assertEqual(len(root.findall('.//measure')), 1)
                first = root.find('part/measure')
                self.assertEqual(first.findtext('attributes/divisions'), '4')
                self.assertIsNotNone(first.find('note/rest'))
                self.assertIsNotNone(root.find('.//repeat[@direction="forward"]'))

    def test_repeat_repair_preserves_real_rests_directions_and_multirests(self):
        for contents in ('<note><rest/></note>', '<direction/>', '<forward><duration>4</duration></forward>',
                         '<attributes><measure-style><multiple-rest>4</multiple-rest></measure-style></attributes>'):
            root = ET.fromstring('<score-partwise><part><measure><print new-system="yes"/>'+contents+
              '</measure><measure><barline><repeat direction="forward"/></barline><note><rest/></note></measure></part></score-partwise>')
            before = ET.tostring(root)
            self.assertEqual(pipeline._remove_repeat_layout_placeholders(root), [])
            self.assertEqual(ET.tostring(root), before)

    def test_forward_repeat_before_notes_is_left_side(self):
        root = ET.fromstring('<score-partwise><part id="P1"><measure><attributes/><barline location="right"><repeat direction="forward"/></barline><note><rest/></note></measure></part></score-partwise>')
        self.assertEqual(len(pipeline._repair_forward_repeat_locations(root)), 1)
        self.assertEqual(root.find('.//barline').get('location'), 'left')

    def test_right_side_repeat_after_notes_is_not_reinterpreted(self):
        root = ET.fromstring('<score-partwise><part id="P1"><measure><note><rest/></note><barline location="right"><repeat direction="forward"/></barline></measure></part></score-partwise>')
        self.assertEqual(pipeline._repair_forward_repeat_locations(root), [])
        self.assertEqual(root.find('.//barline').get('location'), 'right')

    def test_multiple_attributes_are_read_in_order(self):
        root = ET.fromstring('<score-partwise><part id="P1"><measure number="1">'
          '<attributes><divisions>2</divisions></attributes>'
          '<attributes><time><beats>6</beats><beat-type>8</beat-type></time></attributes>'
          '<note><rest/><duration>6</duration></note></measure></part></score-partwise>')
        result = audit(root)[0]
        self.assertEqual(result['meters'], [[1, 6, 8]])
        self.assertEqual(result['durationFlags'], [])

    def test_missing_meter_is_unknown(self):
        self.assertIsNone(audit(score())[0]['durationFlags'][0]['expectedQ'])

    def test_divisions_change_after_first_attributes(self):
        root = ET.fromstring('<score-partwise><part id="P1"><measure>'
          '<attributes><divisions>1</divisions></attributes>'
          '<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>'
          '<note><rest/><duration>16</duration></note></measure></part></score-partwise>')
        self.assertEqual(audit(root)[0]['durationFlags'], [])

    def test_merge_retains_every_part_and_note(self):
        a, b = score(2, 2), score(2, 3)
        result = pipeline._merge_pages([a, b])
        self.assertEqual([len(p.findall('.//note')) for p in result.findall('part')], [5, 5])
        self.assertEqual([m.get('number') for m in result.findall('part')[0].findall('measure')], ['1', '2'])
        self.assertEqual(len(a.findall('part')[0].findall('measure')), 1)

    def test_merge_rejects_added_or_missing_parts(self):
        for pages in ([score(1), score(2)], [score(2), score(1)]):
            with self.assertRaisesRegex(ValueError, 'Part structure'):
                pipeline._merge_pages(pages)

    def test_merge_retains_page_attributes(self):
        a, b = score(), score()
        for root, beat_type in [(a, '8'), (b, '4')]:
            attrs = ET.SubElement(root.find('part/measure'), 'attributes')
            ET.SubElement(ET.SubElement(attrs, 'time'), 'beat-type').text = beat_type
        result = pipeline._merge_pages([a, b])
        self.assertEqual([t.text for t in result.findall('.//time/beat-type')], ['8', '4'])

    def staff_image(self, lines=5, width=200, gap=10):
        image = np.full((100, width + 20), 255, np.uint8)
        for i in range(lines):
            image[20+i*gap, 10:width+10] = 0
        points = [Obj(x=x, y=[20+i*gap for i in range(5)]) for x in range(10,width+10,2)]
        return image, [Obj(staffs=[Obj(grid=points)])]

    def test_real_staff_with_no_pitched_notes_is_allowed(self):
        self.assertTrue(pipeline._has_printed_staff(*self.staff_image()))

    def test_dark_qr_like_region_is_rejected(self):
        image, rows = self.staff_image(width=25, gap=5)
        image[20:41,10:35] = 0
        self.assertFalse(pipeline._has_printed_staff(image, rows))

    def test_blank_page_is_rejected(self):
        image, rows = self.staff_image()
        image[:] = 255
        self.assertFalse(pipeline._has_printed_staff(image, rows))

    def test_failed_recognition_is_not_silently_skipped(self):
        original = pipeline._read_page
        try:
            def fail(path):
                raise RuntimeError('inference failed')
            pipeline._read_page = fail
            with self.assertRaisesRegex(RuntimeError, 'inference failed'):
                pipeline.scan(['first.png'])
        finally:
            pipeline._read_page = original

    def test_engine_nonmusic_exception_is_classified(self):
        with patch.object(pipeline, 'detect_staffs_in_image', side_effect=Exception('No staffs found')):
            with self.assertRaises(pipeline.NonMusicPage):
                pipeline._read_page('cover.png')

    def test_other_detector_exceptions_propagate(self):
        with patch.object(pipeline, 'detect_staffs_in_image', side_effect=RuntimeError('model failed')):
            with self.assertRaisesRegex(RuntimeError, 'model failed'):
                pipeline._read_page('score.png')

    def rest_score(self):
        root = score()
        p = root.find('part')
        p.clear();p.set('id','P1')
        for i in range(3):
            m=ET.SubElement(p,'measure',number=str(i+1))
            if i==0:
                ET.SubElement(ET.SubElement(ET.SubElement(m,'attributes'),'measure-style'),'multiple-rest').text='3'
            n=ET.SubElement(m,'note',{'id':'rest-p0-100-100'} if i==0 else {})
            ET.SubElement(n,'rest',measure='yes');ET.SubElement(n,'duration').text='4'
        return root

    def test_multirest_can_expand_and_shrink_without_sounding_changes(self):
        root=self.rest_score()
        pipeline.repair_rest_count(root,'rest-p0-100-100',11)
        self.assertEqual(len(root.findall('part/measure')),11)
        self.assertEqual(root.findtext('.//multiple-rest'),'11')
        pipeline.repair_rest_count(root,'rest-p0-100-100',2)
        self.assertEqual(len(root.findall('part/measure')),2)

    def test_multirest_never_deletes_sounding_content(self):
        root=self.rest_score();m=root.findall('part/measure')[1]
        ET.SubElement(m.find('note'),'pitch')
        with self.assertRaisesRegex(ValueError,'non-rest'):
            pipeline.repair_rest_count(root,'rest-p0-100-100',2)

    def test_multirest_review_candidates_follow_renumbered_measures(self):
        root = self.rest_score()
        fields = ET.SubElement(ET.SubElement(root, 'identification'), 'miscellaneous')
        field = ET.SubElement(fields, 'miscellaneous-field', name='conversion-audit')
        field.text = json.dumps({'tupletCandidates': [{'part': 'P1', 'measure': 4, 'number': '4'}]})
        text = pipeline.repair_rest_counts_xml(ET.tostring(root, encoding='unicode'),
            json.dumps([{'sourceId': 'rest-p0-100-100', 'count': 11}]))
        result = ET.fromstring(text)
        entry = json.loads(result.findtext('.//miscellaneous-field[@name="conversion-audit"]'))['tupletCandidates'][0]
        self.assertEqual((entry['measure'], entry['number']), (12, '12'))

    def test_unmarked_page_continues_known_meter(self):
        a=ET.fromstring('<score-partwise><part id="P1"><measure number="1"><attributes><divisions>2</divisions><time><beats>6</beats><beat-type>8</beat-type></time></attributes><note id="n1-p0-100-100"><rest/><duration>6</duration></note></measure></part></score-partwise>')
        b=ET.fromstring('<score-partwise><part id="P1"><measure number="1"><attributes><divisions>2</divisions><time><beats>3</beats><beat-type>4</beat-type></time></attributes><note id="n2-p1-100-100"><rest/><duration>6</duration></note></measure></part></score-partwise>')
        merged=pipeline._merge_pages([a,b])
        sources=[{'page':i,'score':s,'layout':[[0,80,200,120]],'meters':[],'inferredFirst':[i==1]} for i,s in enumerate([a,b])]
        pipeline._repair_meters(merged,sources)
        self.assertEqual(audit(merged)[0]['meters'],[[1,6,8]])
        self.assertEqual(audit(merged)[0]['durationFlags'],[])

    def test_explicit_unsupported_meter_is_preserved(self):
        root=ET.fromstring('<score-partwise><part id="P1"><measure><attributes><time><beats>7</beats><beat-type>8</beat-type></time></attributes></measure></part></score-partwise>')
        sources=[{'page':0,'score':root,'layout':[],'meters':[],'inferredFirst':[False]}]
        merged=pipeline._merge_pages([root]);pipeline._repair_meters(merged,sources)
        self.assertEqual(audit(merged)[0]['meters'],[[1,7,8]])


if __name__ == '__main__':
    unittest.main()
