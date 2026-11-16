"""Source-only multirest regressions and cross-font/size/AA raster sweep.

All raster cases are independently drawn SMuFL glyphs, never runtime templates.
Existing legal MusicXML fixtures can additionally be rendered/checked by
probe_multirests_browser.mjs. No independent evaluation reference score is read.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import unittest

import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'web/src/py'))
from score_numbers import read_multirest_regions,rest_number_box

COUNTS=[2,3,4,5,8,11,17]
SYMBOLS={2:[0xe4e2],3:[0xe4e2,0xe4e3],4:[0xe4e1],5:[0xe4e1,0xe4e3],8:[0xe4e1,0xe4e1],11:[0xe4e1,0xe4e1,0xe4e2,0xe4e3]}
_FONT_DIR=None


def font_path(name,directory=None):
    candidates=[Path(directory or '/tmp/tuplet-glyph-fonts')/(name+'.otf'),ROOT.parent/'fonts'/(name+'.otf'),Path('/tmp/accidental-fonts')/(name+'.otf')]
    return next(path for path in candidates if path.exists())


def draw_case(font_name,unit,aa,count=4,style='symbols',negative=None,directory=None):
    directory=directory or _FONT_DIR
    top,left,right=6*unit,unit,29*unit;bottom=top+4*unit
    im=Image.new('L',(30*unit*aa,19*unit*aa),255);d=ImageDraw.Draw(im)
    for y in range(top,bottom+1,unit):d.line((left*aa,y*aa,right*aa,y*aa),fill=0,width=aa)
    font=ImageFont.truetype(str(font_path(font_name,directory)),4*unit*aa)
    text_path=Path(directory or '/tmp/tuplet-glyph-fonts')/'NotoSans.ttf'
    if not text_path.exists():text_path=Path('/tmp/tuplet-glyph-fonts/NotoSans.ttf')
    text=ImageFont.truetype(str(text_path),3*unit*aa)
    cx=15*unit*aa
    glyphs=SYMBOLS.get(count,SYMBOLS[4])
    if style=='maxima':glyphs=[0xe4e0]
    if count==17:style='H'
    if negative in ('whole-with-number','half-with-number'):glyphs=[0xe4e3 if negative.startswith('whole') else 0xe4e4]
    glyph_boxes=[]
    if negative not in ('number-only','tempo','barline'):
        if style=='H':
            a,b=round(cx-3*unit*aa),round(cx+3*unit*aa);cy=(top+2*unit)*aa
            d.rectangle((a,round(cy-.45*unit*aa),b,round(cy+.45*unit*aa)),fill=0)
            for x in (a,b):d.rectangle((x,round(cy-unit*aa),x+max(1,round(.14*unit*aa)),round(cy+unit*aa)),fill=0)
            glyph_boxes.append([a/aa,top+unit,b/aa,top+3*unit])
        else:
            sizes=[font.getbbox(chr(cp)) for cp in glyphs];gap=round(.5*unit*aa);width=sum(b[2]-b[0] for b in sizes)+gap*(len(glyphs)-1);x=round(cx-width/2)
            for cp,(a,b,c,e) in zip(glyphs,sizes):
                y=(top+unit)*aa
                d.text((x-a,y-b),chr(cp),font=font,fill=0)
                glyph_boxes.append([x/aa,y/aa,(x+c-a)/aa,(y+e-b)/aa]);x+=c-a+gap
    if negative=='barline':d.rectangle((14*unit*aa,top*aa,(14*unit+.14*unit)*aa,bottom*aa),fill=0)
    if negative=='tempo':
        d.ellipse((13*unit*aa,2*unit*aa,14*unit*aa,2.7*unit*aa),fill=0);d.line((14*unit*aa,unit*aa,14*unit*aa,2.5*unit*aa),fill=0,width=aa)
    if negative=='beam':
        # Replace the rest with ordinary beamed notes crossing the staff.
        d.rectangle((9*unit*aa,(top-.1*unit)*aa,22*unit*aa,(bottom+.1*unit)*aa),fill=255)
        for y in range(top,bottom+1,unit):d.line((left*aa,y*aa,right*aa,y*aa),fill=0,width=aa)
        for x in (12,15,18):
            d.line((x*unit*aa,(top+.7*unit)*aa,x*unit*aa,(top+3.1*unit)*aa),fill=0,width=max(1,round(.12*unit*aa)))
            d.ellipse(((x-1)*unit*aa,(top+2.7*unit)*aa,x*unit*aa,(top+3.4*unit)*aa),fill=0)
        d.rectangle((12*unit*aa,(top+.7*unit)*aa,18*unit*aa,(top+1.1*unit)*aa),fill=0)
        d.rectangle((12*unit*aa,(top+1.5*unit)*aa,18*unit*aa,(top+1.9*unit)*aa),fill=0)
    if negative!='no-number':
        label=str(count);a,b,c,e=text.getbbox(label);nx=cx if negative!='displaced-number' else 3*unit*aa
        y=round((top-.6*unit)*aa-(e-b));d.text((round(nx-(c-a)/2)-a,y-b),label,font=text,fill=0)
    boxes=[[left,top,right,bottom]]
    if negative=='other-staff':
        # The upper staff has a number and no rest; the lower has a longa and
        # no number. A detector must not borrow evidence from another staff.
        d.rectangle((10*unit*aa,(top+.7*unit)*aa,20*unit*aa,(bottom+.1*unit)*aa),fill=255)
        for y in range(top,bottom+1,unit):d.line((left*aa,y*aa,right*aa,y*aa),fill=0,width=aa)
        nt=14*unit
        for y in range(nt,nt+4*unit+1,unit):d.line((left*aa,y*aa,right*aa,y*aa),fill=0,width=aa)
        d.rectangle((round(cx-.25*unit*aa),(nt+unit)*aa,round(cx+.25*unit*aa),(nt+3*unit)*aa),fill=0)
        boxes.append([left,nt,right,nt+4*unit])
    if aa>1:im=im.resize((30*unit,19*unit),Image.Resampling.LANCZOS)
    return np.asarray(im),boxes,glyph_boxes


class Regressions(unittest.TestCase):
    def setUp(self):
        # Default discovery must not require another experiment's /tmp cache.
        # The optional font sweep remains explicit; a clean checkout reports
        # the missing development-only font inputs rather than failing.
        try:
            font_path('Bravura',_FONT_DIR)
            text=Path(_FONT_DIR or '/tmp/tuplet-glyph-fonts')/'NotoSans.ttf'
            if not text.exists():
                text=Path('/tmp/tuplet-glyph-fonts/NotoSans.ttf')
            if not text.exists():
                raise FileNotFoundError
        except (StopIteration,FileNotFoundError):
            self.skipTest('Optional OFL font rasters unavailable; prepare the font manifest and pass --fonts for the explicit sweep')

    def test_whole_rest_is_not_four_bars(self):
        for negative in ('whole-with-number','half-with-number','barline','tempo','number-only','no-number','displaced-number','beam','other-staff'):
            im,boxes,_=draw_case('Bravura',16,3,negative=negative)
            self.assertEqual(read_multirest_regions(im,boxes),[],negative)

    def test_longa_and_existing_h_api(self):
        for style in ('symbols','H'):
            im,boxes,_=draw_case('Bravura',16,3,style=style)
            regions=read_multirest_regions(im,boxes)
            self.assertEqual(len(regions),1,regions)
            self.assertIsNotNone(rest_number_box(im,boxes[0],(240,128)))


def sweep(args):
    rows=[];out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    for font in ['Bravura','Leipzig','Leland','Sebastian','Eugene']:
        for unit in [8,12,20,30]:
            for aa in [1,3]:
                for count in COUNTS:
                    im,boxes,glyphs=draw_case(font,unit,aa,count,directory=args.fonts)
                    regions=read_multirest_regions(im,boxes)
                    row={'font':font,'unit':unit,'aa':aa,'count':count,'regions':regions,'source_sha256':hashlib.sha256(im.tobytes()).hexdigest()}
                    row['covered']=len(regions)==1
                    if not row['covered']:cv2.imwrite(str(out/f'FAIL-{font}-{unit}-{aa}-{count}.png'),im)
                    rows.append(row)
                im,boxes,_=draw_case(font,unit,aa,8,style='maxima',directory=args.fonts)
                regions=read_multirest_regions(im,boxes)
                row={'font':font,'unit':unit,'aa':aa,'count':8,'variant':'SMuFL-restMaxima',
                     'regions':regions,'covered':len(regions)==1,'source_sha256':hashlib.sha256(im.tobytes()).hexdigest()}
                if not row['covered']:cv2.imwrite(str(out/f'FAIL-{font}-{unit}-{aa}-maxima.png'),im)
                rows.append(row)
    negatives=[]
    for unit in [8,12,20,30]:
        for aa in [1,3]:
            for kind in ['whole-with-number','half-with-number','barline','tempo','number-only','no-number','displaced-number','beam','other-staff']:
                im,boxes,_=draw_case('Bravura',unit,aa,negative=kind,directory=args.fonts);regions=read_multirest_regions(im,boxes)
                negatives.append({'unit':unit,'aa':aa,'kind':kind,'false_regions':regions})
    result={'module_sha256':hashlib.sha256((ROOT/'web/src/py/score_numbers.py').read_bytes()).hexdigest(),
            'positive_n':len(rows),'positive_covered':sum(row['covered'] for row in rows),'negative_n':len(negatives),
            'negative_clean':sum(not row['false_regions'] for row in negatives),'positive':rows,'negative':negatives,
            'font_sha256':{name:hashlib.sha256(font_path(name,args.fonts).read_bytes()).hexdigest() for name in ['Bravura','Leipzig','Leland','Sebastian','Eugene']}}
    (out/'sweep.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:result[key] for key in ['positive_n','positive_covered','negative_n','negative_clean']},indent=2))
    if result['positive_covered']!=len(rows) or result['negative_clean']!=len(negatives):raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sweep',action='store_true');p.add_argument('--fonts');p.add_argument('--out',default='/tmp/multirest-sweep');args,remaining=p.parse_known_args()
    _FONT_DIR=args.fonts
    tests=unittest.main(argv=[sys.argv[0]]+remaining,exit=False)
    if not tests.result.wasSuccessful():raise SystemExit(1)
    if args.sweep:sweep(args)
