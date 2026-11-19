"""Export beam connections proved by the printed image."""
from bisect import bisect_left, bisect_right
from collections import defaultdict
import re
import xml.etree.ElementTree as ET
from beam_evidence import has_secondary_hook


_BEAM_LEVELS = {'eighth': 1, '16th': 2, '32nd': 3, '64th': 4}
_NOTE_ID = re.compile(r'-p(\d+)-(\d+)-(\d+)$')


def _point(note, page):
    at = _NOTE_ID.search(note.get('id', ''))
    if at and int(at[1]) == page:
        return int(at[2]), int(at[3])
    return None


def _events(score, page):
    lanes, heads = defaultdict(list), []
    for part in score.findall('part'):
        for measure in part.findall('measure'):
            for note in measure.findall('note'):
                if note.get('print-object') == 'no':
                    continue
                grace = note.find('grace') is not None
                key = (measure, note.findtext('voice', '1'), note.findtext('staff', '1'), grace)
                lane = lanes[key]
                if not lane or note.find('chord') is None:
                    lane.append([])
                lane[-1].append(note)
                position = _point(note, page)
                if position and note.find('pitch') is not None:
                    heads.append((*position, key, len(lane) - 1, note))
    heads.sort(key=lambda head: head[0])
    return lanes, heads


def _stem_event(stem, heads, unit, lanes):
    matches = []
    for head in stem['heads']:
        x, y = head['center']
        left = bisect_left(heads, x - .40 * unit, key=lambda note: note[0])
        right = bisect_right(heads, x + .40 * unit, key=lambda note: note[0])
        nearby = [(key, index, note) for _, py, key, index, note in heads[left:right]
                  if abs(py - y) <= .35 * unit]
        if len(nearby) != 1:
            return None
        matches.append(nearby[0])
    if not matches:
        return None
    lane, index, _ = matches[0]
    if (any(key != lane or member != index for key, member, _ in matches)
            or {note for _, _, note in matches} != set(lanes[lane][index])):
        return None
    return lane, index


def _fits_beam(event, levels):
    return all(note.find('beam') is None and _BEAM_LEVELS.get(note.findtext('type'), 0) >= levels
               for note in event)


def apply_source_beams(score, page, groups, boxes, ink):
    """Bind printed stem-to-stem paths to consecutive written events.

    A source beam may span a printed rest. The rest must be in the same lane
    and its source location must be between the two stems.
    """
    if not groups:
        return []
    lanes, heads = _events(score, page)
    edges = defaultdict(dict)
    hooks = defaultdict(set)
    evidence = []
    for group in groups:
        _, top, _, bottom, _ = boxes[group['staff']]
        unit = (bottom - top) / 4
        stems = group['stems']
        bindings = [_stem_event(stem, heads, unit, lanes) for stem in stems]
        for i, connection in enumerate(group['connections']):
            a, b = bindings[i:i + 2]
            if a is None or b is None or a[0] != b[0] or a[1] >= b[1]:
                continue
            key, first = a
            last = b[1]
            lane = lanes[key]
            level_count = connection['count']
            if not all(_fits_beam(event, level_count) for event in lane[first:last + 1]):
                continue
            between = []
            for event in lane[first + 1:last]:
                note = event[0]
                position = _point(note, page)
                if (len(event) == 1 and note.find('rest') is not None and position
                        and stems[i]['x'] < position[0] < stems[i + 1]['x']):
                    between.append(note)
            if len(between) != last - first - 1:
                continue
            for index in range(first, last):
                edges[key][index] = level_count
            evidence.append({
                'from': lane[first][0].get('id'), 'to': lane[last][0].get('id'),
                'levels': level_count, 'source': [connection['from'], connection['to']],
            })
            for index, stem, neighbor, direction in (
                (first, stems[i], stems[i + 1], 'forward hook'),
                (last, stems[i + 1], stems[i], 'backward hook'),
            ):
                if _fits_beam(lane[index], 2) and has_secondary_hook(ink, stem, neighbor, connection, unit):
                    hooks[(key, index)].add(direction)

    for key, connections in edges.items():
        for index, event in enumerate(lanes[key]):
            left, right = connections.get(index - 1, 0), connections.get(index, 0)
            for level in range(1, max(left, right) + 1):
                beam = ET.SubElement(event[0], 'beam', number=str(level))
                if level <= min(left, right):
                    beam.text = 'continue'
                else:
                    beam.text = 'begin' if level <= right else 'end'
            directions = hooks.get((key, index), ())
            if max(left, right) == 1 and len(directions) == 1:
                direction = next(iter(directions))
                ET.SubElement(event[0], 'beam', number='2').text = direction
                evidence.append({'note': event[0].get('id'), 'level': 2, 'kind': direction})
    return evidence
