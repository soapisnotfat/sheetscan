"""Reproducible native inference for accuracy experiments (not browser timings).

    python bench/recognize_case.py out.musicxml page1.png page2.png [--read-numbers] [--printed-tuplets]

Opt-in printed-duplet policy saves the proposed and applied changes separately.
No uploaded inputs, no replacement of model weights, no ground-truth edits.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = Path(os.environ.get('SHEETSCAN_SOURCE_DIR', ROOT/'web/src/py')).resolve()
sys.path.insert(0, str(SOURCE_DIR))
import pipeline
from audit_score import audit


def run(output, images, printed_tuplets=False, read_numbers=False):
    started = time.monotonic()
    if read_numbers:
        from number_ocr import read_number
    xml = pipeline.scan([str(path) for path in images], number_reader=read_number if read_numbers else None, printed_tuplets=printed_tuplets)
    root = ET.fromstring(xml)
    conversion = json.loads(root.findtext('.//miscellaneous-field[@name="conversion-audit"]', '{}'))
    candidates, changes = conversion.get('tupletCandidates', []), conversion.get('tupletsApplied', [])
    pipeline._order_children(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(output, encoding='utf-8', xml_declaration=True)
    report = {'mode': 'native CPU; raster inputs; excludes browser text annotation',
              'seconds': round(time.monotonic()-started, 3), 'homrVersion': importlib.metadata.version('homr'),
              'pipelineSha256': hashlib.sha256(Path(pipeline.__file__).read_bytes()).hexdigest(),
              'sourceDirectory': str(SOURCE_DIR),
              'runnerSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'sourceSha256': {name: hashlib.sha256((SOURCE_DIR/name).read_bytes()).hexdigest()
                               for name in ('pipeline.py', 'score_numbers.py', 'printed_tuplets.py',
                                            'tuplet_glyphs.py', 'tuplet_classifier.json', 'tuplet_templates.json',
                                            'accidental_glyphs.py', 'accidental_classifier.json', 'staff_coverage.py')
                               if (SOURCE_DIR/name).exists()},
              'inputs': [{'file': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in images],
              'outputSha256': hashlib.sha256(output.read_bytes()).hexdigest(),
              'printedTupletsEnabled': printed_tuplets, 'candidates': candidates, 'applied': changes,
              'digitReader': 'local Tesseract' if read_numbers else None,
              'structure': audit(root)}
    output.with_suffix('.run.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'output': str(output), 'seconds': report['seconds'], 'candidates': len(candidates), 'applied': len(changes)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('images', type=Path, nargs='+')
    parser.add_argument('--printed-tuplets', action='store_true')
    parser.add_argument('--read-numbers', action='store_true')
    args = parser.parse_args()
    run(args.output, args.images, args.printed_tuplets, args.read_numbers)
