# SPDX-License-Identifier: OFL-1.1
"""Small synthetic-font tuplet classifier; NumPy/cv2 only at inference.

Input is foreground ink (zero background, one foreground), preferably the tight
connected-component crop used by printed_tuplets. Scores are raw logits, never
calibrated probabilities. The unknown class and development-set gates reject
unsupported shapes; score context must still decide whether a digit is a tuplet.
See ACCURACY_GLYPHS.md for the model's synthetic-only validation limits.
"""
import base64
import json
from pathlib import Path

import cv2
import numpy as np

_MODEL = None


def normalize_ink(ink):
    """Normalize foreground ink to the exact 32x24 training representation."""
    ink = np.asarray(ink, dtype=np.float32)
    if ink.ndim != 2 or not ink.size or not np.isfinite(ink).all():
        raise ValueError('Expected a finite, nonempty two-dimensional ink crop')
    # INTER_AREA can overshoot one by a float32 ulp; that remains unit ink.
    if ink.max() > 1.5:
        ink = ink/255.
    ink = np.clip(ink, 0, 1)
    # The caller already supplies a tight crop; preserve its boundary and avoid
    # thresholding away anti-aliasing a second time.
    return cv2.resize(ink, (24, 32), interpolation=cv2.INTER_AREA)


def _load_model():
    global _MODEL
    if _MODEL is None:
        model = json.loads(Path(__file__).with_name('tuplet_classifier.json').read_text())
        for name, item in list(model['weights'].items()):
            model['weights'][name] = np.frombuffer(base64.b64decode(item['data']), '<f2').astype(np.float32).reshape(item['shape'])
        _MODEL = model
    return _MODEL


def _convolution(x, weight, bias):
    # Explicit offsets use only NumPy operations available in browser Pyodide.
    height, width = x.shape[1:]
    radius = weight.shape[-1]//2
    padded = np.pad(x, ((0, 0), (radius, radius), (radius, radius)))
    result = np.broadcast_to(bias[:, None, None], (len(bias), height, width)).copy()
    for dy in range(weight.shape[-2]):
        for dx in range(weight.shape[-1]):
            result += np.einsum('oc,chw->ohw', weight[:, :, dy, dx],
                                padded[:, dy:dy+height, dx:dx+width], optimize=True)
    return np.maximum(result, 0)


def _pool(x):
    channels, height, width = x.shape
    return x.reshape(channels, height//2, 2, width//2, 2).max(axis=(2, 4))


def glyph_logits(ink):
    model = _load_model()
    weights = model['weights']
    x = normalize_ink(ink)[None]
    x = _pool(_convolution(x, weights['conv1.weight'], weights['conv1.bias']))
    x = _pool(_convolution(x, weights['conv2.weight'], weights['conv2.bias']))
    x = np.maximum(weights['fc1.weight']@x.ravel()+weights['fc1.bias'], 0)
    return weights['fc2.weight']@x+weights['fc2.bias']


def classify_glyph(ink):
    """Return number/unknown plus raw score and margin including unknown class.

    ``scores`` keys are strings ("unknown", "2", ...). Empty or invalid input
    raises ValueError. Ordinary textual digits can be shape-identical to tuplets;
    this classifier alone cannot establish musical meaning.
    """
    model = _load_model()
    logits = glyph_logits(ink)
    order = np.argsort(logits)[::-1]
    label = model['labels'][int(order[0])]
    score, margin = float(logits[order[0]]), float(logits[order[0]]-logits[order[1]])
    gate = model['gates'].get(label)
    unknown = label == 'unknown' or gate is None or score < gate['score'] or margin < gate['margin']
    return {'number': None if unknown else int(label), 'unknown': unknown,
            'score': score, 'margin': margin,
            'scores': {key: float(value) for key, value in zip(model['labels'], logits)}}
