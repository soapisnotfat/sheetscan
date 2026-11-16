"""GT-assisted diagnostic of frozen models' complementary errors, not a score.

The oracle can choose the right event using truth and discard false positives.
It is therefore only an upper bound on recall for an ideal selector of unchanged
events. It is NOT an automatic recognizer, and has no meaningful precision.
No alignment or musical correction is performed. Cases without identical bar
counts and meters across every included model are excluded from the aggregate.
"""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from practice_metrics import METRIC_VERSION, _voice_normalized, compare, read


def serial(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [serial(item) for item in value]
    if isinstance(value, dict):
        return {key: serial(item) for key, item in value.items()}
    return value


def run(args):
    report = {'kind': 'GT-assisted-oracle-diagnostic-only', 'metricVersion': METRIC_VERSION,
              'interpretation': 'recall upper bound for an ideal truth-informed event selector; not achieved automatic accuracy; no precision claim',
              'normalization': 'whole-part stable voice-label bijection only; no bar alignment or event edits',
              'cases': []}
    for directory in sorted(args.cases_root.glob('dev-*')):
        truth_path = directory/'truth.musicxml'
        truth_xml = ET.parse(truth_path).getroot()
        truth = read(truth_xml)
        outputs = {'homr-8835054': directory/'baseline.musicxml'}
        outputs.update({f'copista-{size}': args.comparison/directory.name/f'copista-{size}'/'merged.musicxml'
                        for size in ('2m', '28m')})
        item = {'id': directory.name, 'eligible': True, 'models': {}, 'categories': {}}
        normalized = {}
        for name, path in outputs.items():
            root = ET.parse(path).getroot()
            metrics = compare(truth_xml, root)
            a, b, mapping = _voice_normalized(truth, read(root))
            normalized[name] = (a, b)
            eligible = metrics['structureMatches'] and metrics['meterMatches'] and mapping['supported']
            item['eligible'] &= eligible
            item['models'][name] = {'eligible': eligible, 'events': metrics['events'], 'graces': metrics['graces'],
                                    'structureMatches': metrics['structureMatches'], 'meterMatches': metrics['meterMatches'],
                                    'formMatches': metrics['formMatches'],
                                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        if item['eligible']:
            for category in ('events', 'graces'):
                reference = next(iter(normalized.values()))[0][category]
                if any(a[category] != reference for a, _ in normalized.values()):
                    raise ValueError('Voice normalization gave different truth labels across models')
                union, intersection = Counter(), reference.copy()
                for _, reading in normalized.values():
                    correct = reference & reading[category]
                    union |= correct
                    intersection &= correct
                missed = reference-union
                item['categories'][category] = {
                    'truth': sum(reference.values()), 'oracleUnionCorrect': sum(union.values()),
                    'allModelsCorrect': sum(intersection.values()), 'allModelsMiss': sum(missed.values()),
                    'oracleRecallUpperBound': sum(union.values())/sum(reference.values()) if reference else 1,
                    'sharedMisses': [{'event': serial(event), 'count': count} for event, count in missed.items()]}
        else:
            item['exclusionReason'] = 'At least one model has incompatible bar counts/meters or unsupported voice correspondence'
        report['cases'].append(item)
    report['aggregateEligibleOnly'] = {}
    for category in ('events', 'graces'):
        totals = {key: sum(item['categories'][category][key] for item in report['cases'] if item['eligible'])
                  for key in ('truth', 'oracleUnionCorrect', 'allModelsCorrect', 'allModelsMiss')}
        totals['oracleRecallUpperBound'] = totals['oracleUnionCorrect']/totals['truth'] if totals['truth'] else 1
        report['aggregateEligibleOnly'][category] = totals
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({item['id']: {'eligible': item['eligible'], 'categories': {
        key: {k: v for k, v in value.items() if k != 'sharedMisses'} for key, value in item['categories'].items()}}
        for item in report['cases']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases-root', type=Path, required=True)
    parser.add_argument('--comparison', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    run(parser.parse_args())
