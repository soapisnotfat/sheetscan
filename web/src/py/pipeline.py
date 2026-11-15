"""Sheet-music pages -> MusicXML. Runs unchanged natively (bench) and in Pyodide (browser).

Recognition is homr (staff detection + transformer); this module drives it page by
page and adds what homr lacks: octave clefs.
"""
import itertools
import copy
import json
import re
import sys
import types
import xml.etree.ElementTree as ET
from fractions import Fraction

import cv2
import numpy as np
from score_numbers import read_meters, rest_number_box

# homr imports these at module level but only uses them for downloads, PDF
# rendering and title OCR, none of which this pipeline calls.
for _name, _attrs in (("requests", {}), ("pypdfium2", {}), ("rapidocr", {"RapidOCR": None})):
    try:
        __import__(_name)
    except ImportError:
        _mod = types.ModuleType(_name)
        _mod.__dict__.update(_attrs)
        sys.modules[_name] = _mod

from homr import main as homr_main  # noqa: E402
from homr import music_xml_generator, staff_parsing  # noqa: E402
from homr.main import ProcessingConfig, detect_staffs_in_image  # noqa: E402
from homr.model import MultiStaff  # noqa: E402
from homr.music_xml_generator import XmlGeneratorArguments  # noqa: E402
from homr.system_repair import repair_systems  # noqa: E402
from homr.transformer import vocabulary  # noqa: E402
from homr.transformer.configs import Config  # noqa: E402
from homr.triplet_restoration import _as_triplet  # noqa: E402

_CONFIG = ProcessingConfig(
    enable_debug=False, enable_cache=False, write_staff_positions=False,
    read_staff_positions=False, selected_staff=-1, transformer_use_gpu=False,
    segnet_use_gpu=False, coreml_encoder=False, title_detection=False,
)
_TRANSFORMER = Config()
_TRANSFORMER.use_gpu_inference = False
_TRANSFORMER.use_coreml_encoder = False
_page_sources = []
_rest_records = []
_number_reader = None


class NonMusicPage(ValueError):
    """A page with no usable music staff; distinct from recognition failures."""


def _has_printed_staff(image, rows):
    """Require a supported five-line pattern, not a small piece of a QR code.

    Compare ink along the detected lines with ink halfway between them. Work in
    the detector's coordinates and sample its grid so rotation/curvature is kept.
    A real page of rests is valid: this does not require any pitched notes.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    height, width = gray.shape
    for row in rows:
        for staff in row.staffs:
            for k in range(0, len(staff.grid[0].y) - 4, 5):
                points = [p for p in staff.grid if len(p.y) >= k + 5]
                unit = float(np.median([(p.y[k + 4] - p.y[k]) / 4 for p in points]))
                if unit <= 0 or points[-1].x - points[0].x < 8 * unit:
                    continue
                line_hits, gap_hits = [], []
                tolerance = max(1, round(unit * 0.12))
                for point in points:
                    x = round(point.x)
                    if not 0 <= x < width:
                        continue
                    lines = point.y[k:k + 5]
                    for y in lines:
                        a, b = max(0, round(y) - tolerance), min(height, round(y) + tolerance + 1)
                        if b > a:
                            line_hits.append(gray[a:b, x].min() < 150)
                    for y in [(a + b) / 2 for a, b in zip(lines, lines[1:])]:
                        a, b = max(0, round(y) - tolerance), min(height, round(y) + tolerance + 1)
                        if b > a:
                            gap_hits.append(gray[a:b, x].min() < 150)
                if line_hits and gap_hits:
                    line_ink, gap_ink = float(np.mean(line_hits)), float(np.mean(gap_hits))
                    if line_ink >= 0.55 and line_ink - gap_ink >= 0.25:
                        return True
    return False


def _merge_pages(scores):
    """Join equivalent part lists without discarding a new part or its attributes.

    When part identity is ambiguous, fail visibly instead of dropping voices.
    Preserve each page's divisions/key/time/clef changes, including multiple
    attributes elements in one measure. They are legal MusicXML.
    """
    if not scores:
        raise ValueError("No music found on any page")
    merged = copy.deepcopy(scores[0])
    main = merged.findall("part")
    expected_ids = [p.get("id") for p in main]
    before_notes = sum(len(s.findall(".//note")) for s in scores)
    for score in scores[1:]:
        incoming = score.findall("part")
        if [p.get("id") for p in incoming] != expected_ids:
            raise ValueError("Part structure changes between pages; confirm the part mapping before merging")
        for target, source in zip(main, incoming):
            target.extend(copy.deepcopy(source.findall("measure")))
    for part in main:
        for number, measure in enumerate(part.findall("measure"), 1):
            measure.set("number", str(number))
    if len(merged.findall(".//note")) != before_notes:
        raise ValueError("Page merge lost notes or rests")
    return merged


def _first_time_is_inferred(voice):
    for symbol in voice:
        if symbol.rhythm.startswith("timeSignature"):
            return False
        if "barline" in symbol.rhythm or symbol.rhythm.startswith("repeat"):
            break
    return True


def _set_meter(measure, value):
    for attributes in measure.findall('attributes'):
        for time in attributes.findall('time'):
            attributes.remove(time)
    attributes = measure.find('attributes')
    if attributes is None:
        attributes = ET.Element('attributes')
        measure.insert(0, attributes)
    time = ET.SubElement(attributes, 'time')
    ET.SubElement(time, 'beats').text = str(value[0])
    ET.SubElement(time, 'beat-type').text = str(value[1])


def _repair_meters(score, sources):
    """Use printed numeric evidence, and carry meter over an unmarked page break.

    A missing/unsupported glyph does not override a model-read signature. Only
    headers known to have been manufactured by the XML generator are removed.
    """
    parts = score.findall('part')
    inferred = set()
    offsets = [0] * len(parts)
    pages = {source['page']: source for source in sources}
    for source in sources:
        for i, original in enumerate(source['score'].findall('part')):
            if source['inferredFirst'][i]:
                first = parts[i].findall('measure')[offsets[i]].find('attributes')
                if first is not None:
                    inferred.update(first.findall('time'))
            offsets[i] += len(original.findall('measure'))

    anchors = {}
    all_anchors = []
    for pi, part in enumerate(parts):
        for mi, measure in enumerate(part.findall('measure')):
            for note in measure.findall('note'):
                at = re.search(r'-p(\d+)-(\d+)-(\d+)$', note.get('id', ''))
                if not at or note.find('chord') is not None or note.find('grace') is not None:
                    continue
                page, x, y = map(int, at.groups())
                source = pages.get(page)
                if source is None or not source['layout']:
                    continue
                boxes = source['layout']
                distance = lambda box: max(box[1]-y, y-box[3], 0)
                staff = min(range(len(boxes)), key=lambda k: distance(boxes[k]))
                item = {'part': pi, 'measure': mi, 'page': page, 'staff': staff, 'x': x}
                anchors.setdefault((page, staff), []).append(item)
                all_anchors.append(item)

    targets, evidence, conflicts = {}, [], []
    for source in sources:
        for mark in source['meters']:
            row = anchors.get((source['page'], mark['staff']), [])
            if not row:
                continue
            after = [a for a in row if a['x'] > mark['x']]
            if after:
                anchor = min(after, key=lambda a: a['x'])
            else:
                last = max(row, key=lambda a: a['measure'])
                later = [a for a in all_anchors if a['part'] == last['part'] and a['measure'] > last['measure']]
                if not later:
                    continue  # a courtesy meter after the final sounding measure
                anchor = min(later, key=lambda a: (a['measure'], a['x']))
            key = (anchor['part'], anchor['measure'])
            value = (mark['numerator'], mark['denominator'])
            targets.setdefault(key, set()).add(value)
            evidence.append({'part': parts[key[0]].get('id'), 'measure': key[1]+1,
                             'page': source['page'], **mark})

    carried, changes = {}, []
    for pi, part in enumerate(parts):
        active, divisions = None, 1
        for mi, measure in enumerate(part.findall('measure')):
            values = targets.get((pi, mi), set())
            if len(values) > 1:
                conflicts.append({'part': part.get('id'), 'measure': mi+1, 'values': sorted(values)})
                values = set()
            if values:
                value = next(iter(values))
                _set_meter(measure, value)
                changes.append({'part': part.get('id'), 'measure': mi+1, 'kind': 'printed-meter', 'meter': value})
            for attributes in measure.findall('attributes'):
                if attributes.find('divisions') is not None:
                    divisions = int(attributes.findtext('divisions'))
                for time in list(attributes.findall('time')):
                    if time in inferred and active is not None:
                        attributes.remove(time)
                        changes.append({'part': part.get('id'), 'measure': mi+1,
                                        'kind': 'page-continuation', 'meter': active})
                    else:
                        numerator, denominator = time.findtext('beats'), time.findtext('beat-type')
                        if numerator and denominator:
                            active = (sum(int(v) for v in numerator.split('+')), int(denominator))
            notes = measure.findall('note')
            if active and notes and all(n.find('rest') is not None and n.find('rest').get('measure') == 'yes' for n in notes):
                duration = Fraction(active[0]*4*divisions, active[1])
                if duration.denominator == 1:
                    for node in measure.findall('note/duration') + measure.findall('backup/duration'):
                        node.text = str(duration.numerator)
        carried[part.get('id')] = active
    return {'printedMeters': evidence, 'changes': changes, 'conflicts': conflicts}


def _padding_rest(measure):
    notes = measure.findall('note')
    return bool(notes) and all(n.find('pitch') is None and n.find('unpitched') is None
                               and n.find('rest') is not None and n.find('rest').get('measure') == 'yes'
                               and not n.get('id') for n in notes) and all(n.tag in ('note', 'backup') for n in measure)


def repair_rest_count(score, note_id, count):
    """Resize only a verified expanded multirest; never remove sounding measures."""
    if not 2 <= count <= 256:
        raise ValueError('Printed multirest count is out of range')
    for part in score.findall('part'):
        measures = part.findall('measure')
        for index, measure in enumerate(measures):
            if not any(n.get('id') == note_id for n in measure.findall('note')):
                continue
            multiple = measure.find('attributes/measure-style/multiple-rest')
            if multiple is None:
                raise ValueError('Multirest source marker is missing')
            previous = int(multiple.text)
            padding = measures[index+1:index+previous]
            if len(padding) != previous-1 or not all(_padding_rest(m) for m in padding):
                raise ValueError('Multirest span contains non-rest content; correction needs review')
            if count > previous:
                for _ in range(count-previous):
                    part.insert(list(part).index(measure)+previous, copy.deepcopy(padding[-1]))
            elif count < previous:
                for item in padding[count-1:]:
                    part.remove(item)
            multiple.text = str(count)
            for number, item in enumerate(part.findall('measure'), 1):
                item.set('number', str(number))
            return {'part': part.get('id'), 'sourceId': note_id, 'startMeasure': index+1,
                    'previous': previous, 'count': count}
    raise ValueError('Multirest source was not found')


def repair_rest_counts_xml(text, changes_json):
    score = ET.fromstring(text)
    audit_field = score.find('.//miscellaneous-field[@name="conversion-audit"]')
    audit = json.loads(audit_field.text) if audit_field is not None else {}
    sources_field = score.find('.//miscellaneous-field[@name="numeric-sources"]')
    sources = json.loads(sources_field.text) if sources_field is not None else []
    for change in json.loads(changes_json):
        fixed = repair_rest_count(score, change['sourceId'], int(change['count']))
        delta = fixed['count']-fixed['previous']
        for entry in audit.get('printedMeters', []) + audit.get('changes', []) + audit.get('conflicts', []):
            if entry.get('part') == fixed['part'] and entry.get('measure', 0) >= fixed['startMeasure']+fixed['previous']:
                entry['measure'] += delta
        audit.setdefault('restChanges', []).append(fixed)
        for source in sources:
            if source['sourceId'] == change['sourceId']:
                source['count'] = int(change['count'])
                source['reading'] = change.get('reading')
    if audit_field is not None:
        audit_field.text = json.dumps(audit)
    if sources_field is not None:
        sources_field.text = json.dumps(sources)
    _order_children(score)
    return ET.tostring(score, encoding='unicode', xml_declaration=True)


def _ink(region):
    """Mask (0/255) of what is printed in a piece of the page. The cut is nearer to the
    paper than to the darkest ink, so that thin strokes a scanner turned grey still count."""
    if region.size == 0:
        return np.zeros((1, 1), np.uint8)
    paper, darkest = float(np.median(region)), float(region.min())
    if paper - darkest < 40:  # nothing printed here
        return np.zeros(region.shape, np.uint8)
    return (region < paper - 0.3 * (paper - darkest)).astype(np.uint8) * 255


def _has_eight_below(image, x0, x1, lines, limit, bass):
    """Is there a small "8" under a clef (an octave clef)? lines are the staff's five
    line positions there. An 8 is the only glyph with two small holes, one above the
    other. It may touch the clef or the bottom line, so look for the holes, not the
    glyph. Under a bass clef the 8 straddles the bottom line; a treble clef has loops
    of its own there, and its 8 hangs below the tail."""
    unit, bottom = (lines[4] - lines[0]) / 4, lines[4]
    y0, y1 = int(bottom - (1.2 if bass else 0.3) * unit), int(min(bottom + 5 * unit, limit))
    ink = _ink(image[y0:y1, max(int(x0), 0) : int(x1)])
    contours, hierarchy = cv2.findContours(ink, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return False
    holes = [cv2.boundingRect(c) for c, h in zip(contours, hierarchy[0]) if h[3] != -1]
    holes = [
        (bx + w / 2, by + h / 2)
        for bx, by, w, h in holes  # wider holes are half notes cut by a ledger line
        if 0.15 * unit <= w <= 0.65 * unit and 0.15 * unit <= h <= 0.65 * unit
    ]
    return any(
        abs(ax - bx) < 0.25 * unit and 0.2 * unit < by - ay < 1.1 * unit
        for ax, ay in holes
        for bx, by in holes
    )


def _has_pitch(symbol):
    """A note the transformer gave a pitch like "C4" (now and then it gives none)."""
    return symbol.rhythm.startswith("note") and symbol.pitch[:1] in tuple("CDEFGAB") and symbol.pitch[1:].isdigit()


def _staff_name(symbol):
    return "lower" if symbol.position.startswith("lower") else "upper"


def _mark_octave_clefs(image, staff, symbols, carried):
    """Renames clefs with an 8 below to clef_.._8vb and lowers the notes they govern.
    The first clef of a staff sits at its start; a later one (a clef change) is looked
    for around where the transformer saw it. `carried` is how the line above ended,
    {staff name: (lowered, clef sign)}: a line starts as the last one ended, so an 8
    which is missed there is still known. Returns the same for this line."""
    state, started = dict(carried), set()
    for symbol in symbols:
        name = _staff_name(symbol)
        if symbol.rhythm.startswith(("note", "rest")):
            started.add(name)
            if state.get(name, (False,))[0] and _has_pitch(symbol):
                symbol.pitch = symbol.pitch[:-1] + str(int(symbol.pitch[-1]) - 1)
        elif symbol.rhythm.startswith("clef"):
            sign = symbol.rhythm.split("_")[1][0]
            change = name in started and symbol.image_coordinates
            point = staff.get_at(symbol.image_coordinates[0]) if change else staff.grid[0]
            k = 5 if name == "lower" else 0
            if point is None or len(point.y) < k + 5:
                continue
            lines = point.y[k : k + 5]
            unit = (lines[4] - lines[0]) / 4
            x = symbol.image_coordinates[0] if change else point.x + 1.5 * unit
            limit = point.y[5] - unit if k == 0 and len(point.y) > 5 else image.shape[0]
            found = _has_eight_below(image, x - 2.5 * unit, x + 2.5 * unit, lines, limit, sign == "F")
            lowered = found or (name not in started and carried.get(name) == (True, sign))
            state[name] = (lowered, sign)
            if lowered:
                symbol.rhythm += "_8vb"
    return state


_parse_staff_image = staff_parsing.parse_staff_image
_build_clef = music_xml_generator.build_clef
_line_above = None  # (top of the staff, how its octave clefs ended) of the last staff read


def _parse_staff_image_with_octave_clefs(debug, index, staff, image, *args, **kwargs):
    # (Placing notes far from the staff by their notehead blob instead of the transformer's
    # count of ledger lines was tried here: no gain, chord heads run together.)
    global _line_above
    symbols = _parse_staff_image(debug, index, staff, image, *args, **kwargs)
    # homr reads a part line by line down the page, then starts the next part at the top.
    carried = _line_above[1] if _line_above and _line_above[0] < staff.min_y else {}
    _line_above = (staff.min_y, _mark_octave_clefs(image, staff, symbols, carried))
    return symbols


def _build_clef_with_octave(model_clef, attributes):
    _build_clef(model_clef, attributes)
    if model_clef.rhythm.endswith("_8vb"):
        ET.SubElement(attributes.findall("clef")[-1], "clef-octave-change").text = "-1"


def _step(chord):
    """The notes and rests which decide how long a chord lasts (its shortest), and that length."""
    timed = [s for s in chord if s.rhythm.startswith(("note", "rest")) and s.get_duration().fraction > 0]
    if not timed:
        return [], 0
    shortest = min(s.get_duration().fraction for s in timed)
    return [s for s in timed if s.get_duration().fraction == shortest], shortest


def _fit_measure(measure, typical):
    """Bring a measure to the usual length by the fewest changes between plain and tuplet
    note values; if no such change fits exactly, it is left as read.
    Too long: a plain value next to tuplets is part of the tuplet (a quarter under a
    triplet bracket). Too short: tuplets which are none.
    (Also demanding that tuplet groups fill whole beats was tried and read worse.)"""
    total = vocabulary._get_duration_of_measure(measure)
    if not typical or total == typical:
        return measure
    steps = [shortest for shortest, length in map(_step, measure) if length]
    tuplets = [n for n, shortest in enumerate(steps) if any(s.is_tuplet() for s in shortest)]
    if total > typical:
        change = _as_triplet
        candidates = [
            n for n, shortest in enumerate(steps)
            if n not in tuplets and any(abs(n - t) <= 2 for t in tuplets)
            and all(change(s) is not s for s in shortest)
        ]
    else:
        change = lambda s: s.remove_tuplet()  # noqa: E731
        candidates = tuplets
    for size in range(1, min(len(candidates), 6) + 1):
        for chosen in itertools.combinations(candidates[:12], size):
            swap = {id(s): change(s) for n in chosen for s in steps[n]}
            trial = [[swap.get(id(s), s) for s in chord] for chord in measure]
            if vocabulary._get_duration_of_measure(trial) == typical:
                return trial
    return measure


def _repair_tuplets(chords):
    """Stands in for homr's _fix_over_eager_tuplets, which strips every tuplet from any
    measure shorter than the usual one - ruinous for music that is full of them."""
    measures = vocabulary._group_into_measures(chords)
    typical = vocabulary._get_typical_duration_of_measures(measures)
    return vocabulary._flatten_measures([_fit_measure(m, typical) for m in measures])


vocabulary._fix_over_eager_tuplets = _repair_tuplets

_page = 0  # index of the page being read, for note ids
_notes = 0


def _build_note_id(note, symbol):
    """Gives every note an id which says where it was seen: n<count>-p<page>-<x>-<y>,
    in pixels of the page image. The editor uses it to show a note's place on the scan."""
    global _notes
    _notes += 1
    at = symbol.image_coordinates
    where = f"-p{_page}-{max(round(at[0]), 0)}-{max(round(at[1]), 0)}" if at else ""
    note.set("id", f"n{_notes}{where}")


_build_multi_measure_rest = music_xml_generator.build_multi_measure_rest


def _capture_multi_measure_rest(symbol, attributes):
    count = _build_multi_measure_rest(symbol, attributes)
    if count and symbol.image_coordinates:
        _rest_records.append({'attributes': attributes, 'symbol': symbol, 'count': count})
    return count


# homr segments a page eight tiles at a time; two at a time need far less memory at once
# (which phones lack) and are as fast on a CPU.
_extract = homr_main.extract
homr_main.extract = lambda *args, **kwargs: _extract(*args, batch_size=2, **kwargs)

# homr has no hooks; its functions look these up as module globals on every call.
staff_parsing.parse_staff_image = _parse_staff_image_with_octave_clefs
music_xml_generator.build_clef = _build_clef_with_octave
music_xml_generator.build_image_position = _build_note_id
music_xml_generator.build_multi_measure_rest = _capture_multi_measure_rest


def _are_joined(image, upper, lower):
    """Do two staves belong to one system? Then a line joins them at their left end."""
    a, b = upper.grid[0], lower.grid[0]
    unit = (a.y[4] - a.y[0]) / 4
    x = int(max(a.x, b.x))
    gap = image[int(a.y[-1] + unit / 2) : int(b.y[0] - unit / 2), max(int(x - 1.5 * unit), 0) : int(x + 1.5 * unit)]
    return gap.size > 0 and _ink(gap).any(axis=1).mean() > 0.95


def _split_unjoined_systems(image, rows):
    """homr guesses which staves form a system from the layout of the page, and e.g.
    takes a piano system followed by a single-staff line for a system of two parts
    sounding together. Keep only what the system line confirms."""
    result = []
    for row in rows:
        group = [row.staffs[0]]
        for staff in row.staffs[1:]:
            if _are_joined(image, group[-1], staff):
                group.append(staff)
            else:
                result.append(MultiStaff(group, []))
                group = [staff]
        result.append(row if len(group) == len(row.staffs) else MultiStaff(group, []))
    return result


def _staff_boxes(rows, to_input):
    """Where the staves are, for placing text found on the page: one
    [left, top line, right, bottom line, system index] per staff, in page-image pixels."""
    boxes = []
    for system, row in enumerate(rows):
        for staff in row.staffs:
            first, last = staff.grid[0], staff.grid[-1]
            for k in range(0, len(first.y) - 4, 5):
                left, top = to_input((first.x, first.y[k]))
                right, bottom = to_input((last.x, first.y[k + 4]))
                boxes.append([round(left), round(top), round(right), round(bottom), system])
    return boxes


def _read_page(path):
    """One page image -> (MusicXML <score-partwise> element, staff boxes)."""
    global _line_above, _rest_records
    _line_above = None
    _rest_records = []
    try:
        rows, image, debug, _, _, to_input = detect_staffs_in_image(path, _CONFIG)
    except Exception as error:
        if str(error) in ("No staffs found", "No noteheads or clefs found"):
            raise NonMusicPage(str(error)) from error
        raise
    try:
        rows = _split_unjoined_systems(image, repair_systems(debug, rows))
        if not _has_printed_staff(image, rows):
            raise NonMusicPage("No supported five-line music staff found")
        voices = staff_parsing.parse_staffs(debug, rows, image, config=_TRANSFORMER)
    finally:
        debug.clean_debug_files_from_previous_runs()
    for symbol in (s for voice in voices for s in voice):
        if symbol.image_coordinates:  # so far in the resized page homr works on
            symbol.image_coordinates = to_input(symbol.image_coordinates)
    xml = music_xml_generator.generate_xml(XmlGeneratorArguments(False, None, None), voices, "")
    boxes = _staff_boxes(rows, to_input)
    original = cv2.imread(path)
    meters = read_meters(original, boxes)
    parents = {child: parent for parent in xml.iter() for child in parent}
    rests, rest_changes = [], []
    for record in _rest_records:
        measure = parents.get(record['attributes'])
        notes = measure.findall('note') if measure is not None else []
        note = next((n for n in notes if n.find('rest') is not None), None)
        if note is None:
            continue
        symbol = record['symbol']
        _build_note_id(note, symbol)
        x, y = symbol.image_coordinates
        nearest = min(boxes, key=lambda box: max(box[1]-y, y-box[3], 0))
        number_box = rest_number_box(original, nearest, (x,y))
        source = {'sourceId': note.get('id'), 'page': _page, 'count': record['count'],
                  'x': round(x), 'y': round(y), 'numberBox': number_box}
        rests.append(source)
        if _number_reader and number_box:
            a,b,c,d = number_box
            reading = _number_reader(original[b:d,a:c])
            source['reading'] = reading
            if reading and reading['value'] != record['count']:
                rest_changes.append(repair_rest_count(xml, note.get('id'), reading['value']))
                source['count'] = reading['value']
    _page_sources.append({'page': _page, 'score': xml, 'layout': boxes, 'meters': meters,
                          'rests': rests, 'restChanges': rest_changes,
                          'inferredFirst': [_first_time_is_inferred(voice) for voice in voices]})
    return xml, boxes


# The MusicXML schema fixes the order of children; homr writes some out of it (voice
# after type, alter after octave, clef before key). Most programs don't mind, Finale
# refuses the file. bench/validate.py checks the result against the schema.
_CHILD_ORDER = {
    "note": "grace cue chord pitch unpitched rest duration tie instrument footnote level voice type dot "
            "accidental time-modification stem notehead notehead-text staff beam notations lyric play listen",
    "pitch": "step alter octave",
    "attributes": "footnote level divisions key time staves part-symbol instruments clef staff-details "
                  "transpose for-part directive measure-style",
}


def _order_children(score):
    for tag, order in _CHILD_ORDER.items():
        rank = {name: i for i, name in enumerate(order.split())}
        for element in score.iter(tag):
            element[:] = sorted(element, key=lambda child: rank.get(child.tag, len(rank)))  # stable


def _give_every_staff_a_clef(score):
    """A staff that is silent at first (a piece opening on single-staff lines before the
    piano enters) gets its first clef only where it starts: put that clef at the beginning."""
    for part in score.findall("part"):
        first = part.find("measure/attributes")
        if first is None:
            continue
        have = {clef.get("number", "1") for clef in first.findall("clef")}
        for clef in part.iter("clef"):
            number = clef.get("number", "1")
            if number not in have:
                have.add(number)
                copy = ET.fromstring(ET.tostring(clef))
                last = first.findall("clef")
                first.insert(list(first).index(last[-1]) + 1 if last else len(first), copy)


def scan(paths, progress=lambda done, total: None, number_reader=None):
    """Recognise each page image; pages without music are skipped. Returns MusicXML text.
    The staff boxes of every page ride along as the miscellaneous field "staff-layout"."""
    global _page, _page_sources, _number_reader
    _page_sources = []
    _number_reader = number_reader
    scores, layout = [], [[] for _ in paths]
    for _page, path in enumerate(paths):
        progress(_page, len(paths))
        try:
            xml, boxes = _read_page(path)
        except NonMusicPage as error:
            print(f"page {_page + 1} skipped: {error}", file=sys.stderr)
            continue
        except BaseException:
            _number_reader = None
            raise
        layout[_page] = boxes
        scores.append(xml)
    progress(len(paths), len(paths))
    _number_reader = None
    merged = _merge_pages(scores)
    numeric_audit = _repair_meters(merged, _page_sources)
    numeric_audit['restChanges'] = [change for source in _page_sources for change in source['restChanges']]
    _give_every_staff_a_clef(merged)
    _order_children(merged)
    identification = merged.find("identification")
    if identification is None:
        identification = ET.Element("identification")
        work = merged.find('work')
        merged.insert(list(merged).index(work)+1 if work is not None else 0, identification)
    miscellaneous = identification.find('miscellaneous')
    if miscellaneous is None:
        miscellaneous = ET.SubElement(identification, 'miscellaneous')
    field = ET.SubElement(miscellaneous, "miscellaneous-field")
    field.set("name", "staff-layout")
    field.text = json.dumps(layout)
    field = ET.SubElement(miscellaneous, 'miscellaneous-field', name='numeric-sources')
    field.text = json.dumps([rest for source in _page_sources for rest in source['rests']])
    field = ET.SubElement(miscellaneous, 'miscellaneous-field', name='conversion-audit')
    field.text = json.dumps(numeric_audit)
    return ET.tostring(merged, encoding="unicode", xml_declaration=True)
