"""Generate the small OFL Bravura raster bank used by printed_tuplets.py.

Development only: needs Pillow and the Bravura.otf path as its argument.
The recognizer needs neither Pillow nor an installed font.
"""
import base64
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def generate(font_path):
    font = ImageFont.truetype(str(font_path), 110)
    bank = []
    missing = bytes(font.getmask(chr(0x10FFFD)))
    for number in range(2, 10):
        for first in (0xE880, 0xF4CC):  # SMuFL tuplet digits, regular and light
            character = chr(first + number)
            if bytes(font.getmask(character)) == missing:
                continue
            left, top, right, bottom = font.getbbox(character)
            image = Image.new('L', (right-left+8, bottom-top+8), 255)
            ImageDraw.Draw(image).text((4-left, 4-top), character, font=font, fill=0)
            ink = 255-np.array(image)
            x, y, width, height = cv2.boundingRect((ink > 80).astype(np.uint8))
            raster = cv2.resize(ink[y:y+height, x:x+width], (24, 32), interpolation=cv2.INTER_AREA)
            bank.append({'number': number, 'font': Path(font_path).stem, 'codepoint': hex(first+number),
                         'raster': base64.b64encode(raster.tobytes()).decode()})
    return bank


if __name__ == '__main__':
    path = Path(__file__).resolve().parents[1] / 'web/src/py/tuplet_templates.json'
    path.write_text(json.dumps([item for font in sys.argv[1:] for item in generate(font)], indent=2)+'\n')
    print(path)
