"""Strict MusicXML comparison for score-following practice.

Unlike evalscore.py's aligned diagnostic, this never shifts bars to maximize a
score. A missing bar, wrong rest, duration, tie or tuplet is a musical error.
Written pitch is compared, not inferred concert pitch. IDs and divisions units
are ignored. This is an evaluator, not a recognizer confidence estimator.

    python bench/practice_metrics.py truth.musicxml reading.musicxml [--out report.json]
    python bench/practice_metrics.py truth.musicxml reading.musicxml --gate .995

The gate requires joint event precision AND recall, exact bar/meter structure,
and tempo correctness when the truth specifies tempo. Tiny fixtures are useful
regressions, not evidence of 99.5% accuracy on unseen complete pieces.
"""
import argparse
from collections import Counter
from fractions import Fraction
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def _duration(item, divisions):
    return Fraction(item.findtext('duration', '0'))/divisions


def read(root):
    if root.tag != 'score-partwise' or not root.findall('part'):
        raise ValueError('Expected a non-empty score-partwise MusicXML document')
    events, attacks, graces, meters, tempos, form = Counter(), Counter(), Counter(), {}, Counter(), Counter()
    parts = root.findall('part')
    ignored_hidden, ignored_tempo = 0, 0
    bars = []
    for pi, part in enumerate(parts):
        divisions, meter = 1, None
        measures = part.findall('measure')
        bars.append(len(measures))
        for mi, measure in enumerate(measures):
            cursor, previous = Fraction(), Fraction()
            for item in measure:
                if item.tag == 'attributes':
                    divisions = int(item.findtext('divisions', str(divisions)))
                    for time in item.findall('time'):
                        beats, unit = time.findtext('beats'), time.findtext('beat-type')
                        if beats and unit:
                            meter = (tuple(map(int, beats.split('+'))), int(unit))
                elif item.tag in ('backup', 'forward'):
                    cursor += _duration(item, divisions)*(-1 if item.tag == 'backup' else 1)
                elif item.tag == 'direction':
                    offset = Fraction(item.findtext('offset', '0'))/divisions
                    sound = item.find('sound')
                    bpm = Fraction(sound.get('tempo')) if sound is not None and sound.get('tempo') else None
                    if bpm is None:
                        metro = item.find('.//metronome')
                        if metro is not None and metro.findtext('per-minute'):
                            units = {'whole': 4, 'half': 2, 'quarter': 1, 'eighth': Fraction(1, 2), '16th': Fraction(1, 4)}
                            unit = units.get(metro.findtext('beat-unit'))
                            if unit:
                                dots = len(metro.findall('beat-unit-dot'))
                                bpm = Fraction(metro.findtext('per-minute'))*unit*(2-Fraction(1, 2)**dots)
                    # Playback-only MIDI tempo is not observable in a PDF.
                    printed = item.get('print-object') != 'no' and (item.find('.//metronome/per-minute') is not None
                              or any(re.search(r'\d', words.text or '') for words in item.findall('.//words')))
                    if bpm is not None and printed:
                        tempos[(pi, mi, cursor+offset, bpm)] += 1
                    elif bpm is not None:
                        ignored_tempo += 1
                elif item.tag == 'barline':
                    for repeat in item.findall('repeat'):
                        direction = repeat.get('direction')
                        side = item.get('location', 'left' if direction == 'forward' else 'right')
                        form[(pi, mi, side, 'repeat', direction, repeat.get('times', '2') if direction == 'backward' else '')] += 1
                    for ending in item.findall('ending'):
                        form[(pi, mi, item.get('location', 'right'), 'ending', ending.get('type'), ending.get('number'))] += 1
                elif item.tag == 'note':
                    voice, staff = item.findtext('voice', '1'), item.findtext('staff', '1')
                    pitch = item.find('pitch')
                    kind = 'note' if pitch is not None else 'rest' if item.find('rest') is not None else 'unpitched'
                    value = (pitch.findtext('step'), Fraction(pitch.findtext('alter', '0')), pitch.findtext('octave')) if pitch is not None else None
                    hidden = item.get('print-object') == 'no'
                    if hidden:
                        ignored_hidden += 1
                    if item.find('grace') is not None:
                        if not hidden:
                            graces[(pi, mi, voice, staff, cursor, kind, value)] += 1
                        continue
                    duration = _duration(item, divisions)
                    onset = previous if item.find('chord') is not None else cursor
                    ties = tuple(sorted(t.get('type') for t in item.findall('tie')))
                    modification = item.find('time-modification')
                    ratio = Fraction(int(modification.findtext('normal-notes')), int(modification.findtext('actual-notes'))) if modification is not None else Fraction(1)
                    if not hidden:
                        events[(pi, mi, voice, staff, onset, duration, kind, value, ties, ratio)] += 1
                    if not hidden and kind == 'note' and 'stop' not in ties:
                        attacks[(pi, mi, voice, staff, onset, value)] += 1
                    if item.find('chord') is None:
                        previous = cursor
                        cursor += duration
            meters[(pi, mi)] = meter
    return {'events': events, 'attacks': attacks, 'graces': graces, 'meters': meters, 'tempos': tempos, 'bars': bars, 'form': form,
            'ignoredHiddenEvents': ignored_hidden, 'ignoredPlaybackTempos': ignored_tempo}


def _counts(truth, reading):
    matched, nt, nr = sum((truth & reading).values()), sum(truth.values()), sum(reading.values())
    return {'truth': nt, 'reading': nr, 'correct': matched, 'missing': nt-matched, 'extra': nr-matched,
            'precision': matched/nr if nr else float(not nt),
            'recall': matched/nt if nt else float(not nr),
            'f1': 2*matched/(nt+nr) if nt+nr else 1.0}


def compare(truth_root, reading_root):
    truth, reading = read(truth_root), read(reading_root)
    events = _counts(truth['events'], reading['events'])
    bars = set(truth['meters']) | set(reading['meters'])
    bar_errors = []
    for key in sorted(bars):
        a = Counter({e: count for e, count in truth['events'].items() if e[:2] == key})
        b = Counter({e: count for e, count in reading['events'].items() if e[:2] == key})
        if a != b or truth['meters'].get(key) != reading['meters'].get(key):
            bar_errors.append({'partIndex': key[0]+1, 'measureIndex': key[1]+1,
                               'events': _counts(a, b), 'meterMatches': truth['meters'].get(key) == reading['meters'].get(key)})
    rest = lambda counter: Counter({event: n for event, n in counter.items() if event[6] == 'rest'})
    return {'scope': 'strict written notation at original part/bar/voice/onset; no bar alignment',
            'events': events, 'attackPitchDiagnostic': _counts(truth['attacks'], reading['attacks']),
            'rests': _counts(rest(truth['events']), rest(reading['events'])),
            'graces': _counts(truth['graces'], reading['graces']),
            'truthMeasuresByPart': truth['bars'], 'readingMeasuresByPart': reading['bars'],
            'structureMatches': truth['bars'] == reading['bars'],
            'meterMatches': truth['meters'] == reading['meters'],
            'formMatches': truth['form'] == reading['form'],
            'truthHasTempo': bool(truth['tempos']), 'tempoMatches': truth['tempos'] == reading['tempos'],
            'unobservableInPdf': {'truthHiddenEvents': truth['ignoredHiddenEvents'], 'readingHiddenEvents': reading['ignoredHiddenEvents'],
                                 'truthPlaybackOnlyTempos': truth['ignoredPlaybackTempos'], 'readingPlaybackOnlyTempos': reading['ignoredPlaybackTempos']},
            'exactBars': len(bars)-len(bar_errors), 'totalBars': len(bars), 'barErrors': bar_errors}


def passes(report, threshold):
    return (report['events']['truth'] > 0 and report['events']['precision'] >= threshold and report['events']['recall'] >= threshold
            and report['graces']['precision'] >= threshold and report['graces']['recall'] >= threshold
            and report['structureMatches'] and report['meterMatches']
            and report['formMatches']
            and (not report['truthHasTempo'] or report['tempoMatches']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('truth', type=Path)
    parser.add_argument('reading', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--gate', type=float)
    args = parser.parse_args()
    if args.gate is not None and not 0 <= args.gate <= 1:
        parser.error('--gate must be between 0 and 1')
    report = compare(ET.parse(args.truth).getroot(), ET.parse(args.reading).getroot())
    if args.gate is not None:
        report['gate'] = {'threshold': args.gate, 'passed': passes(report, args.gate)}
    text = json.dumps(report, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text+'\n')
    print(text)
    raise SystemExit(1 if args.gate is not None and not report['gate']['passed'] else 0)
