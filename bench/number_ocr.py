"""Optional local Tesseract callback for the native accuracy runner.

The browser already has its own Tesseract.js reader. This uses the same source
crop and requires agreement in at least two readings; it never uploads a score.
Needs the tesseract command, not an additional Python runtime dependency.
"""
from collections import Counter
import csv
import io
import subprocess

import cv2


def read_number(image):
    if image.size == 0:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    large = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    binary = cv2.threshold(large, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
    observations = []
    for pixels, mode in ((large, 7), (binary, 7), (binary, 13)):
        padded = cv2.copyMakeBorder(pixels, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=255)
        result = subprocess.run(['tesseract', 'stdin', 'stdout', '-l', 'eng', '--psm', str(mode),
            '-c', 'tessedit_char_whitelist=0123456789', 'tsv'], input=cv2.imencode('.png', padded)[1].tobytes(),
            capture_output=True, timeout=10, check=True)
        words = [row for row in csv.DictReader(io.StringIO(result.stdout.decode()), delimiter='\t')
                 if row['level'] == '5' and row['text'].strip()]
        text = ''.join(word['text'].strip() for word in words)
        confidence = min((float(word['conf']) for word in words), default=0)
        if text.isdigit() and 2 <= int(text) <= 256 and confidence >= 55:
            observations.append({'value': int(text), 'score': round(confidence, 2), 'mode': mode})
    votes = Counter(observation['value'] for observation in observations).most_common(1)
    return {'value': votes[0][0], 'agreement': votes[0][1], 'observations': observations} if votes and votes[0][1] >= 2 else None
