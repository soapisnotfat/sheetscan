"""Repair missing metronome font ink in a versioned test input, never in runtime.

Supply original PDF, its vector PDF/SVG provenance, and an OFL SMuFL font.
Only empty PDF glyph slots corresponding to explicit SVG metronome codepoints
are filled. No MusicXML, reference BPM, pitch, or measure is read.
The original is never overwritten. Non-glyph pixels must compare identically.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, ContentStream, DecodedStreamObject, DictionaryObject,
                          NameObject, NumberObject)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def image_object(writer, pixels, gray=False):
    image = DecodedStreamObject()
    image.set_data(pixels.tobytes())
    image.update({NameObject('/Type'): NameObject('/XObject'),
                  NameObject('/Subtype'): NameObject('/Image'),
                  NameObject('/Width'): NumberObject(pixels.shape[1]),
                  NameObject('/Height'): NumberObject(pixels.shape[0]),
                  NameObject('/ColorSpace'): NameObject('/DeviceGray' if gray else '/DeviceRGB'),
                  NameObject('/BitsPerComponent'): NumberObject(8)})
    return image


def inverse_final_transform(page, reader):
    current, stack = [1,0,0,1,0,0], []
    for operands, operator in ContentStream(page.get_contents(), reader).operations:
        if operator == b'q':
            stack.append(current[:])
        elif operator == b'Q':
            current = stack.pop()
        elif operator == b'cm':
            a,b,c,d,e,f = current
            g,h,i,j,k,l = map(float,operands)
            current = [a*g+c*h,b*g+d*h,a*i+c*j,b*i+d*j,a*k+c*l+e,b*k+d*l+f]
    a,b,c,d,e,f = current
    determinant = a*d-b*c
    return [d/determinant,-b/determinant,-c/determinant,a/determinant,
            (c*f-d*e)/determinant,(b*e-a*f)/determinant]


def repair(original, vector, svg, font, destination):
    original, vector, svg, font, destination = map(Path, (original, vector, svg, font, destination))
    if destination.resolve() in [original.resolve(), vector.resolve()]:
        raise ValueError('Output must be a new versioned PDF')
    tree = ET.parse(svg)
    units = []
    for group in tree.getroot().iter():
        if group.get('class') == 'tempo':
            for span in group.iter():
                value = (span.text or '').strip()
                if value and all('\ueca0' <= c <= '\uecb7' or c.isspace() for c in value):
                    units.append({'codepoints': [f'U+{ord(c):04X}' for c in value if not c.isspace()],
                                  'text': value, 'sourceGroup': group.get('id')})
    source = PdfReader(vector)
    target = PdfReader(original)
    if len(source.pages) != len(target.pages):
        raise ValueError('Vector and target page counts differ')
    slots = []
    for page_index, page in enumerate(source.pages):
        def visit(text, cm, tm, font_dictionary, size):
            if not text.strip() or '\x00' not in text:
                return
            if text.strip() != '\x00':
                raise ValueError('Only individual unmapped unit slots are supported')
            descendant = font_dictionary['/DescendantFonts'][0].get_object()
            descriptor = descendant['/FontDescriptor'].get_object()
            # PDF CID 0 must be genuinely empty, not a visible unrecognized glyph.
            raw = descriptor['/FontFile2'].get_data()
            import struct
            tables = {}
            for i in range(struct.unpack_from('>H', raw, 4)[0]):
                tag, _, offset, length = struct.unpack_from('>4sIII', raw, 12+16*i)
                tables[tag] = (offset, length)
            long_loca = struct.unpack_from('>h', raw, tables[b'head'][0]+50)[0]
            begin, end = struct.unpack_from('>II' if long_loca else '>HH', raw, tables[b'loca'][0])
            if begin != end:
                raise ValueError('Unmapped source glyph has ink; do not replace it')
            a, b, c, d, e, f = cm
            x = tm[4]*a + tm[5]*c + e
            y = tm[4]*b + tm[5]*d + f
            if abs(b) > 1e-6 or abs(c) > 1e-6 or a <= 0 or d >= 0:
                raise ValueError('Unsupported rotated/skewed unit slot')
            slots.append({'page': page_index, 'x': x, 'y': y, 'fontPoints': abs(size*d),
                          'emptyFontSHA256': hashlib.sha256(raw).hexdigest(), 'emptyFontBytes': len(raw)})
        page.extract_text(visitor_text=visit)
    if not units or len(slots) != len(units):
        raise ValueError(f'Explicit SVG units / empty vector slots disagree: {len(units)} / {len(slots)}')
    writer = PdfWriter()
    writer.clone_document_from_reader(target)
    # Do not wrap/rewrite existing operators: an added save can change a browser
    # renderer's antialias optimization. Cancel the final CTM only for new ink.
    inverses = [inverse_final_transform(page,target) for page in target.pages]
    masks = [[] for _ in target.pages]
    for index, (slot, unit) in enumerate(zip(slots, units)):
        page = writer.pages[slot['page']]
        reference = source.pages[slot['page']]
        sx = float(page.mediabox.width)/float(reference.mediabox.width)
        sy = float(page.mediabox.height)/float(reference.mediabox.height)
        x, y, size = slot['x']*sx, slot['y']*sy, slot['fontPoints']*sy
        resolution = 8  # 576 dpi alpha image, embedded without a text/GT layer.
        face = ImageFont.truetype(str(font), round(size*resolution))
        box = face.getbbox(unit['text'], anchor='ls')
        if box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError('Fallback font does not draw the explicit source unit')
        pad = 2
        image = Image.new('RGBA', (box[2]-box[0]+2*pad, box[3]-box[1]+2*pad))
        ImageDraw.Draw(image).text((pad-box[0], pad-box[1]), unit['text'], font=face, anchor='ls', fill=(0,0,0,255))
        pixels = np.asarray(image)
        alpha = image_object(writer, pixels[:,:,3], True)
        ink = image_object(writer, pixels[:,:,:3])
        ink[NameObject('/SMask')] = writer._add_object(alpha)
        name = NameObject(f'/RepairedTempoUnit{index}')
        resources = page['/Resources'].get_object()
        xobjects = resources.get('/XObject', DictionaryObject()).get_object()
        xobjects[name] = writer._add_object(ink)
        resources[NameObject('/XObject')] = xobjects
        left = x+(box[0]-pad)/resolution
        bottom = y-(box[3]+pad)/resolution
        width, height = image.width/resolution, image.height/resolution
        addition = DecodedStreamObject()
        reset = ' '.join(f'{n:.12f}' for n in inverses[slot['page']])
        addition.set_data(f'q {reset} cm {width:.8f} 0 0 {height:.8f} {left:.8f} {bottom:.8f} cm {name} Do Q\n'.encode())
        existing = page.get('/Contents')
        page[NameObject('/Contents')] = ArrayObject([*(existing if isinstance(existing, ArrayObject) else [existing]), writer._add_object(addition)])
        masks[slot['page']].append([left, float(page.mediabox.height)-bottom-height, left+width, float(page.mediabox.height)-bottom])
        slot.update(unit, targetGlyphBoxPoints=masks[slot['page']][-1])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('wb') as stream:
        writer.write(stream)
    preserved=[]
    output_reader=PdfReader(destination)
    for index,page in enumerate(target.pages):
        original_operators=page.get_contents().get_data()
        new_operators=output_reader.pages[index].get_contents().get_data()
        if not new_operators.startswith(original_operators):
            raise ValueError('Original drawing operators were changed')
        preserved.append({'page':index,'originalDrawingOperatorsSHA256':hashlib.sha256(original_operators).hexdigest(),
                          'originalDrawingOperatorsPreserved':True})
    preflight = []
    with tempfile.TemporaryDirectory(prefix='tempo-render-preflight-') as scratch:
        for label, source_path in [('before', original), ('after', destination)]:
            subprocess.run(['pdftoppm', '-r', '200', '-png', str(source_path), str(Path(scratch)/label)], check=True, capture_output=True)
        for page_index, page_masks in enumerate(masks):
            before = np.asarray(Image.open(Path(scratch)/f'before-{page_index+1}.png').convert('RGB'))
            after = np.asarray(Image.open(Path(scratch)/f'after-{page_index+1}.png').convert('RGB'))
            allowed = np.zeros(before.shape[:2], dtype=bool)
            for x0,y0,x1,y1 in page_masks:
                allowed[max(0,math.floor(y0*200/72)-2):math.ceil(y1*200/72)+2,
                        max(0,math.floor(x0*200/72)-2):math.ceil(x1*200/72)+2] = True
            changed = np.any(before != after, axis=2)
            outside = int(np.count_nonzero(changed & ~allowed))
            if outside or not np.any(changed):
                Image.fromarray(before).save(destination.with_suffix('.before.png'))
                Image.fromarray(after).save(destination.with_suffix('.after.png'))
                yy,xx=np.where(changed & ~allowed)
                destination.with_suffix('.failed-preflight.json').write_text(json.dumps({'masks':page_masks,'outsideXY':list(zip(xx.tolist(),yy.tolist()))}))
                raise ValueError(f'Repair must add glyph ink only: outside={outside}')
            preflight.append({'page':page_index,'changedPixels':int(changed.sum()),'changedOutsideGlyphMasks':outside,
                              'beforePixelsSHA256':hashlib.sha256(before.tobytes()).hexdigest(),
                              'afterPixelsSHA256':hashlib.sha256(after.tobytes()).hexdigest()})
    receipt = {'operation':'explicit-SVG-unit-fallback-ink-only','originalSHA256':sha(original),
               'vectorSHA256':sha(vector),'svgSHA256':sha(svg),'fallbackFontSHA256':sha(font),
               'outputSHA256':sha(destination),'glyphs':slots,'preflight':preflight,'drawingPreservation':preserved,
               'referenceMusicXMLRead':False,'productionInference':False}
    destination.with_suffix('.repair.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['input','vector','svg','font','output']:
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    print(json.dumps(repair(args.input,args.vector,args.svg,args.font,args.output),indent=2))
