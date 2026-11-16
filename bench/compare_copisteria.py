"""Compare pinned Copisteria models on frozen practice-score cases.

    ../.venv/bin/python bench/compare_copisteria.py --cases-root dev-samples/independent-eval/validated-v1 --split dev

No GT-derived correction: the common text input is local Tesseract OCR. Only
page concatenation is normalized, and that uses the same part-preserving merger
as Sheetscan. A missing page/failed case remains in the truth denominator.
Raw model MusicXML, detector caches, OCR inputs, logs and reports stay in the
ignored output directory. Native tempo/text integration is reported separately
from core note/structure quality.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from practice_metrics import compare, read

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'web/src/py'))
import pipeline


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ocr(path):
    result = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'eng', '--psm', '11', 'tsv'],
                            capture_output=True, text=True, timeout=120, check=True)
    words = []
    for row in csv.DictReader(result.stdout.splitlines(), delimiter='\t'):
        if row['level'] != '5' or not row['text'].strip() or float(row['conf']) < 55:
            continue
        x, y, width, height = [int(row[k]) for k in ('left', 'top', 'width', 'height')]
        words.append({'text': row['text'], 'xyxy': [x, y, x+width, y+height], 'role': 'words'})
    return words


def run(args):
    source = args.copisteria_root.resolve()
    # Keep the venv entry point: resolving its symlink would run the base Python.
    python = args.python.absolute()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    report = {'status': 'running', 'codeCommit': commit, 'codeLicense': 'Apache-2.0',
              'inputPolicy': 'identical page rasters + local Tesseract words; no GT correction',
              'normalization': 'concatenate pages only when part IDs match; no bar alignment, note correction or concert transposition',
              'scope': 'native CPU, not a browser backend; core events and structure; native tempo/role integration differs',
              'weights': [{'file': str(p.relative_to(source)), 'bytes': p.stat().st_size, 'sha256': digest(p)}
                          for p in sorted((source/'models').rglob('*.pt'))], 'cases': []}
    def save():
        temp = output/'summary.tmp'
        temp.write_text(json.dumps(report, indent=2)+'\n')
        temp.replace(output/'summary.json')
    save()
    for directory in sorted(args.cases_root.resolve().glob(args.split+'-*')):
        case = json.loads((directory/'case.json').read_text())
        if args.only and case['id'] not in args.only:
            continue
        truth = directory/'truth.musicxml'
        if digest(truth) != case['truthSha256']:
            raise ValueError(f"Frozen GT hash changed: {case['id']}")
        truth_root = ET.parse(truth).getroot()
        copied = output/case['id']/'inputs'
        copied.mkdir(parents=True, exist_ok=True)
        pages = sorted(directory.glob('input-*.png'), key=lambda p: int(p.stem.split('-')[-1]))
        if not pages:
            raise ValueError(f"Case has no raster inputs: {case['id']}")
        images = []
        for page in pages:
            target = copied/page.name
            shutil.copy2(page, target)
            target.with_suffix('.texts.json').write_text(json.dumps(ocr(target), indent=2)+'\n')
            images.append(target)
        for detector in args.detectors:
            dest = output/case['id']/f'copista-{detector}'
            dest.mkdir(parents=True, exist_ok=True)
            item = {'id': case['id'], 'split': case['split'], 'detector': detector,
                    'truthSha256': digest(truth), 'inputs': [{'file': p.name, 'sha256': digest(p)} for p in images]}
            started = time.monotonic()
            command = [str(python), '-m', 'copisteria.pipeline', *map(str, images), '--out', str(dest), '--detector', detector]
            item['command'] = command
            try:
                env = dict(os.environ, OMP_NUM_THREADS='4', MKL_NUM_THREADS='4')
                with (dest/'run.log').open('w') as log:
                    subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900, check=True)
                readings = [ET.parse(dest/(p.stem+'.musicxml')).getroot() for p in images]
                merged = pipeline._merge_pages(readings)
                path = dest/'merged.musicxml'
                ET.ElementTree(merged).write(path, encoding='utf-8', xml_declaration=True)
                metrics = compare(truth_root, merged)
                item.update(status='read', metrics=metrics, outputSha256=digest(path))
                (dest/'strict.json').write_text(json.dumps(metrics, indent=2)+'\n')
            except Exception as error:
                counts = read(truth_root)
                total = sum(counts['events'].values())
                item.update(status='failed', error=str(error),
                            metrics={'events': {'truth': total, 'reading': 0, 'correct': 0, 'missing': total, 'extra': 0,
                                               'precision': 0, 'recall': 0, 'f1': 0}, 'structureMatches': False})
            item['seconds'] = round(time.monotonic()-started, 3)
            report['cases'].append(item)
            save()
            print(json.dumps({'id': item['id'], 'detector': detector, 'status': item['status'],
                              'seconds': item['seconds'], 'events': item['metrics']['events']}), flush=True)
    report['aggregate'] = {}
    for detector in args.detectors:
        rows = [row for row in report['cases'] if row['detector'] == detector]
        totals = {key: sum(row['metrics']['events'][key] for row in rows) for key in ('truth', 'reading', 'correct')}
        totals['precision'] = totals['correct']/totals['reading'] if totals['reading'] else 0
        totals['recall'] = totals['correct']/totals['truth'] if totals['truth'] else 0
        totals['cases'] = len(rows)
        totals['failedCases'] = sum(row['status'] == 'failed' for row in rows)
        report['aggregate'][detector] = totals
    report['status'] = 'complete'
    save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases-root', type=Path, required=True)
    parser.add_argument('--split', choices=('dev', 'holdout'), default='dev')
    parser.add_argument('--output', type=Path, default=ROOT/'dev-samples/model-comparison/independent-v1')
    parser.add_argument('--copisteria-root', type=Path, default=ROOT.parent/'copisteria')
    parser.add_argument('--python', type=Path, default=ROOT.parent/'.copisteria-venv/bin/python')
    parser.add_argument('--detectors', choices=('2m', '28m'), nargs='+', default=['2m', '28m'])
    parser.add_argument('--only', nargs='*')
    run(parser.parse_args())
