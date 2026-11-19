"""Frozen, self-authored development and holdout MusicXML for OMR evaluation.

The melodies are procedurally authored CC0. Ground truth is generated directly,
never transcribed from recognition output. Seeds, profiles and hashes are saved
before inference. Whole pieces, not adjacent pages, define the split.

    python bench/heldout_cases.py [output-directory]

Use web/tools/render-heldout.mjs to render each truth at its declared font/layout.
This is a controlled synthetic corpus, not a real-score accuracy certification.
"""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import random
import sys
import xml.etree.ElementTree as ET

D = 1680
SHARPS = 'FCGDAEB'
FLATS = 'BEADGCF'


def el(parent, tag, text=None, **attrs):
    node = ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})
    if text is not None:
        node.text = str(text)
    return node


def ev(q, kind, *, dots=0, rest=False, ratio=None, group=None, grace=False):
    return dict(q=F(q), kind=kind, dots=dots, rest=rest, ratio=ratio, group=group, grace=grace)


def pattern(meter, variant):
    """Legal independent rhythm plans; no recognizer knowledge or filename rules."""
    total = F(meter[0]*4, meter[1])
    if meter == (4, 4):
        choices = [
            [ev('1/2', 'eighth', group=i//4) for i in range(8)],
            [ev('3/2', 'quarter', dots=1), ev('1/2', 'eighth'), ev(1, 'quarter'), ev(1, 'quarter', rest=True)],
            [ev('1/2', 'eighth'), ev('1/4', '16th', group=1), ev('1/4', '16th', group=1), ev('3/2', 'quarter', dots=1), ev('1/2', 'eighth'), ev(1, 'quarter')],
            [*[ev('1/3', 'eighth', ratio=(3, 2), group=0) for _ in range(3)], ev(1, 'quarter'), ev(2, 'half')],
            [*[ev('2/5', 'eighth', ratio=(5, 4), group=0) for _ in range(5)], ev(1, 'quarter'), ev('1/2', 'eighth', group=1), ev('1/2', 'eighth', group=1)],
            [*[ev('1/4', '16th', group=0) for _ in range(4)], ev(1, 'quarter'), ev('3/2', 'quarter', dots=1), ev('1/2', 'eighth')],
            [ev(2, 'half'), ev(1, 'quarter'), ev('1/2', 'eighth', group=0), ev('1/2', 'eighth', group=0)],
        ]
    elif meter == (6, 8):
        choices = [
            [ev('1/2', 'eighth', group=i//3) for i in range(6)],
            [ev('3/2', 'quarter', dots=1), ev('3/2', 'quarter', dots=1)],
            [ev('3/4', 'eighth', ratio=(2, 3), group=0), ev('3/4', 'eighth', ratio=(2, 3), group=0), *[ev('1/2', 'eighth', group=1) for _ in range(3)]],
            [ev('3/4', 'eighth', dots=1), ev('1/4', '16th'), ev('1/2', 'eighth'), ev('3/2', 'quarter', dots=1, rest=True)],
            [*[ev('1/4', '16th', group=0) for _ in range(6)], ev('3/2', 'quarter', dots=1)],
        ]
    elif meter == (3, 4):
        choices = [[ev(1, 'quarter') for _ in range(3)],
                   [ev('3/2', 'quarter', dots=1), ev('1/2', 'eighth'), ev(1, 'quarter')],
                   [*[ev('1/3', 'eighth', ratio=(3, 2), group=0) for _ in range(3)], ev(2, 'half')],
                   [ev('1/2', 'eighth', group=i//3) for i in range(6)]]
    elif meter == (2, 4):
        choices = [[ev(1, 'quarter'), ev(1, 'quarter')],
                   [ev('1/2', 'eighth', group=0) for _ in range(4)],
                   [ev('3/2', 'quarter', dots=1), ev('1/2', 'eighth')],
                   [ev('2/5', 'eighth', ratio=(5, 4), group=0) for _ in range(5)]]
    elif meter == (3, 8):
        choices = [[ev('1/2', 'eighth', group=0) for _ in range(3)],
                   [ev('1/4', '16th', group=0) for _ in range(6)],
                   [ev('3/4', 'eighth', ratio=(2, 3), group=0) for _ in range(2)],
                   [ev('3/2', 'quarter', dots=1)]]
    else:
        raise ValueError(meter)
    result = choices[variant % len(choices)]
    assert sum((e['q'] for e in result), F()) == total
    return result


class Part:
    def __init__(self, root, pid, rng, *, bass=False, staves=1, base=35, spread=9):
        self.node = el(root, 'part', id=pid)
        self.rng, self.bass, self.staves = rng, bass, staves
        self.base, self.spread = base, spread
        self.walk = base
        self.key = 0
        self.accidentals = {}
        self.pending_tie = None
        self.previous_note = None
        self.previous_pitch = None

    def bar(self, number, meter, *, key=None, initial=False, bpm=None, implicit=False, page_break=False, system_break=False):
        m = el(self.node, 'measure', number=number, **({'implicit': 'yes'} if implicit else {}))
        self.accidentals = {}
        if page_break:
            el(m, 'print', **{'new-page': 'yes'})
        elif system_break:
            el(m, 'print', **{'new-system': 'yes'})
        if initial or key is not None or meter is not None:
            a = el(m, 'attributes')
            if initial:
                el(a, 'divisions', D)
            if key is not None:
                self.key = key
                el(el(a, 'key'), 'fifths', key)
            if meter:
                t = el(a, 'time'); el(t, 'beats', meter[0]); el(t, 'beat-type', meter[1])
            if initial:
                if self.staves > 1: el(a, 'staves', self.staves)
                for staff in range(1, self.staves+1):
                    c = el(a, 'clef', **({'number': staff} if self.staves > 1 else {}))
                    bass = self.bass or staff > 1
                    el(c, 'sign', 'F' if bass else 'G'); el(c, 'line', 4 if bass else 2)
        if bpm:
            d = el(m, 'direction', placement='above'); met = el(el(d, 'direction-type'), 'metronome')
            el(met, 'beat-unit', 'quarter'); el(met, 'per-minute', bpm); el(d, 'sound', tempo=bpm)
        return m

    def pitch(self, chromatic=False, *, low=False):
        self.walk = max(self.base-self.spread, min(self.base+self.spread, self.walk+self.rng.choice([-2,-1,-1,0,1,1,2])))
        pitch = self.walk-(14 if low else 0)
        step, octave = 'CDEFGAB'[pitch % 7], pitch//7
        base_alter = 1 if self.key > 0 and step in SHARPS[:self.key] else -1 if self.key < 0 and step in FLATS[:-self.key] else 0
        alter = self.rng.choice([-1,0,1]) if chromatic and self.rng.random() < .22 else base_alter
        return step, octave, alter

    def emit(self, m, events, *, voice='1', staff='1', chromatic=False, grace=False, ties=False, low=False):
        beam_groups = {}
        for i, event in enumerate(events):
            if grace and i == 1 and not event['rest']:
                self._note(m, ev(0, 'eighth', grace=True), self.pitch(chromatic, low=low), voice, staff)
            if event['rest']:
                pitch = None
            elif self.pending_tie is not None:
                pitch = self.pending_tie
            else:
                pitch = self.pitch(chromatic, low=low)
            n = self._note(m, event, pitch, voice, staff)
            if pitch and self.pending_tie is not None:
                el(n, 'tie', type='stop'); el(el(n, 'notations'), 'tied', type='stop')
                self.pending_tie = None
            self.previous_note, self.previous_pitch = (n, pitch) if pitch else (None, None)
            if event['group'] is not None and pitch:
                beam_groups.setdefault(event['group'], []).append((n, event))
        for group in beam_groups.values():
            if len(group) < 2:
                continue
            for j, (n, event) in enumerate(group):
                if event['kind'] in ('eighth','16th','32nd'):
                    for level in range(1, {'eighth':1,'16th':2,'32nd':3}[event['kind']]+1):
                        el(n, 'beam', 'begin' if j == 0 else 'end' if j == len(group)-1 else 'continue', number=level)
                if event['ratio'] and j in (0,len(group)-1):
                    notation = n.find('notations')
                    if notation is None: notation = el(n, 'notations')
                    el(notation, 'tuplet', type='start' if j == 0 else 'stop', number=1)
        if ties and self.previous_note is not None:
            el(self.previous_note, 'tie', type='start')
            notation = self.previous_note.find('notations')
            if notation is None: notation = el(self.previous_note, 'notations')
            el(notation, 'tied', type='start')
            self.pending_tie = self.previous_pitch

    def _note(self, measure, event, pitch, voice, staff):
        n = el(measure, 'note')
        if event['grace']: el(n, 'grace', slash='yes')
        if pitch:
            step, octave, alter = pitch
            p = el(n, 'pitch'); el(p, 'step', step)
            if alter: el(p, 'alter', alter)
            el(p, 'octave', octave)
        else:
            el(n, 'rest')
        if not event['grace']:
            duration = event['q']*D; assert duration.denominator == 1
            el(n, 'duration', duration.numerator)
        el(n, 'voice', voice)
        el(n, 'type', event['kind'])
        for _ in range(event['dots']): el(n, 'dot')
        if pitch:
            step, octave, alter = pitch
            expected = self.accidentals.get((step,octave,staff), 1 if self.key > 0 and step in SHARPS[:self.key] else -1 if self.key < 0 and step in FLATS[:-self.key] else 0)
            if alter != expected: el(n, 'accidental', {-1:'flat',0:'natural',1:'sharp'}[alter])
            self.accidentals[(step,octave,staff)] = alter
        if event['ratio']:
            tm = el(n, 'time-modification');el(tm, 'actual-notes', event['ratio'][0]);el(tm, 'normal-notes', event['ratio'][1])
        if self.staves > 1: el(n, 'staff', staff)
        return n


PROFILES = [
    dict(id='dev-sharp-syncopation', split='dev', seed=41037, bars=32, key=2, meter=(4,4), font='Leipzig', dpi=200, chromatic=True),
    dict(id='dev-compound-beams', split='dev', seed=41053, bars=32, key=-2, meter=(6,8), font='Bravura', dpi=200, grace=True),
    dict(id='dev-mixed-pickup-form', split='dev', seed=41077, bars=40, key=-3, meter=(3,4), font='Leipzig', dpi=180, mixed=True, pickup=True, repeats=True),
    dict(id='dev-piano-polyphony', split='dev', seed=41113, bars=24, key=1, meter=(4,4), font='Bravura', dpi=200, piano=True),
    dict(id='holdout-flat-range', split='holdout', seed=73013, bars=36, key=-4, meter=(4,4), font='Leipzig', dpi=160, chromatic=True, wide=True),
    dict(id='holdout-compound-graces', split='holdout', seed=73039, bars=36, key=3, meter=(6,8), font='Bravura', dpi=180, grace=True, mixed=True),
    dict(id='holdout-rests-form', split='holdout', seed=73061, bars=80, key=0, meter=(4,4), font='Leipzig', dpi=200, rests=True, repeats=True, chromatic=True),
    dict(id='holdout-piano-multipage', split='holdout', seed=73091, bars=40, key=-2, meter=(3,4), font='Bravura', dpi=160, piano=True, mixed=True),
]


def make(profile):
    rng = random.Random(profile['seed'])
    root = ET.Element('score-partwise', version='4.0')
    el(el(root,'work'),'work-title', profile['id'])
    el(el(root,'identification'),'rights','Self-authored generated notation, CC0')
    listing = el(root,'part-list')
    for pid, name in [('P1','Alto Saxophone')] + ([('P2','Piano')] if profile.get('piano') else []):
        el(el(listing,'score-part',id=pid),'part-name',name)
    lead = Part(root,'P1',rng,base=34,spread=14 if profile.get('wide') else 7)
    piano = Part(root,'P2',random.Random(profile['seed']+1),staves=2,base=31,spread=5) if profile.get('piano') else None
    meter = profile['meter']; counter=1; rest_remaining=0
    if profile.get('pickup'):
        m = lead.bar(0,meter,key=profile['key'],initial=True,bpm=76,implicit=True)
        lead.emit(m,[ev(1,'quarter')])
    for index in range(1,profile['bars']+1):
        new_meter = None
        if profile.get('mixed') and index % 8 == 1:
            meter = [(3,4),(2,4),(6,8),(4,4),(3,8)][(index//8)%5]
            new_meter = meter
        initial = index == 1 and not profile.get('pickup')
        key = profile['key'] if initial else (profile['key']+1 if profile['key'] < 4 else -2) if index == 17 and profile.get('chromatic') else None
        m = lead.bar(index, meter if initial else new_meter, key=key, initial=initial,
                     bpm=76+profile['seed']%28 if initial else 104 if index==profile['bars']//2 else None,
                     page_break=index in (25,49,73), system_break=index>1 and index%4==1)
        if profile.get('repeats') and index in (5, profile['bars']-7):
            el(el(m,'barline',location='left'),'repeat',direction='forward')
        if profile.get('rests') and index in (13, 42):
            rest_remaining = 12 if index==13 else 17
            el(el(el(m,'attributes'),'measure-style'),'multiple-rest',rest_remaining)
        if rest_remaining:
            n = el(m,'note');el(n,'rest',measure='yes');el(n,'duration',F(meter[0]*4,meter[1])*D)
            rest_remaining-=1
        else:
            rhythm = pattern(meter,rng.randrange(10000))
            lead.emit(m,rhythm,chromatic=profile.get('chromatic',False),grace=profile.get('grace',False) and index%5==2,
                      ties=index%7==6 and index != profile['bars'] and (not profile.get('rests') or index+1 not in (13,42)))
        if profile.get('repeats') and index in (12,profile['bars']):
            el(el(m,'barline',location='right'),'repeat',direction='backward',times=2)
        if piano:
            p = piano.bar(index,meter if index==1 else new_meter,key=profile['key'] if index==1 else key,initial=index==1)
            total = F(meter[0]*4,meter[1])
            piano.emit(p,pattern(meter,index+2),voice='1',staff='1')
            el(el(p,'backup'),'duration',total*D)
            # Distinct bass voice: two beat-sized notes where possible.
            if total in (2,3,4):
                bass = [ev(1,'quarter') for _ in range(int(total))]
            else:
                bass = [ev('1/2','eighth') for _ in range(int(total*2))]
            piano.emit(p,bass,voice='2',staff='2',low=True)
    # Stable MusicXML schema order independent of how ties/beams were appended.
    order = {name:i for i,name in enumerate('grace cue chord pitch unpitched rest duration tie instrument voice type dot accidental time-modification stem notehead staff beam notations lyric'.split())}
    for n in root.iter('note'): n[:]=sorted(n,key=lambda item:order.get(item.tag,999))
    return root


if __name__=='__main__':
    destination = Path(sys.argv[1] if len(sys.argv)>1 else 'dev-samples/independent-eval')
    destination.mkdir(parents=True,exist_ok=True)
    manifest={'version':1,'origin':'self-authored-CC0','freezePolicy':'truth/profile/seed fixed before inference; full-piece split',
              'qualification':'controlled synthetic corpus, not real-library accuracy proof','cases':[]}
    for profile in PROFILES:
        folder=destination/profile['id'];folder.mkdir(parents=True,exist_ok=True)
        data=ET.tostring(make(profile),encoding='utf-8',xml_declaration=True)
        path=folder/'truth.musicxml'
        if path.exists() and path.read_bytes()!=data:
            raise SystemExit(f'Refusing to mutate frozen truth: {path}')
        path.write_bytes(data)
        row={**profile,'layout':'auto','truth':'truth.musicxml','truthSha256':hashlib.sha256(data).hexdigest()}
        (folder/'case.json').write_text(json.dumps(row,indent=2)+'\n')
        manifest['cases'].append(row)
    output=destination/'frozen-manifest.json'
    if output.exists() and json.loads(output.read_text())!=manifest:
        raise SystemExit('Refusing to mutate frozen manifest')
    output.write_text(json.dumps(manifest,indent=2)+'\n')
    print(output)
