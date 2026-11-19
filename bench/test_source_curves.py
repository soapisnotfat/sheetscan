from pathlib import Path
import json
import sys
import unittest

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web/src/py'))
from source_curves import read_grace_slur


class PrintedGraceCurveTests(unittest.TestCase):
    def test_slurs_and_ties_from_engraved_source(self):
        fixtures = Path(__file__).parent / 'fixtures'
        cases = json.loads((fixtures / 'grace-curves.json').read_text())
        image = cv2.imread(str(fixtures / 'grace-curves.png'), cv2.IMREAD_GRAYSCALE)
        self.assertIsNotNone(image)
        for case in cases:
            with self.subTest(case=case['name'], mark=case['mark']):
                start = case['y']
                region = image[start:start + case['height'], :case['width']]
                reading = read_grace_slur(region, case['start'], case['stop'], case['unit'])
                self.assertEqual(reading is not None, case['mark'] == 'slur')
                if reading:
                    left, top, right, bottom = reading['box']
                    self.assertTrue(0 <= left < right <= case['width'])
                    self.assertTrue(0 <= top < bottom <= case['height'])


if __name__ == '__main__':
    unittest.main()
