"""Independent qualification layer; frozen practice-v2 event denominator is unchanged.

Checks inherited key/clef/transposition, octave spans and navigation controls at
original musical locations. Optional beaming fidelity is reported separately.
This is a scoped qualification, not a claim to cover every MusicXML feature.

References: https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/sound/
https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/key/
https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/octave-shift/
"""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from practice_metrics import compare as core_compare, passes as core_passes

VERSION = 'qualification-v1'


def _key(node):
    # Compare effective alterations, not major/minor prose or signature layout.
    alterations = {step: Fraction() for step in 'CDEFGAB'}
    if node.find('fifths') is not None:
        fifths = int(node.findtext('fifths'))
        order = 'FCGDAEB' if fifths >= 0 else 'BEADGCF'
        for index in range(abs(fifths)):
            alterations[order[index % 7]] += 1 if fifths >= 0 else -1
    else:
        entries, step = [], None
        for child in node:
            if child.tag == 'key-step':
                step = child.text
            elif child.tag == 'key-alter' and step is not None:
                entries.append((step, Fraction(child.text))); step = None
        if not entries or len({step for step, _ in entries}) != len(entries):
            raise ValueError('unsupported missing/repeated nontraditional key steps')
        alterations.update(entries)
    return tuple(sorted(alterations.items()))


def _clef(node):
    sign = node.findtext('sign')
    line = node.findtext('line', {'G': '2', 'F': '4', 'C': '3'}.get(sign))
    return (sign, line, int(node.findtext('clef-octave-change', '0')))


def _time_only(node, default):
    return tuple(sorted({int(n.strip()) for n in node.get('time-only', default).split(',')}))


def _words(text):
    # Deliberately bounded vocabulary; do not silently interpret arbitrary prose.
    text = re.sub(r'\s+', ' ', text.strip().lower().replace('.', ''))
    if re.search(r'\b(dc|da capo)\b', text):
        return 'dacapo'
    if re.search(r'\b(ds|dal segno)\b', text):
        return 'dalsegno'
    if re.fullmatch(r'(to|al) coda', text):
        return 'tocoda'
    if text == 'fine':
        return 'fine'
    if text in ('segno', '𝄋'):
        return 'segno'
    if text in ('coda', '𝄌'):
        return 'coda'
    return None


def read(root):
    if root.tag != 'score-partwise' or not root.findall('part'):
        raise ValueError('Expected nonempty score-partwise MusicXML')
    headers, beams, shifts, controls = {}, Counter(), Counter(), []
    issues, markers = [], defaultdict(list)
    for pi, part in enumerate(root.findall('part')):
        staves = {'1'} | {n.text for n in part.findall('.//note/staff') if n.text}
        for node in part.findall('.//attributes/staves'):
            staves.update(str(i+1) for i in range(int(node.text)))
        # An omitted initial key/clef is not assumed to agree with printed GT.
        # Unknown defaults are explicit and cannot qualify against known context.
        state = {s: {'key': None, 'clef': None, 'transpose': Fraction()} for s in staves}
        timeline = defaultdict(dict); active_shifts = {}; divisions = 1
        for mi, measure in enumerate(part.findall('measure')):
            cursor, previous = Fraction(), Fraction()
            for s in staves:
                timeline[(pi, mi, s)][Fraction()] = dict(state[s])
            for item in measure:
                if item.tag == 'attributes':
                    divisions = int(item.findtext('divisions', str(divisions)))
                    for tag, parser in [('key', _key), ('clef', _clef),
                                        ('transpose', lambda n: Fraction(n.findtext('chromatic', '0')) + 12*int(n.findtext('octave-change', '0')))]:
                        for node in item.findall(tag):
                            targets = [node.get('number')] if node.get('number') else (['1'] if tag == 'clef' else staves)
                            if node.get('print-object') == 'no' and tag != 'transpose':
                                issues.append(f'unobservable hidden {tag} at part {pi+1} bar {mi+1}')
                            try:
                                value = parser(node)
                            except (ValueError, TypeError) as error:
                                issues.append(f'unsupported {tag} at part {pi+1} bar {mi+1}: {error}')
                                value = ('unsupported',)
                            if tag == 'key' and node.find('fifths') is None and node.find('key-octave') is not None:
                                issues.append(f'unsupported octave-specific nontraditional key at part {pi+1} bar {mi+1}')
                            if tag == 'transpose' and node.find('double') is not None:
                                issues.append(f'unsupported doubled transposition at part {pi+1} bar {mi+1}')
                            for staff in targets:
                                state[staff][tag] = value
                                timeline[(pi, mi, staff)][cursor] = dict(state[staff])
                elif item.tag in ('backup', 'forward'):
                    cursor += Fraction(item.findtext('duration', '0'))/divisions * (-1 if item.tag == 'backup' else 1)
                elif item.tag == 'note':
                    onset = previous if item.find('chord') is not None else cursor
                    duration = Fraction(item.findtext('duration', '0'))/divisions
                    staff, voice = item.findtext('staff', '1'), item.findtext('voice', '1')
                    pitch = item.find('pitch')
                    value = None if pitch is None else (pitch.findtext('step'), Fraction(pitch.findtext('alter', '0')), pitch.findtext('octave'))
                    for beam in item.findall('beam'):
                        beams[(pi, mi, voice, staff, onset, duration, value, int(beam.get('number', '1')), beam.text)] += 1
                    if item.find('chord') is None and item.find('grace') is None:
                        previous, cursor = cursor, cursor+duration
                elif item.tag in ('direction', 'sound', 'barline'):
                    offset = Fraction(item.findtext('offset', '0'))/divisions
                    staff = item.findtext('staff', '1')
                    position = (pi, mi, Fraction() if item.tag == 'barline' and item.get('location') == 'left' else cursor+offset)
                    for node in item.findall('.//octave-shift'):
                        ident = (staff, node.get('number', '1')); typ = node.get('type')
                        if typ in ('up', 'down'):
                            if ident in active_shifts:
                                issues.append(f'overlapping octave-shift label {ident} at {position}')
                            active_shifts[ident] = (position, typ, int(node.get('size', '8')))
                        elif typ == 'stop':
                            if ident not in active_shifts:
                                issues.append(f'orphan octave-shift stop at {position}')
                            else:
                                start, direction, size = active_shifts.pop(ident)
                                shifts[(pi, staff, start, position, direction, size)] += 1
                        elif typ == 'continue' and ident not in active_shifts:
                            issues.append(f'orphan octave-shift continuation at {position}')
                    sounds = [item] if item.tag == 'sound' else item.findall('sound')
                    present = set()
                    for sound in sounds:
                        sound_position = (pi, mi, cursor+Fraction(sound.findtext('offset', item.findtext('offset', '0')))/divisions)
                        for kind in ('segno', 'coda', 'dacapo', 'dalsegno', 'tocoda', 'fine', 'forward-repeat'):
                            value = sound.get(kind)
                            if value is None or value == 'no':
                                continue
                            present.add(kind)
                            if kind in ('segno', 'coda'):
                                markers[(pi, kind, value)].append(sound_position)
                                controls.append((kind, sound_position, None, ()))
                            else:
                                default = '2' if kind == 'tocoda' else '1'
                                controls.append((kind, sound_position, value, _time_only(sound, default)))
                    for kind in ('segno', 'coda'):
                        if item.find('.//'+kind) is not None and kind not in present:
                            markers[(pi, kind, None)].append(position)
                            controls.append((kind, position, None, ())); present.add(kind)
                    if item.tag == 'barline':
                        for kind in ('segno', 'coda'):
                            if item.get(kind) is not None and kind not in present:
                                markers[(pi, kind, item.get(kind))].append(position)
                                controls.append((kind, position, None, ())); present.add(kind)
                    for words in item.findall('.//words'):
                        text = ''.join(words.itertext()); kind = _words(text)
                        if kind and kind not in present:
                            if kind in ('segno', 'coda'):
                                markers[(pi, kind, None)].append(position)
                            controls.append((kind, position, None, (2,) if kind == 'tocoda' else (1,)))
                            present.add(kind)
                        elif not kind and re.search(r'\b(capo|segno|coda|fine)\b', text.lower()):
                            issues.append(f'unsupported navigation words at {position}: {text}')
        for ident in active_shifts:
            issues.append(f'unclosed octave-shift in part {pi+1}: {ident}')
        # Remove redundant declarations and compare effective inherited context,
        # rather than requiring identical XML export style.
        for key, changes in timeline.items():
            previous_state = None
            for onset, value in sorted(changes.items()):
                frozen = tuple((category, value[category]) for category in ('key', 'clef', 'transpose'))
                if frozen != previous_state:
                    headers[(*key, onset)] = frozen
                    previous_state = frozen
    navigation = Counter()
    for kind, position, token, times in controls:
        target = None
        if kind in ('dalsegno', 'tocoda'):
            mark = 'segno' if kind == 'dalsegno' else 'coda'
            candidates = markers.get((position[0], mark, token), []) if token is not None else []
            if not candidates:
                candidates = [p for (part, typ, label), points in markers.items() if part == position[0] and typ == mark and (token is None or label is None) for p in points]
            candidates = list(set(candidates))
            if len(candidates) != 1:
                issues.append(f'unresolved/ambiguous {kind} at {position}')
                target = ('unresolved',)
            else:
                target = candidates[0]
        elif kind == 'dacapo':
            target = (position[0], 0, Fraction())
        elif kind == 'fine':
            try:
                target = Fraction(token) if token not in (None, 'yes') else None
            except ValueError:
                issues.append(f'unsupported fine duration at {position}: {token}')
        # Markers are identified by location, not arbitrary name or XML IDs.
        navigation[(kind, position, target, times if kind not in ('segno', 'coda') else ())] += 1
    return {'headers': headers, 'navigation': navigation, 'octaveShifts': shifts, 'beams': beams, 'issues': issues}


def _differences(truth, reading):
    keys = set(truth) | set(reading)
    return [{'location': key, 'truth': truth.get(key), 'reading': reading.get(key)}
            for key in sorted(keys, key=str) if truth.get(key) != reading.get(key)]


def compare(truth_root, reading_root, threshold=.995):
    core = core_compare(truth_root, reading_root)
    truth, reading = read(truth_root), read(reading_root)
    differences = _differences(truth['headers'], reading['headers'])
    categories = {}
    def category_timeline(score, category):
        result, last = {}, {}
        for key, value in sorted(score['headers'].items(), key=lambda item: (item[0][0], item[0][1], item[0][2], item[0][3])):
            group, current = key[:3], dict(value)[category]
            if group not in last or current != last[group]:
                result[key] = current; last[group] = current
        return result
    for category in ('key', 'clef', 'transpose'):
        a = category_timeline(truth, category)
        b = category_timeline(reading, category)
        detail = _differences(a, b)
        categories[category] = {'matches': a == b, 'differences': detail,
                                'unequalValuesAtCommonLocations': [d for d in detail if d['location'] in a and d['location'] in b],
                                'unmatchedLocations': [d for d in detail if d['location'] not in a or d['location'] not in b]}
    # Voice labels in beam diagnostics use the same whole-part bijection as core.
    maps = {p['partIndex']-1: {pair['reading']: pair['truth'] for pair in p['pairs']}
            for p in core['voiceNormalization']['parts']}
    normalized_beams = Counter()
    for key, count in reading['beams'].items():
        normalized_beams[(*key[:2], maps.get(key[0], {}).get(key[2], key[2]), *key[3:])] += count
    beam_matches = truth['beams'] == normalized_beams
    beam_status = 'explicit-beaming-matches' if beam_matches else ('omitted-explicit-beams-auto-beaming-possible' if truth['beams'] and not normalized_beams else 'different-explicit-beaming')
    supported = not truth['issues'] and not reading['issues']
    header_matches = all(value['matches'] for value in categories.values())
    navigation_matches = truth['navigation'] == reading['navigation']
    shift_matches = truth['octaveShifts'] == reading['octaveShifts']
    known_headers = all(dict(value)['key'] is not None and dict(value)['clef'] is not None for value in truth['headers'].values())
    return {'qualificationVersion': VERSION, 'coreMetricVersion': core['metricVersion'],
            'coreGate': {'threshold': threshold, 'passes': core_passes(core, threshold), 'events': core['events']},
            'supported': supported, 'truthHasKnownKeyAndClef': known_headers,
            'issues': {'truth': truth['issues'], 'reading': reading['issues']},
            'headers': {'matches': header_matches, 'categories': categories, 'differences': differences},
            'navigation': {'matches': navigation_matches, 'truth': list(truth['navigation'].items()), 'reading': list(reading['navigation'].items())},
            'octaveShifts': {'matches': shift_matches, 'truth': list(truth['octaveShifts'].items()), 'reading': list(reading['octaveShifts'].items())},
            'notationFidelity': {'explicitBeamsMatch': beam_matches, 'beamStatus': beam_status,
                                 'truthBeamElements': sum(truth['beams'].values()), 'readingBeamElements': sum(normalized_beams.values()),
                                 'affectsPerformanceGate': False, 'interpretation': 'Beams are optional MusicXML; omission can use automatic beaming. This diagnostic alone does not establish a wrong rhythm.'},
            'performanceGateV1Passes': core_passes(core, threshold) and supported and known_headers and header_matches and navigation_matches and shift_matches,
            'scope': 'Core notation events plus inherited key/clef/transposition, octave spans, and bounded DC/DS/coda/fine control graph. No arbitrary part/bar/staff alignment. Not a full notation-fidelity or population-accuracy certificate.'}


def dump(report):
    return json.dumps(report, indent=2, default=str)+'\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('truth', type=Path); parser.add_argument('reading', type=Path)
    parser.add_argument('--out', type=Path); parser.add_argument('--gate', type=float, default=.995)
    args = parser.parse_args()
    report = compare(ET.parse(args.truth).getroot(), ET.parse(args.reading).getroot(), args.gate)
    if args.out:
        args.out.write_text(dump(report))
    else:
        print(dump(report), end='')
