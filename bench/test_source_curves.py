from pathlib import Path
import json
import sys
import unittest

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web/src/py'))
from source_curves import read_grace_slur, read_ordinary_curve


class PrintedCurveTests(unittest.TestCase):
    def source_crops(self, name):
        fixtures = Path(__file__).parent / 'fixtures'
        cases = json.loads((fixtures / f'{name}.json').read_text())
        image = cv2.imread(str(fixtures / f'{name}.png'), cv2.IMREAD_GRAYSCALE)
        self.assertIsNotNone(image)
        for case in cases:
            y = case['y']
            yield case, image[y:y + case['height'], :case['width']]

    def test_slurs_and_ties_from_engraved_grace_pairs(self):
        for case, region in self.source_crops('grace-curves'):
            with self.subTest(case=case['name'], mark=case['mark']):
                reading = read_grace_slur(region, case['start'], case['stop'], case['unit'])
                self.assertEqual(reading is not None, case['mark'] == 'slur')
                if reading:
                    left, top, right, bottom = reading['box']
                    self.assertTrue(0 <= left < right <= case['width'])
                    self.assertTrue(0 <= top < bottom <= case['height'])

    def test_same_pitch_ties_slurs_and_repetitions(self):
        for case, region in self.source_crops('ordinary-curves'):
            with self.subTest(case=case['name'], mark=case['mark']):
                reading = read_ordinary_curve(region, case['start'], case['stop'], case['unit'])
                self.assertEqual(reading['curve'] if reading else None, case['mark'])
                if reading:
                    left, top, right, bottom = reading['box']
                    self.assertTrue(0 <= left < right <= case['width'])
                    self.assertTrue(0 <= top < bottom <= case['height'])


if __name__ == '__main__':
    unittest.main()
