"""Source-only crop decisions, including ledger ownership between two staffs."""
from pathlib import Path
import sys
import unittest
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'web/src/py'))
from staff_coverage import choose_staff_region


def source(top=140, bottom=180, head_y=90, ledgers=True):
    image=np.full((400,400),255,np.uint8)
    for y in range(top,bottom+1,10): cv2.line(image,(20,y),(380,y),0,1)
    cv2.ellipse(image,(200,head_y),(7,4),0,0,360,0,-1)
    if ledgers:
        reference=top if head_y<top else bottom
        sign=-1 if head_y<top else 1
        for y in range(reference+sign*10,head_y+sign,sign*10):cv2.line(image,(190,y),(210,y),0,1)
    grid=[{'x':20,'y':list(range(top,bottom+1,10))},{'x':380,'y':list(range(top,bottom+1,10))}]
    heads=[{'center':[200,head_y],'size':[14,8]}]
    return image,[20,top-40,381,bottom+40],grid,heads


class StaffCoverageTests(unittest.TestCase):
    def test_expands_for_high_head_while_retaining_old_pixels(self):
        image,box,grid,heads=source()
        got=choose_staff_region(image,box,grid,heads)
        self.assertTrue(got['changed'])
        self.assertEqual(got['box'],[20,80,381,220])
        self.assertEqual(got['discardedInkPixels'],0)

    def test_low_ledger_is_symmetric(self):
        image,box,grid,heads=source(head_y=230)
        got=choose_staff_region(image,box,grid,heads)
        self.assertEqual(got['box'],[20,100,381,240])

    def test_title_or_unbacked_head_does_not_expand(self):
        args=source(ledgers=False)
        self.assertFalse(choose_staff_region(*args)['changed'])

    def test_nearer_previous_staff_owns_low_ledger_head(self):
        # Head lies +3 spaces below the preceding staff, and 5 spaces above
        # the current one: it is outside the old +/-2 guard but belongs above.
        image,box,grid,heads=source(top=180,bottom=220,head_y=130)
        got=choose_staff_region(image,box,grid,heads,neighbours=[{'top':60,'bottom':100}])
        self.assertFalse(got['changed'])

    def test_midpoint_abstains(self):
        image,box,grid,heads=source(top=180,bottom=220,head_y=130)
        self.assertFalse(choose_staff_region(image,box,grid,heads,neighbours=[{'top':40,'bottom':80}])['changed'])

    def test_distant_neighbour_does_not_block_valid_expansion(self):
        image,box,grid,heads=source(top=180,bottom=220,head_y=130)
        self.assertTrue(choose_staff_region(image,box,grid,heads,neighbours=[{'top':0,'bottom':40}])['changed'])

    def test_long_staff_lines_do_not_impersonate_ledgers(self):
        image,box,grid,heads=source(ledgers=False)
        for y in (100,110,120,130):cv2.line(image,(20,y),(380,y),0,1)
        self.assertFalse(choose_staff_region(image,box,grid,heads)['changed'])


if __name__=='__main__':unittest.main()
