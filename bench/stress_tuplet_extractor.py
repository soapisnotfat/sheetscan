"""Fresh rendered geometry stress tests, not a whole-score accuracy benchmark.

No training, threshold changes, test-score labels or forced digit filling. The
frozen classifier is identical before/after; only candidate extraction differs.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'web/src/py'))


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def figure(font_path, number, height):
    font = ImageFont.truetype(str(font_path), 100)
    glyph = chr(0xE880+number)
    bounds = font.getbbox(glyph)
    image = Image.new('L', (bounds[2]-bounds[0]+8, bounds[3]-bounds[1]+8), 255)
    ImageDraw.Draw(image).text((4-bounds[0], 4-bounds[1]), glyph, font=font, fill=0)
    ink = 255-np.array(image)
    x, y, width, old_height = cv2.boundingRect((ink > 80).astype(np.uint8))
    if old_height < 2:
        raise ValueError(f'{font_path}: missing digit {number}')
    return cv2.resize(ink[y:y+old_height, x:x+width], (max(1, round(width*height/old_height)), height), interpolation=cv2.INTER_AREA)


def render(font, number, unit, height_ratio, gap, mode):
    width, height = round(28*unit), round(19*unit)
    image = np.full((height, width), 255, np.uint8)
    top, bottom, center = round(8*unit), round(12*unit), round(14*unit)
    glyph = figure(font, number, round(height_ratio*unit)) if number else None
    if glyph is not None:
        y = round(top+.2*unit)-len(glyph)
        x = center-glyph.shape[1]//2
        image[y:y+len(glyph), x:x+glyph.shape[1]] = 255-glyph
        if mode == 'fragment':
            # A second one-pixel horizontal dropout, independent of the staff.
            image[y+round(.47*len(glyph)), x:x+glyph.shape[1]] = 255
        end = y+len(glyph)
    else:
        end = round(top+.2*unit)
    for y in np.linspace(top, bottom, 5).round().astype(int):
        image[y:y+1, round(unit):width-round(unit)] = 0
    beam = end+gap
    cv2.rectangle(image, (round(center-3*unit), beam), (round(center+3*unit), beam+max(2, round(.3*unit))), 0, -1)
    for x in (round(center-3*unit), round(center+3*unit)):
        cv2.line(image, (x, beam), (x, bottom-round(.5*unit)), 0, max(1, round(.12*unit)))
        cv2.ellipse(image, (x-round(.4*unit), bottom-round(.5*unit)), (max(2, round(.6*unit)), max(2, round(.35*unit))), -20, 0, 360, 0, -1)
    return image, [[round(unit), top, width-round(unit), bottom]], center, end-len(glyph)/2 if glyph is not None else end


def run(args):
    before = module(args.baseline, 'extractor_before')
    after = module(ROOT/'web/src/py/printed_tuplets.py', 'extractor_after')
    fonts = dict(item.split('=', 1) for item in args.font)
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'scope': 'fresh synthetic glyph+staff+beam extraction stress; not independent full-score quality',
              'frozenClassifierSha256': digest(ROOT/'web/src/py/tuplet_classifier.json'),
              'beforeSourceSha256': digest(args.baseline), 'afterSourceSha256': digest(ROOT/'web/src/py/printed_tuplets.py'),
              'fontSha256': {name: digest(Path(path)) for name, path in fonts.items()},
              'groupNotes': 'Bravura/Leipzig/Leland are training fonts for the frozen glyph classifier; Eugene was not a tuplet training font but uses Bravura fallback outlines; these renders were generated after the extractor change',
              'cases': [], 'groups': {}}
    for name, path in fonts.items():
        for dpi in (150, 200, 250):
            unit = 14.25*dpi/200
            for ratio in (1.4, 1.7):
                for gap in (1, 2, 4):
                    for number in (0, 2, 3, 4, 5, 8):
                        mode = 'fragment' if ratio == 1.7 and gap == 4 else 'clean'
                        image, boxes, cx, cy = render(Path(path), number, unit, ratio, gap, mode)
                        expected = number if number in (2, 3, 5) else None
                        item = {'font': name, 'dpi': dpi, 'heightRatio': ratio, 'beamGapPixels': gap,
                                'number': expected, 'sourceShape': number, 'mode': mode,
                                'rasterSha256': hashlib.sha256(image.tobytes()).hexdigest()}
                        for label, recognizer in (('before', before), ('after', after)):
                            found = recognizer.read_tuplet_marks(image, boxes)
                            correct = [m for m in found if m['number'] == expected and abs(m['x']-cx) <= unit and abs(m['y']-cy) <= unit]
                            item[label] = {'correct': bool(correct) if expected else not bool(found),
                                           'detections': len(found), 'falseDetections': len(found)-min(1, len(correct)),
                                           'numbers': [m['number'] for m in found]}
                        report['cases'].append(item)
    for name in fonts:
        rows = [r for r in report['cases'] if r['font'] == name]
        report['groups'][name] = {}
        for label in ('before', 'after'):
            pos = [r for r in rows if r['number'] is not None]
            neg = [r for r in rows if r['number'] is None]
            report['groups'][name][label] = {'positiveCorrect': sum(r[label]['correct'] for r in pos), 'positiveTotal': len(pos),
                'negativeRejected': sum(r[label]['correct'] for r in neg), 'negativeTotal': len(neg),
                'falseDetections': sum(r[label]['falseDetections'] for r in rows)}
    (args.out/'results.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report['groups'], indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', action='append', required=True, help='NAME=FILE.otf; repeat for each font')
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    run(parser.parse_args())
