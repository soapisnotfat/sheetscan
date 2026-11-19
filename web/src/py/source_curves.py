"""Locate printed curves using independently attached noteheads."""
import cv2
import numpy as np


def _curve_ink(image, left, top, right, bottom, unit):
    if left < 0 or top < 0 or right > image.shape[1] or bottom > image.shape[0]:
        return None
    pad = round(3 * unit)
    wide = image[top:bottom, max(left - pad, 0):right + pad]
    ink = (cv2.cvtColor(wide, cv2.COLOR_BGR2GRAY) if wide.ndim == 3 else wide) < 160
    staff_rows = ink.mean(axis=1) > .76
    offset = min(pad, left)
    crop = ink[:, offset:offset + right - left].copy()
    crop[staff_rows] = False
    return crop


def read_grace_slur(image, start, stop, unit):
    """Return an arc anchored outside the two heads, or leave the reading alone.

    Ties can also be long or curved. Require ink near the first head's centre,
    separated from both heads vertically, with the bow between the endpoints.
    Normalise the dimensions by the printed staff spacing.
    """
    x_start, y_start = start
    x_stop, y_stop = stop
    if (unit < 6 or not 1.15 * unit <= x_stop - x_start <= 4 * unit
            or abs(y_stop - y_start) > .25 * unit):
        return None

    y = (y_start + y_stop) / 2
    left = round(x_start - .58 * unit)
    right = round(x_stop + .58 * unit) + 1
    top = round(y - 2.65 * unit)
    bottom = round(y + 2.65 * unit) + 1
    crop = _curve_ink(image, left, top, right, bottom, unit)
    if crop is None:
        return None
    rows = np.arange(top, bottom)
    kernel = np.ones((max(3, round(.21 * unit) | 1), 1), np.uint8)
    candidates = []
    for sign in (-1, 1):
        side = crop & ((rows[:, None] - y) * sign >= round(.55 * unit))
        mask = cv2.morphologyEx(side.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
        _, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        for index, component in enumerate(stats[1:], 1):
            x, row, width, height, _ = map(int, component)
            x_left, x_right = left + x, left + x + width - 1
            if (abs(x_left - x_start) > .25 * unit
                    or not -.99 * unit <= x_right - x_stop <= .30 * unit
                    or width < .58 * (x_stop - x_start) or height > 1.1 * unit):
                continue
            ys, xs = np.nonzero((labels == index) & side)
            span = (xs - x) / width
            regions = (span <= .21, (span >= .42) & (span <= .58), span >= .79)
            if not all(region.any() for region in regions):
                continue
            start_height, middle, stop_height = [
                float(np.median((ys[region] + top - y) * sign)) / unit for region in regions
            ]
            if (min(start_height, stop_height) >= .72
                    and (start_height + stop_height) / 2 >= .83
                    and middle - (start_height + stop_height) / 2 >= .10):
                candidates.append({
                    'box': [x_left, top + row, x_right + 1, top + row + height],
                    'side': 'above' if sign < 0 else 'below',
                })
    return candidates[0] if len(candidates) == 1 else None


def read_ordinary_curve(image, start, stop, unit):
    """Distinguish an inner tie from a higher slur that reaches the note centres."""
    x_start, y_start = start
    x_stop, y_stop = stop
    distance = x_stop - x_start
    if (unit < 6 or not 2.55 * unit <= distance <= 9 * unit
            or abs(y_stop - y_start) > .25 * unit):
        return None

    y = (y_start + y_stop) / 2
    left, right = round(x_start - .9 * unit), round(x_stop + .9 * unit) + 1
    top, bottom = round(y - 3.55 * unit), round(y + 3.55 * unit) + 1
    crop = _curve_ink(image, left, top, right, bottom, unit)
    if crop is None:
        return None
    rows = np.arange(top, bottom)
    kernel = np.ones((max(3, round(.21 * unit) | 1), 1), np.uint8)
    candidates = []
    for sign in (-1, 1):
        offsets = (rows - y) * sign
        side = crop & (offsets[:, None] >= max(1, .08 * unit))
        mask = cv2.morphologyEx(side.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
        _, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        for index, component in enumerate(stats[1:], 1):
            x, row, width, height, _ = map(int, component)
            x_left, x_right = left + x, left + x + width - 1
            if width < max(.43 * distance, 1.25 * unit) or row == 0 or row + height == len(rows):
                continue
            left_inset, right_inset = (x_left - x_start) / unit, (x_stop - x_right) / unit
            near, far = sorted((left_inset, right_inset))
            inside = .48 <= near and far <= 1.62 and height <= 1.10 * unit
            reaches_centres = (-.44 <= near and (far <= .76 or (near <= .30 and far <= 1.12))
                               and width >= .74 * distance and height <= 2.5 * unit)
            if not inside and not reaches_centres:
                continue
            ys, xs = np.nonzero((labels == index) & side)
            span = (xs - x) / (width - 1)
            regions = (span <= .20, (span > .20) & (span <= .40), (span > .40) & (span <= .60),
                       (span > .60) & (span <= .80), span > .80)
            if not all(region.any() for region in regions):
                continue
            start_height, left_arc, middle, right_arc, stop_height = [
                float(np.median(offsets[ys[region]])) / unit for region in regions
            ]
            low_tip, high_tip = sorted((start_height, stop_height))
            if middle - high_tip < .12 or left_arc < start_height + .03 or right_arc < stop_height + .03:
                continue
            if (inside and .18 <= low_tip and high_tip <= .76 and high_tip - low_tip <= .27
                    and middle <= 1.25 and max(left_arc, right_arc) <= middle + .08):
                curve = 'tie'
            elif (reaches_centres and 1.09 <= low_tip and high_tip <= 2.85
                    and high_tip - low_tip <= .75 and max(left_arc, right_arc) <= middle + .24):
                curve = 'slur'
            else:
                continue
            candidates.append({
                'curve': curve,
                'box': [x_left, top + row, x_right + 1, top + row + height],
                'side': 'above' if sign < 0 else 'below',
            })
    return candidates[0] if len(candidates) == 1 else None
