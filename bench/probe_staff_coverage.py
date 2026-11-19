"""Record actual model-input crops and raw codec tokens, without changing them.

This probe does not open a reference score. Segmented-head positions are model
evidence, not ground truth. Use original pixels to verify any suspected clipping.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def run(args):
    source = Path(os.environ.get('SHEETSCAN_SOURCE_DIR', ROOT/'web/src/py')).resolve()
    sys.path.insert(0, str(source))
    import pipeline
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'scope': 'diagnostic native OMR crops and raw decoder tokens; region intervention only when explicitly selected; no GT read or note correction',
              'diagnosticRegionMode': args.region_mode, 'diagnosticRegionUnits': args.units,
              'inputSha256': hashlib.sha256(args.image.read_bytes()).hexdigest(),
              'sourceSha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.suffix in ('.py', '.json')},
              'regions': [], 'staffInputs': []}
    original_symbols = pipeline.homr_main.predict_symbols
    def symbols(debug, predictions):
        result = original_symbols(debug, predictions)
        report['rawHeads'] = [{'center': [float(v) for v in head.center], 'size': [float(v) for v in head.size]}
                              for head in result.noteheads]
        report['workingImageShape'] = list(predictions.preprocessed.shape)
        report['workingImageSha256'] = hashlib.sha256(predictions.preprocessed.tobytes()).hexdigest()
        cv2.imwrite(str(args.out/'working-page.png'), predictions.preprocessed)
        return result
    pipeline.homr_main.predict_symbols = symbols
    original_region = pipeline.staff_parsing._calculate_region
    def region(staff, regions):
        box = original_region(staff, regions)
        unmodified = box.copy()
        delta = round(args.units*float(staff.average_unit_size))
        if args.region_mode in ('shift', 'expand'):
            box[1] = max(0, box[1]-delta)
        if args.region_mode == 'shift':
            box[3] -= delta
        notes = [{'center': [float(x) for x in n.center], 'position': int(n.position)} for n in staff.get_notes()]
        report['regions'].append({'box': [int(x) for x in box], 'unmodifiedBox': [int(x) for x in unmodified],
                                  'staffLinesY': [float(y) for y in staff.grid[0].y],
                                  'staffUnit': float(staff.average_unit_size), 'heads': notes,
                                  'headsOutsideRegion': [n for n in notes if not box[0] <= n['center'][0] < box[2]
                                                        or not box[1] <= n['center'][1] < box[3]]})
        return box
    pipeline.staff_parsing._calculate_region = region
    original_parse = pipeline.staff_parsing.parse_staff_tromr
    def parse(*, staff_image, staff, config):
        index = len(report['staffInputs'])
        image = np.asarray(staff_image)
        displayed = np.rint(image*255).astype(np.uint8) if image.dtype.kind == 'f' and image.max() <= 1 else image
        cv2.imwrite(str(args.out/f'staff-{index}.png'), displayed)
        decoded = original_parse(staff_image=staff_image, staff=staff, config=config)
        report['staffInputs'].append({'index': index, 'shape': list(image.shape), 'dtype': str(image.dtype),
            'rawImageSha256': hashlib.sha256(image.tobytes()).hexdigest(),
            'decoder': [{'rhythm': s.rhythm, 'pitch': s.pitch, 'lift': s.lift, 'position': s.position,
                         'slur': s.slur, 'attention': [float(x) for x in s.coordinates] if s.coordinates is not None else None}
                        for s in decoded]})
        (args.out/'probe.json').write_text(json.dumps(report, indent=2)+'\n')
        return decoded
    pipeline.staff_parsing.parse_staff_tromr = parse
    if args.detect_only:
        rows, image, debug, _, _, _ = pipeline.detect_staffs_in_image(str(args.image), pipeline._CONFIG)
        rows = pipeline._split_unjoined_systems(image, pipeline.repair_systems(debug, rows))
        regions = pipeline.staff_parsing.StaffRegions(rows)
        report['staffs'] = []
        for row in rows:
            for staff in row.staffs:
                region(staff, regions)
                report['staffs'].append({'grid': [{'x': float(p.x), 'y': [float(v) for v in p.y]} for p in staff.grid],
                                         'grandStaff': staff.is_grandstaff,
                                         'assignedHeads': [{'center': [float(v) for v in n.center], 'position': int(n.position)} for n in staff.get_notes()]})
        (args.out/'probe.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps({'rawHeads': len(report['rawHeads']), 'staffs': len(report['staffs'])}))
        return
    result = pipeline.scan([str(args.image)], printed_tuplets=True)
    (args.out/'reading.musicxml').write_text(result)
    (args.out/'probe.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'staffs': len(report['staffInputs']), 'headsOutsideRegions': [len(r['headsOutsideRegion']) for r in report['regions']]}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--region-mode', choices=('baseline', 'shift', 'expand'), default='baseline',
                        help='Diagnostic intervention only; no production policy is changed')
    parser.add_argument('--units', type=float, default=2)
    parser.add_argument('--detect-only', action='store_true')
    run(parser.parse_args())
