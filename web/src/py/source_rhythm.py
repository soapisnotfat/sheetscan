"""Source-verified duplets before heuristic triplet restoration.

The recognizer vocabulary has no direct 2:3 rhythm token. Independent printed 2,
source beam/stem/head geometry and a printed meter bind an existing pair of
attacks. The complete measure must then fit in every voice; otherwise it is left
unchanged. Pitches, lifts, notes and rests are never inserted or removed here.
"""
import copy
import math
import re
from fractions import Fraction

from beam_evidence import read_beam_groups
from score_numbers import read_meters
from printed_tuplets import read_tuplet_marks
from homr.transformer.vocabulary import SymbolDuration, sort_token_chords

_NOTE = re.compile(r'note_(8|16|32)(\.*)$')
_PITCH = re.compile(r'([A-G])(\d+)$')
_BEAMS = {'beamStart', 'beamContinue', 'beamStop'}


def source_geometry(rows, raw_heads, to_input):
    boxes, descriptors, grids, staff_map = [], [], [], {}
    for system, row in enumerate(rows):
        for slot, staff in enumerate(row.staffs):
            first, last = staff.grid[0], staff.grid[-1]
            lanes = {}
            for k in range(0, len(first.y)-4, 5):
                left, top = to_input((first.x, first.y[k]))
                right, bottom = to_input((last.x, first.y[k+4]))
                lane = 'lower' if k else 'upper'
                lanes[lane] = len(boxes)
                descriptors.append({'system': system, 'slot': slot, 'lane': lane})
                boxes.append([round(left), round(top), round(right), round(bottom), system])
            staff_map[id(staff)] = lanes
            grids.append({'grid': [{'x': float(to_input((p.x, p.y[0]))[0]),
                                    'y': [float(to_input((p.x, y))[1]) for y in p.y]}
                                   for p in staff.grid]})
    heads = []
    for head in raw_heads:
        x, y = head['center']
        w, h = head['size']
        a, b = to_input((x, y))
        c, d = to_input((x+w, y+h))
        heads.append({'center': [float(a), float(b)], 'size': [float(c-a), float(d-b)], 'angle': head.get('angle', 0)})
    return boxes, descriptors, staff_map, grids, heads


def prepare_context(image, rows, raw_heads, to_input, page):
    boxes, descriptors, staff_map, grids, heads = source_geometry(rows, raw_heads, to_input)
    return {'page': page, 'boxes': boxes, 'descriptors': descriptors, 'rawSymbols': [],
            'staffMap': staff_map, 'toInput': to_input, 'rawHeads': heads,
            'meters': read_meters(image, boxes),
            'tuplets': read_tuplet_marks(image, boxes),
            'beams': read_beam_groups(image, grids, heads), 'changes': [], 'diagnostics': []}


def mark_staff(symbols, staff, context):
    lanes = context['staffMap'].get(id(staff), {})
    clefs = {}
    for symbol in symbols:
        lane = 'lower' if symbol.position.startswith('lower') else 'upper'
        symbol._source_staff = lanes.get(lane)
        clef = re.fullmatch(r'clef_([GFC])([1-5])', symbol.rhythm)
        if clef:
            reference = {'G': 4*7+4, 'F': 3*7+3, 'C': 4*7}[clef[1]]
            clefs[lane] = reference-2*(int(clef[2])-1)
        symbol._source_clef_offset = clefs.get(lane)


def _meter(context, staff, x):
    descriptor = context['descriptors'][staff]
    choices = []
    for mark in context['meters']:
        candidate = context['descriptors'][mark['staff']]
        if (candidate['slot'] != descriptor['slot'] or candidate['lane'] != descriptor['lane']
                or candidate['system'] > descriptor['system']
                or candidate['system'] == descriptor['system'] and mark['x'] > x):
            continue
        choices.append((candidate['system'], mark['x'], mark))
    if not choices:
        return None
    mark = max(choices, key=lambda item: item[:2])[2]
    return mark['numerator'], mark['denominator']


def _event_match(notes, source_event, context, staff, written, allow_triplet=False):
    heads = sorted(source_event['heads'], key=lambda h: h['staffPosition'])
    if len(notes) != len(heads) or not heads or any(h.get('positionResidual', 1) > .3 for h in heads):
        return None
    pitches = []
    for symbol in notes:
        match = _PITCH.fullmatch(symbol.pitch)
        base = _NOTE.fullmatch(symbol.rhythm)
        triplet = (allow_triplet and symbol.rhythm.startswith('note_')
                   and symbol.get_duration().kern == written and symbol.get_duration().dots == 0
                   and (symbol.get_duration().actual_notes, symbol.get_duration().normal_notes) in ((1,1),(3,2)))
        if (match is None or not (base is not None and int(base[1]) == written and not base[2] or triplet)
                or getattr(symbol, '_source_staff', None) != staff
                or symbol.image_coordinates is None):
            return None
        pitches.append((int(match[2])*7+'CDEFGAB'.index(match[1]), symbol))
    pitches.sort(key=lambda item: item[0])
    if len({h['staffPosition'] for h in heads}) != len(heads):
        return None
    offsets = {pitch-head['staffPosition'] for (pitch, _), head in zip(pitches, heads)}
    if len(offsets) != 1:
        return None
    unit = (context['boxes'][staff][3]-context['boxes'][staff][1])/4
    points = [context['toInput'](symbol.image_coordinates) for _, symbol in pitches]
    distances = [math.dist(point, head['center']) for point, head in zip(points, heads)]
    # Relative intervals alone can bind a descending pair to the next two
    # decoded notes. Require the decoded clef and physical staff to identify
    # every source pitch absolutely. Vertical attention is unreliable even
    # for correct notes (it may land between staves), so attention only limits
    # horizontal location after this independent source-pitch verification.
    # Missing, octave-shifted or unsupported clefs deliberately abstain.
    expected = {getattr(symbol, '_source_clef_offset', None) for _, symbol in pitches}
    if (None in expected or expected != offsets
            or max(abs(point[0]-head['center'][0]) for point, head in zip(points, heads)) > 2*unit):
        return None
    return next(iter(offsets)), max(distances)/unit


def _beam_state(notes):
    states = {piece for symbol in notes for piece in symbol.slur.split('_') if piece in _BEAMS}
    return next(iter(states)) if len(states) == 1 else None


def _parts(symbols):
    chunks, current = [], []
    for symbol in symbols:
        if any(word in symbol.rhythm for word in ('barline', 'repeat', 'newline')):
            if current:
                chunks.append(current)
                current = []
        else:
            current.append(symbol)
    if current:
        chunks.append(current)
    return chunks



def _continuous_serialization(chunk, chosen, budget):
    """Simulate the generator's earliest-sounding-end chord timeline.

    Independent voice totals alone cannot prove an interleaved sequence: a
    misplaced raw chord marker can shift onsets despite equal final totals.
    No source order, missing attack or rest is invented to repair that sequence.
    """
    clock, sounding, ends = Fraction(), [], {}
    for chord in sort_token_chords(chunk):
        durations = {}
        for symbol in chord:
            if not symbol.rhythm.startswith(('note', 'rest')):
                continue
            proposal = chosen.get(id(symbol))
            duration = (Fraction(proposal['normal'], proposal['actual']*proposal['written'])
                        if proposal else symbol.get_duration().fraction)
            if duration > 0:
                durations[symbol.position] = max(duration, durations.get(symbol.position, Fraction()))
        if not durations:
            continue
        for position, duration in durations.items():
            if position in ends and ends[position] != clock:
                return False
            ends[position] = clock+duration
        sounding.extend(clock+duration for duration in durations.values())
        clock = min(end for end in sounding if end > clock)
        sounding = [end for end in sounding if end > clock]
    return bool(ends) and all(end == budget for end in ends.values())


def constrain(symbols, context):
    """Return copied symbols only after all source-backed changes fit each voice."""
    replacements = {}
    index = {id(symbol): i for i, symbol in enumerate(symbols)}
    context.setdefault('rawSymbols', []).append([{'rhythm':s.rhythm,'pitch':s.pitch,'position':s.position,'staff':getattr(s,'_source_staff',None),'imageCoordinates':list(context['toInput'](s.image_coordinates)) if s.image_coordinates is not None else None} for s in symbols])
    for measure_index, chunk in enumerate(_parts(symbols), 1):
        voices = {}
        for chord in sort_token_chords(chunk):
            by_position = {}
            for symbol in chord:
                if symbol.rhythm.startswith(('note', 'rest')):
                    by_position.setdefault(symbol.position, []).append(symbol)
            for position, notes in by_position.items():
                voices.setdefault(position, []).append(notes)
        proposals = []
        for group in context['beams']:
            if group.get('eventCount') != 2 or group['beamCount'] not in (1, 2, 3):
                continue
            staff = group['staff']
            stems = group['stems']
            first_x, last_x = stems[0]['x'], stems[-1]['x']
            marks = [mark for mark in context['tuplets'] if mark['staff'] == staff
                     and mark['number'] == 2 and first_x <= mark['x'] <= last_x]
            if len(marks) != 1:
                continue
            mark = marks[0]
            meter = _meter(context, staff, first_x)
            if meter is None or meter[0] % 3 or meter[1] not in (8, 16):
                continue
            written = 2**(group['beamCount']+2)
            candidates = []
            for position, events in voices.items():
                for before, after in zip(events, events[1:]):
                    a = _event_match(before, stems[0], context, staff, written)
                    b = _event_match(after, stems[1], context, staff, written)
                    if a is None or b is None or a[0] != b[0]:
                        continue
                    first_beam, last_beam = _beam_state(before), _beam_state(after)
                    if ((first_beam is not None or last_beam is not None)
                            and (first_beam, last_beam) != ('beamStart', 'beamStop')):
                        continue
                    candidates.append({'notes': before+after, 'events': [before, after], 'sourceEvents': stems,
                                       'actual': 2, 'normal': 3, 'position': position,
                                       'written': written, 'meter': meter,
                                       'evidence': mark, 'beamCount': group['beamCount'],
                                       'staff': staff, 'offset': a[0],
                                       'maxAttentionDistanceUnits': max(a[1], b[1])})
            if len(candidates) == 1:
                proposals.append(candidates[0])
        if not proposals:
            continue
        # A complete source duplet beat can prove that the opposite three
        # equally beamed attacks are plain, even if the decoder already guessed
        # them as triplets. This is narrower than globally removing triplets:
        # every event must map to source heads, the full printed beat must fit,
        # and cross-staff horizontal onset order must agree independently.
        counterpart = []
        for position, events in voices.items():
            if any(p['position'] == position for p in proposals) or len(events) != 3:
                continue
            candidates = []
            for source_group in context['beams']:
                if source_group.get('eventCount') != 3:
                    continue
                written = 2**(source_group['beamCount']+2)
                parents = [p for p in proposals if p['written'] == written
                           and Fraction(3, written) == Fraction(p['meter'][0], p['meter'][1])]
                if not parents:
                    continue
                staff = source_group['staff']
                source_events = source_group['stems']
                matches = [_event_match(event, source_event, context, staff, written, True)
                           for event, source_event in zip(events, source_events)]
                if any(match is None for match in matches) or len({m[0] for m in matches}) != 1:
                    continue
                left, right = source_events[0]['x'], source_events[-1]['x']
                if any(m['staff'] == staff and left <= m['x'] <= right
                       for m in context['tuplets']):
                    continue
                candidates.append({'notes': [n for event in events for n in event],
                    'events': events, 'sourceEvents': source_events, 'actual': 1, 'normal': 1,
                    'position': position, 'written': written, 'meter': parents[0]['meter'],
                    'evidence': parents[0]['evidence'], 'beamCount': source_group['beamCount'],
                    'staff': staff, 'offset': matches[0][0],
                    'maxAttentionDistanceUnits': max(m[1] for m in matches),
                    'counterpart': True})
            if len(candidates) == 1:
                counterpart.extend(candidates)
        proposals.extend(counterpart)
        chosen = {}
        for proposal in proposals:
            for symbol in proposal['notes']:
                if id(symbol) in chosen:
                    break
                chosen[id(symbol)] = proposal
            else:
                continue
            chosen = {}
            break
        meters = {proposal['meter'] for proposal in proposals}
        if not chosen or len(meters) != 1:
            continue
        numerator, denominator = next(iter(meters))
        budget = Fraction(numerator, denominator)
        totals = {}
        for position, events in voices.items():
            total = Fraction()
            for event in events:
                values = []
                for symbol in event:
                    proposal = chosen.get(id(symbol))
                    value = (Fraction(proposal['normal'], proposal['actual']*proposal['written']) if proposal
                             else symbol.get_duration().fraction)
                    values.append(value)
                total += max(values, default=Fraction())
            totals[position] = total
        diagnostic = {'page': context['page'], 'measureInVoice': measure_index,
                      'sourceMeter': [numerator, denominator],
                      'voiceTotalsWholeNotes': {key: str(value) for key, value in totals.items()},
                      'proposedGroups': len(proposals)}
        if not totals or any(total != budget for total in totals.values()):
            context['diagnostics'].append({**diagnostic, 'status': 'unknown-incomplete-voice-budget'})
            continue
        if not _continuous_serialization(chunk, chosen, budget):
            context['diagnostics'].append({**diagnostic, 'status': 'inconsistent-global-chord-timeline'})
            continue
        if counterpart:
            anchors = {}
            for proposal in proposals:
                for event, source_event in zip(proposal['events'], proposal['sourceEvents']):
                    anchors[id(event[0])] = (sum(h['center'][0] for h in source_event['heads'])
                                             / len(source_event['heads']), proposal['staff'])
            clocks = []
            complete = True
            for position, events in voices.items():
                clock = Fraction()
                for event in events:
                    anchor = anchors.get(id(event[0]))
                    if anchor is None:
                        complete = False
                        break
                    clocks.append((position, clock, anchor[0], anchor[1]))
                    clock += max(Fraction(chosen[id(n)]['normal'], chosen[id(n)]['actual']*chosen[id(n)]['written'])
                                 if id(n) in chosen else n.get_duration().fraction for n in event)
            contradicts = False
            for i, a in enumerate(clocks):
                for b in clocks[i+1:]:
                    if a[0] == b[0]:
                        continue
                    unit = min((context['boxes'][si][3]-context['boxes'][si][1])/4 for si in (a[3],b[3]))
                    if abs(a[2]-b[2]) <= .8*unit:
                        continue
                    if a[1] == b[1] or (a[1] < b[1]) != (a[2] < b[2]):
                        contradicts = True
            if not complete or contradicts:
                context['diagnostics'].append({**diagnostic, 'status': 'source-onset-order-unknown-or-contradictory'})
                continue
        for proposal in proposals:
            changed = []
            for symbol in proposal['notes']:
                before = symbol.get_duration()
                target = SymbolDuration(Fraction(1, proposal['written']), 0, proposal['actual'], proposal['normal'], proposal['written'])
                if (before.fraction, before.actual_notes, before.normal_notes, before.dots) == (
                        target.fraction, target.actual_notes, target.normal_notes, target.dots):
                    continue
                replacement = copy.copy(symbol)
                replacement._duration = target
                replacements[id(symbol)] = replacement
                changed.append({'modelIndex': index[id(symbol)], 'pitch': symbol.pitch,
                                'position': symbol.position, 'rhythm': symbol.rhythm,
                                'fromWholeNotes': str(before.fraction),
                                'toWholeNotes': str(target.fraction)})
            if changed:
                context['changes'].append({**diagnostic, 'kind': 'source-duplet-before-codec',
                    'staff': proposal['staff'], 'evidence': proposal['evidence'],
                    'beamCount': proposal['beamCount'], 'actual': proposal['actual'], 'normal': proposal['normal'],
                    'sourceOnsetOrderChecked': bool(counterpart),
                    'maxAttentionDistanceUnits': proposal['maxAttentionDistanceUnits'], 'edits': changed})
    return [replacements.get(id(symbol), symbol) for symbol in symbols]
