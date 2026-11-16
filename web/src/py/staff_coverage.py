"""Conservative source-pixel evidence for an accidentally clipped staff crop.

No score, filename, expected pitch or reference labels enter this module. The
window expands only when a raw segmented head at its edge has short ledger-line
support and neighbouring staffs stay excluded. It never discards existing source
pixels. The existing renderer still produces the same fixed-size encoder tensor.
"""
import math

import cv2
import numpy as np


def _ledger_lines(ink, x, y, reference, unit):
    direction = -1 if y < reference else 1
    distance = abs(y-reference)/unit
    found = []
    for step in range(1, int(math.ceil(distance))):
        row_y = reference+direction*step*unit
        # Avoid counting the notehead itself as a ledger line.
        if abs(row_y-y) < .55*unit:
            continue
        radius = max(1, round(.12*unit))
        a, b = max(0, round(row_y)-radius), min(len(ink), round(row_y)+radius+1)
        left, right = max(0, round(x-3*unit)), min(ink.shape[1], round(x+3*unit)+1)
        if a >= b or left >= right:
            continue
        row = ink[a:b, left:right].max(axis=0).astype(np.uint8)
        row = cv2.morphologyEx(row[None], cv2.MORPH_CLOSE,
                               np.ones((1, max(2, round(.2*unit))), np.uint8))[0]
        center = round(x)-left
        positions = [i for i in range(max(0, center-round(.2*unit)), min(len(row), center+round(.2*unit)+1)) if row[i]]
        if not positions:
            continue
        start = end = min(positions, key=lambda i: abs(i-center))
        while start and row[start-1]:
            start -= 1
        while end+1 < len(row) and row[end+1]:
            end += 1
        # Full neighbouring staff lines and long beams are not short ledgers.
        if 1.05*unit <= end-start+1 <= 2.8*unit:
            found.append({'y': round(row_y, 2), 'left': left+start, 'right': left+end})
    return found


def choose_staff_region(image, region, grid, raw_heads, assigned_heads=(), neighbours=()):
    """Return {box, changed, reason, evidence} using working-page coordinates.

    grid is [{x, y:[staff lines]}]; raw_heads are {center:[x,y],size:[w,h]}.
    Assigned heads alone cannot establish coverage: clipped high heads may never
    have been assigned to a staff. Neighbours are {top,bottom} core-line bounds.
    """
    box = [int(v) for v in region]
    result = {'box': box, 'changed': False, 'reason': 'no-source-clipping-evidence', 'evidence': []}
    if not grid or len(grid[0]['y']) < 5:
        return result
    xs = np.asarray([p['x'] for p in grid], float)
    ys = np.asarray([p['y'] for p in grid], float)
    unit = float(np.median(np.diff(ys[:, :5], axis=1)))
    if unit < 3:
        return result
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    ink = (gray < 160).astype(np.uint8)
    top, bottom = float(ys[:, 0].min()), float(ys[:, -1].max())
    candidates = {'above': [], 'below': []}
    for head in raw_heads:
        x, y = map(float, head['center'])
        width, height = map(float, head['size'])
        if not (box[0] < x < box[2] and .35*unit <= height <= 1.6*unit and .5*unit <= width <= 2.2*unit):
            continue
        side = ('above' if box[1]-2.5*unit <= y and y-height/2 <= box[1]+1 and y < top else
                'below' if y+height/2 >= box[3]-1 and y <= box[3]+2.5*unit and y > bottom else None)
        if side is None:
            continue
        local_top = float(np.interp(x, xs, ys[:, 0]))
        local_bottom = float(np.interp(x, xs, ys[:, -1]))
        distance = max(local_top-y, y-local_bottom, 0)
        # A head in the gap may be a low ledger note of the preceding staff.
        # Abstain at the midpoint too: proximity must favour this staff by a
        # half-space, independently of incomplete assigned-head membership.
        if any(max(other['top']-y, y-other['bottom'], 0) <= distance+.5*unit
               for other in neighbours):
            continue
        reference = float(np.interp(x, xs, ys[:, 0 if side == 'above' else -1]))
        ledgers = _ledger_lines(ink, x, y, reference, unit)
        if len(ledgers) >= 2:
            candidates[side].append({'center': [x, y], 'size': [width, height], 'ledgerLines': ledgers})
    result['evidence'] = [*candidates['above'], *candidates['below']]
    if not result['evidence']:
        return result
    above = math.ceil(max(0, box[1]-min((h['center'][1]-unit for h in candidates['above']), default=box[1])))
    below = math.ceil(max(0, max((h['center'][1]+unit for h in candidates['below']), default=box[3])-box[3]))
    if max(above, below) > 2.5*unit:
        result['reason'] = 'required-move-too-large'
        return result
    proposed = [box[0], max(0, box[1]-above), box[2], min(len(ink), box[3]+below)]
    if any((other['bottom'] < top and proposed[1] < other['bottom']+.5*unit)
           or (other['top'] > bottom and proposed[3] > other['top']-.5*unit) for other in neighbours):
        result['reason'] = 'neighbour-staff-protected'
        return result
    # Low notes, grand-staff bass, clefs and text already in the old crop are
    # retained verbatim. No conclusion relies on assigned-head completeness.
    result.update(box=proposed, changed=proposed != box, reason='source-ledger-head-clipping-expansion',
                  paddingPixels={'above': box[1]-proposed[1], 'below': proposed[3]-box[3]}, discardedInkPixels=0)
    return result
