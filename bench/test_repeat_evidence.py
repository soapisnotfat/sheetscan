from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'web/src/py'))
from score_numbers import read_forward_repeats
from pipeline import _repair_printed_forward_repeats


def image(dots=2, thick=True, double=True):
    page = np.full((200, 400), 255, np.uint8)
    for y in range(60, 141, 20):
        page[y, 10:390] = 0
    cv2.rectangle(page, (150, 60), (158 if thick else 151, 140), 0, -1)
    if double:
        cv2.rectangle(page, (169, 60), (171, 140), 0, -1)
    for y in (90, 110)[:dots]:
        cv2.circle(page, (181, y), 4, 0, -1)
    return page, [[10, 60, 389, 140]]


class RepeatEvidenceTests(unittest.TestCase):
    def test_complete_repeat_geometry_is_recognized(self):
        marks = read_forward_repeats(*image())
        self.assertEqual(len(marks), 1)
        self.assertEqual(marks[0]['kind'], 'forward-repeat')
        self.assertAlmostEqual(marks[0]['x'], 181, places=1)

    def test_single_bar_double_bar_or_one_dot_do_not_imply_repeat(self):
        for args in ({'dots': 0}, {'dots': 1}, {'double': False}, {'thick': False}):
            self.assertEqual(read_forward_repeats(*image(**args)), [])

    def test_notehead_shapes_are_not_repeat_dots(self):
        page, boxes = image(dots=0)
        for y in (90, 110):
            cv2.ellipse(page, (181, y), (9, 6), -20, 0, 360, 0, -1)
        self.assertEqual(read_forward_repeats(page, boxes), [])

    def test_repeat_addition_requires_source_and_unique_following_measure(self):
        root = ET.fromstring('<score-partwise><part id="P1"><measure number="1"><note id="n1-p0-120-100"/></measure><measure number="2"><note id="n2-p0-220-100"/></measure></part></score-partwise>')
        page, boxes = image()
        sources = [{'page': 0, 'layout': boxes, 'forwardRepeats': read_forward_repeats(page, boxes)}]
        changes = _repair_printed_forward_repeats(root, sources)
        self.assertEqual([c['measure'] for c in changes], [2])
        self.assertEqual(len(root.findall('.//repeat')), 1)
        self.assertEqual(_repair_printed_forward_repeats(root, sources), [])
        self.assertIsNone(root.find('part/measure').find('barline'))


if __name__ == '__main__':
    unittest.main()
