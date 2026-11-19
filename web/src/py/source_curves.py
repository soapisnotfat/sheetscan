"""Locate a printed grace slur using independently attached noteheads."""
import cv2
import numpy as np


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
    if left < 0 or top < 0 or right > image.shape[1] or bottom > image.shape[0]:
        return None
    pad = round(3 * unit)
    wide = image[top:bottom, max(left - pad, 0):right + pad]
    ink = (cv2.cvtColor(wide, cv2.COLOR_BGR2GRAY) if wide.ndim == 3 else wide) < 160
    staff_rows = ink.mean(axis=1) > .76
    offset = min(pad, left)
    crop = ink[:, offset:offset + right - left].copy()
    crop[staff_rows] = False
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
