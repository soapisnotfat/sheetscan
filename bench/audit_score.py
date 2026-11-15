"""Read every MusicXML attributes element in order; never assume a missing meter.

Duration discrepancies are review candidates, not automatically notation errors.
"""
from fractions import Fraction
import xml.etree.ElementTree as ET
import json
import sys


def audit(root):
    parts = []
    for part in root.findall('part'):
        divisions, meter = 1, None
        result = {'id': part.get('id'), 'measures': len(part.findall('measure')),
                  'pitchedEvents': len(part.findall('.//note/pitch')), 'meters': [],
                  'multirests': [], 'durationFlags': []}
        for index, measure in enumerate(part.findall('measure'), 1):
            cursor, end = Fraction(0), Fraction(0)
            for item in measure:
                if item.tag == 'attributes':
                    if item.find('divisions') is not None:
                        divisions = int(item.findtext('divisions'))
                    for signature in item.findall('time'):
                        beats, beat_type = signature.findtext('beats'), signature.findtext('beat-type')
                        if beats and beat_type:
                            meter = (sum(int(v) for v in beats.split('+')), int(beat_type))
                            result['meters'].append([index, *meter])
                    for rest in item.findall('./measure-style/multiple-rest'):
                        result['multirests'].append([index, int(rest.text)])
                elif item.tag in ('note', 'backup', 'forward'):
                    duration = Fraction(int(item.findtext('duration', '0')), divisions)
                    if item.tag == 'backup':
                        cursor -= duration
                    elif item.tag == 'forward':
                        cursor += duration
                        end = max(end, cursor)
                    elif item.find('chord') is None and item.find('grace') is None:
                        cursor += duration
                        end = max(end, cursor)
            expected = Fraction(meter[0] * 4, meter[1]) if meter else None
            if expected is None or end != expected:
                result['durationFlags'].append({'measureIndex': index, 'number': measure.get('number'),
                    'expectedQ': str(expected) if expected is not None else None,
                    'actualQ': str(end), 'implicit': measure.get('implicit')})
        parts.append(result)
    return parts


if __name__ == '__main__':
    print(json.dumps(audit(ET.parse(sys.argv[1]).getroot()), ensure_ascii=False, indent=2))
