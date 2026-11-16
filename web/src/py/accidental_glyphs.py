# SPDX-License-Identifier: OFL-1.1
"""Accidental shape evidence and conservative head-adjacent CV proposals.

No pitch or measure-state changes occur here. A key-signature glyph is visually
identical to the same local accidental; the caller must establish its context.
The CNN scores are raw logits, not calibrated confidence probabilities.
"""
import base64
import json
from pathlib import Path

import cv2
import numpy as np

_MODEL = None


def normalize_ink(ink):
    ink = np.asarray(ink, np.float32)
    if ink.ndim != 2 or not ink.size or not np.isfinite(ink).all():
        raise ValueError('Expected finite nonempty two-dimensional foreground ink')
    if ink.max() > 1.5:
        ink = ink/255.
    return cv2.resize(np.clip(ink, 0, 1), (24, 32), interpolation=cv2.INTER_AREA)


def _load_model():
    global _MODEL
    if _MODEL is None:
        _MODEL = json.loads(Path(__file__).with_name('accidental_classifier.json').read_text())
        for key, item in list(_MODEL['weights'].items()):
            _MODEL['weights'][key] = np.frombuffer(base64.b64decode(item['data']), '<f2').astype(np.float32).reshape(item['shape'])
    return _MODEL


def _conv(x, weight, bias):
    height, width = x.shape[1:]
    radius = weight.shape[-1]//2
    padded = np.pad(x, ((0,0),(radius,radius),(radius,radius)))
    out = np.broadcast_to(bias[:,None,None], (len(bias),height,width)).copy()
    for dy in range(weight.shape[-2]):
        for dx in range(weight.shape[-1]):
            out += np.einsum('oc,chw->ohw', weight[:,:,dy,dx], padded[:,dy:dy+height,dx:dx+width], optimize=True)
    return np.maximum(out, 0)


def _pool(x):
    c,h,w = x.shape
    return x.reshape(c,h//2,2,w//2,2).max(axis=(2,4))


def accidental_logits(ink):
    w = _load_model()['weights']
    x = normalize_ink(ink)[None]
    x = _pool(_conv(x, w['conv1.weight'], w['conv1.bias']))
    x = _pool(_conv(x, w['conv2.weight'], w['conv2.bias']))
    x = np.maximum(w['fc1.weight']@x.ravel()+w['fc1.bias'], 0)
    return w['fc2.weight']@x+w['fc2.bias']


def classify_accidental(ink):
    model = _load_model()
    logits = accidental_logits(ink)
    order = np.argsort(logits)[::-1]
    kind = model['labels'][int(order[0])]
    score, margin = float(logits[order[0]]), float(logits[order[0]]-logits[order[1]])
    gate = model['gates'].get(kind)
    unknown = gate is None or kind == 'unknown' or score < gate['score'] or margin < gate['margin']
    return {'kind': None if unknown else kind, 'unknown': unknown, 'score': score, 'margin': margin,
            'scores': {label: float(value) for label,value in zip(model['labels'], logits)}}


def accidental_candidates(image, staff_boxes, heads):
    """Return untyped evidence crops from original pixels and segmented heads.

    staff_boxes: [left, top-line, right, bottom-line, ...], in image pixels.
    heads: dictionaries {staff, center:[x,y], position}, from segmentation, never
    transformer attention. Each result has box, head_index, position and ink.
    Candidates may include key signatures/stems and require type/context checks.
    """
    gray = cv2.cvtColor(image,cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    found = []
    for staff_index, box in enumerate(staff_boxes):
        left,top,right,bottom = box[:4]
        unit = (bottom-top)/4
        if unit < 2:
            continue
        x0,x1 = max(0,round(left)),min(gray.shape[1],round(right))
        y0,y1 = max(0,round(top-3*unit)),min(len(gray),round(bottom+3*unit))
        ink = (gray[y0:y1,x0:x1] < 160).astype(np.uint8)
        lines = cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,max(12,round(7*unit))),np.uint8))
        clean = cv2.morphologyEx(ink-lines,cv2.MORPH_CLOSE,np.ones((3,1),np.uint8))
        _,labels,stats,_ = cv2.connectedComponentsWithStats(clean)
        for label,(x,y,w,h,area) in enumerate(stats[1:],1):
            if not (.8*unit <= h <= 4.5*unit and .12*unit <= w <= 2.3*unit and area >= 6):
                continue
            cx,cy = x0+x+w/2,y0+y+h/2
            choices = []
            for index,head in enumerate(heads):
                if head['staff'] != staff_index:
                    continue
                hx,hy = head['center']
                if .45*unit <= hx-cx <= 2.9*unit and abs(hy-cy) <= 1.2*unit and x0+x+w < hx-.25*unit:
                    choices.append((hx-cx+abs(hy-cy),index))
            if not choices:
                continue
            _,index = min(choices)
            found.append({'staff': staff_index, 'box': [x0+int(x),y0+int(y),x0+int(x+w),y0+int(y+h)],
                          'head_index': index, 'position': int(heads[index]['position']),
                          'ink': (labels[y:y+h,x:x+w] == label).astype(np.float32)})
    return found


def read_accidentals(image, staff_boxes, heads):
    """Return JSON-safe typed/unknown proposals in original input pixels.

    ``heads`` dictionaries require staff (index into staff_boxes), center [x,y],
    and position (segmentation staff position); optional id is carried as
    head_id. head_index always indexes the exact supplied heads list. Unknown
    candidates remain in the result for coverage/abstention auditing. No note
    pitch, key signature, accidental state or score XML is consulted or changed.
    """
    result=[]
    for candidate in accidental_candidates(image,staff_boxes,heads):
        ink=candidate.pop('ink')
        candidate.update(classify_accidental(ink))
        left,top,right,bottom=candidate['box']
        candidate['center']=[(left+right)/2,(top+bottom)/2]
        candidate['head_id']=heads[candidate['head_index']].get('id')
        result.append(candidate)
    return result
