from pathlib import Path
import json
import sys
from types import SimpleNamespace as Obj
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'web/src/py'))
from pipeline import _reassociate_note_coordinates
import pipeline


def fixture(positions=(1, 2, 3), pitches=('E4', 'F4', 'G4')):
    heads = [Obj(position=pos, center=(100+i*40, 200-pos*5)) for i, pos in enumerate(positions)]
    result = [Obj(rhythm='note_8', pitch=pitch, image_coordinates=(300-i*40, 500)) for i, pitch in enumerate(pitches)]
    staff = Obj(is_grandstaff=False, get_notes=lambda: heads, average_unit_size=10)
    return result, staff


class SourceGeometryTests(unittest.TestCase):
    def test_unique_head_order_repairs_attention_without_editing_music(self):
        result, staff = fixture()
        pitches = [symbol.pitch for symbol in result]
        audit = _reassociate_note_coordinates(result, staff)
        self.assertEqual(audit['decodedNotes'], 3)
        self.assertEqual([symbol.image_coordinates[0] for symbol in result], [100, 140, 180])
        self.assertEqual([symbol.pitch for symbol in result], pitches)

    def test_one_unmatched_detector_head_can_be_skipped(self):
        result, staff = fixture((1, 9, 2, 3))
        audit = _reassociate_note_coordinates(result, staff)
        self.assertEqual(audit['detectedHeads'], 4)
        self.assertEqual([symbol.image_coordinates[0] for symbol in result], [100, 180, 220])

    def test_ambiguous_missing_simultaneous_or_different_pitch_sequence_abstains(self):
        for positions in ((1, 1, 2, 3), (1, 2), (1, 3, 2)):
            result, staff = fixture(positions)
            old = [symbol.image_coordinates for symbol in result]
            self.assertIsNone(_reassociate_note_coordinates(result, staff))
            self.assertEqual([symbol.image_coordinates for symbol in result], old)
        result, staff = fixture()
        staff.get_notes()[1].center = (101, 200)
        self.assertIsNone(_reassociate_note_coordinates(result, staff))

    def test_polyphony_is_not_associated_as_a_melody(self):
        result, staff = fixture()
        staff.is_grandstaff = True
        self.assertIsNone(_reassociate_note_coordinates(result, staff))
        staff.is_grandstaff = False
        result.append(Obj(rhythm='chord_8', pitch='C5', image_coordinates=None))
        self.assertIsNone(_reassociate_note_coordinates(result, staff))

    def test_one_pitch_error_in_a_long_unique_line_is_preserved(self):
        def pitch(index):
            return 'CDEFGAB'[index % 7]+str(index//7)
        pitches = [pitch(29+i) for i in range(30)]
        pitches[15] = pitch(29+16)
        result, staff = fixture(tuple(range(30)), tuple(pitches))
        audit = _reassociate_note_coordinates(result, staff)
        self.assertEqual(audit['pitchDisagreements'], 1)
        self.assertEqual([s.pitch for s in result], pitches)
        self.assertEqual(result[15].image_coordinates, staff.get_notes()[15].center)

    def test_coordinate_wrapper_composes_with_existing_octave_wrapper(self):
        result, staff = fixture()
        staff.min_y = 100
        with patch.object(pipeline, '_parse_staff_image_geometry_base', return_value=result) as base, \
             patch.object(pipeline, '_mark_octave_clefs', return_value={}), \
             patch.object(pipeline, '_line_above', None):
            found = pipeline.staff_parsing.parse_staff_image(None, 0, staff, None, None, None)
        base.assert_called_once()
        self.assertIs(found, result)
        self.assertEqual(result[0].image_coordinates, staff.get_notes()[0].center)

    def test_observed_compound_bar18_chooses_first_pair_and_preserves_third(self):
        from printed_tuplets import tuplet_candidates, apply_tuplet
        data = json.loads((Path(__file__).parent/'fixtures/compound-attention-regression.json').read_text())
        heads = [Obj(center=(x, y), position=pos) for x, y, pos in data['staff']['heads']]
        result = [Obj(rhythm=r, pitch=p, image_coordinates=point) for r, p, voice, point in data['staff']['decoded']]
        staff = Obj(is_grandstaff=False, get_notes=lambda: heads, average_unit_size=17)
        mark = {'staff': 0, 'number': 2, **data['printedDuplet']}
        sources = [{'page': 0, 'layout': [[0, 560, 1920, 640]], 'tuplets': [mark]}]
        def score():
            root = ET.fromstring('<score-partwise><part id="P1"><measure number="1"><attributes><divisions>4</divisions><time><beats>6</beats><beat-type>8</beat-type></time></attributes></measure></part></score-partwise>')
            for index in data['measureNoteIndices']:
                symbol = result[index]
                x, y = symbol.image_coordinates
                note = ET.SubElement(root.find('part/measure'), 'note', id=f'n{index}-p0-{int(x)}-{int(y)}')
                pitch = ET.SubElement(note, 'pitch')
                ET.SubElement(pitch, 'step').text = symbol.pitch[0]
                ET.SubElement(pitch, 'octave').text = symbol.pitch[1:]
                for tag, value in [('duration', '2'), ('voice', '1'), ('type', 'eighth'), ('staff', '1')]:
                    ET.SubElement(note, tag).text = value
            return root
        before = tuplet_candidates(score(), sources)
        self.assertEqual([n.split('-')[0] for n in before[0]['notes']], ['n23', 'n24'])
        _reassociate_note_coordinates(result, staff)
        root = score()
        after = tuplet_candidates(root, sources)
        self.assertEqual([n.split('-')[0] for n in after[0]['notes']], ['n22', 'n23'])
        apply_tuplet(root, after[0])
        third = root.find('part/measure').findall('note')[2]
        self.assertIsNone(third.find('time-modification'))
        self.assertEqual(third.findtext('duration'), '2')


if __name__ == '__main__':
    unittest.main()
