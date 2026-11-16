"""Inspect actual homr detector masks and head-adjacent accidental candidates.

Reads an explicitly supplied development source image and prediction MusicXML;
never reads reference scores. Crops, mask arrays, provenance and a contact sheet
are written outside the repository. A candidate is evidence, not a pitch edit.
"""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import sys
import types
import xml.etree.ElementTree as ET

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def components(ink):
    _, labels, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8))
    return [(int(x), int(y), int(x+w), int(y+h), int(area)) for x, y, w, h, area in stats[1:]], labels


def original_box(box, mapping):
    left, top = mapping((float(box[0]), float(box[1])))
    right, bottom = mapping((float(box[2]), float(box[3])))
    return [round(float(value), 3) for value in (left, top, right, bottom)]


def run(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, attrs in (("requests", {}), ("pypdfium2", {}), ("rapidocr", {"RapidOCR": None})):
        try:
            __import__(name)
        except ImportError:
            mod = types.ModuleType(name)
            mod.__dict__.update(attrs)
            sys.modules[name] = mod
    from homr import main, model
    from homr.segmentation.config import segnet_path_onnx
    import homr
    package = Path(homr.__file__).parent
    # Snapshot all source files before invoking any detector code. The pipeline
    # under active development is deliberately never imported.
    snapshot = out/'homr-source'
    for path in package.rglob('*.py'):
        target = snapshot/path.relative_to(package)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    source_hashes = {str(p.relative_to(snapshot)): sha(p) for p in sorted(snapshot.rglob('*.py'))}
    captured = {}
    base = main.load_and_preprocess_predictions
    def capture(*a, **kw):
        result = base(*a, **kw)
        captured['predictions'] = result[0]
        return result
    main.load_and_preprocess_predictions = capture
    config = main.ProcessingConfig(enable_debug=False, enable_cache=False, write_staff_positions=False,
                                  read_staff_positions=False, selected_staff=-1, transformer_use_gpu=False,
                                  segnet_use_gpu=False, coreml_encoder=False, title_detection=False)
    rows, image, debug, _, _, mapping = main.detect_staffs_in_image(str(args.image), config)
    debug.clean_debug_files_from_previous_runs()
    predictions = captured['predictions']
    np.savez_compressed(out/'detector-masks.npz', image=image, symbols=predictions.symbols,
                        staff=predictions.staff, clefs_keys=predictions.clefs_keys,
                        notehead=predictions.notehead, stems_rest=predictions.stems_rest)
    original = cv2.imread(str(args.image))
    # Already-recognized notes are recorded without using them as target labels.
    predicted = []
    for measure in ET.parse(args.prediction).getroot().iter('measure'):
        for note in measure.findall('note'):
            match = re.search(r'-p(\d+)-(\d+)-(\d+)$', note.get('id', ''))
            if match:
                predicted.append({'id': note.get('id'), 'measure': measure.get('number'),
                    'center': [int(match[2]), int(match[3])],
                    'decoded_pitch': [note.findtext('pitch/step'), note.findtext('pitch/alter', '0'), note.findtext('pitch/octave')]})
    entries, staffs, heads = [], [], []
    symbol_counts = Counter()
    for staff_index, staff in enumerate(s for row in rows for s in row.staffs):
        symbol_counts.update(type(symbol).__name__ for symbol in staff.symbols)
        unit = float(staff.average_unit_size)
        left, right = staff.min_x, staff.max_x
        top, bottom = staff.grid[0].y[0], staff.grid[0].y[-1]
        staffs.append({'index': staff_index, 'unit': unit, 'box': original_box([left, top, right, bottom], mapping)})
        for symbol in staff.symbols:
            if isinstance(symbol, model.Note):
                heads.append({'staff': staff_index, 'center_model': list(map(float, symbol.center)),
                              'center_source': list(map(float, mapping(symbol.center))),
                              'position': int(symbol.position), 'unit': unit})
            elif isinstance(symbol, model.Accidental):
                entries.append({'origin': 'homr.Accidental', 'staff': staff_index,
                                'position': int(symbol.position), 'box_model': list(map(float, symbol.box.box))})
    # homr's Accidental class is not constructed by the installed detector.
    # Derive additional untyped boxes from its actual symbols segmentation,
    # within the left neighborhood of an actual detected notehead. The source
    # staff mask is removed; this can split/miss symbols and is audited below.
    # This installed Segnet places accidentals in clefs_keys (class 3), while
    # symbols (class 5) is almost empty on the probed score. Do not confuse the
    # model.Accidental class with a constructed detector output.
    masks = (predictions.clefs_keys > 0).astype(np.uint8)
    boxes, _ = components(masks)
    for x0, y0, x1, y1, area in boxes:
        width, height = x1-x0, y1-y0
        cx, cy = (x0+x1)/2, (y0+y1)/2
        nearest = []
        for index, head in enumerate(heads):
            hx, hy = head['center_model']; unit = head['unit']
            if .15*unit < hx-cx < 3.2*unit and abs(hy-cy) < 1.4*unit:
                nearest.append((hx-cx+abs(hy-cy), index))
        if not nearest:
            continue
        _, index = min(nearest)
        head = heads[index]; unit = head['unit']
        if .9*unit <= height <= 4.6*unit and .15*unit <= width <= 2.4*unit and area >= 8:
            entries.append({'origin': 'segnet.clefs_keys-component', 'staff': head['staff'],
                            'box_model': [x0, y0, x1, y1], 'area': area,
                            'nearest_head_index': index, 'position': head['position']})
    panels = []
    for index, entry in enumerate(entries):
        box = entry['box_model']
        entry['box_source'] = original_box(box, mapping)
        x0, y0, x1, y1 = map(lambda value: int(round(value)), box)
        crop = image[max(0,y0):min(len(image),y1),max(0,x0):min(image.shape[1],x1)]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        ink = (gray < 160).astype(np.uint8)
        entry['raw_components'] = len(components(ink)[0])
        entry['id'] = f'a{index:03d}'
        cv2.imwrite(str(out/(entry['id']+'-crop.png')), crop)
        np.save(out/(entry['id']+'-ink.npy'), ink)
        if 'nearest_head_index' in entry:
            head = heads[entry['nearest_head_index']]
            entry['head'] = head
            hx, hy = head['center_source']
            closest = min(predicted, key=lambda item: (item['center'][0]-hx)**2+(item['center'][1]-hy)**2)
            entry['nearest_predicted_note'] = closest
            entry['predicted_note_distance_source'] = float(np.hypot(closest['center'][0]-hx, closest['center'][1]-hy))
            unit = head['unit']
        else:
            unit = 18
        context = image[max(0,round(y0-unit)):min(image.shape[0],round(y1+unit)),
                        max(0,round(x0-unit)):min(image.shape[1],round(x1+4*unit))]
        panel = np.full((140, 260, 3), 255, np.uint8)
        if context.ndim == 2:
            context = cv2.cvtColor(context, cv2.COLOR_GRAY2BGR)
        scale = min(245/context.shape[1], 110/context.shape[0])
        resized = cv2.resize(context, (max(1,round(context.shape[1]*scale)), max(1,round(context.shape[0]*scale))))
        panel[25:25+resized.shape[0], :resized.shape[1]] = resized
        cv2.putText(panel, f"{entry['id']} staff{entry['staff']} pos{entry['position']}", (3,18), cv2.FONT_HERSHEY_SIMPLEX, .45, (0,0,180), 1)
        panels.append(panel)
    if panels:
        while len(panels)%5:
            panels.append(np.full((140,260,3),255,np.uint8))
        sheet = np.vstack([np.hstack(panels[i:i+5]) for i in range(0,len(panels),5)])
        cv2.imwrite(str(out/'candidate-contact.png'), sheet)
    report = {'source_image_sha256': sha(args.image), 'prediction_sha256': sha(args.prediction),
              'homr_version': importlib.metadata.version('homr'), 'segnet_model': str(segnet_path_onnx),
              'segnet_model_sha256': sha(segnet_path_onnx), 'source_sha256': source_hashes,
              'symbol_counts': dict(symbol_counts), 'staffs': staffs, 'heads': heads, 'detected_heads': len(heads),
              'candidate_count': len(entries), 'candidates': entries,
              'status': 'Untyped source evidence only; no reference MusicXML was read, and no pitch was changed.'}
    (out/'probe.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('source_image_sha256','prediction_sha256','homr_version','segnet_model_sha256','symbol_counts','detected_heads','candidate_count')}, indent=2))


def raw_candidates(args):
    sys.path.insert(0, str(ROOT/'web/src/py'))
    from accidental_glyphs import accidental_candidates, classify_accidental
    out = Path(args.out)
    prior = json.loads((out/'probe.json').read_text())
    if sha(args.image) != prior['source_image_sha256']:
        raise ValueError('Source image differs from detector receipt')
    image = cv2.imread(str(args.image))
    heads = [{'staff':h['staff'],'center':h['center_source'],'position':h['position']} for h in prior['heads']]
    candidates = accidental_candidates(image,[s['box'] for s in prior['staffs']],heads)
    panels, records = [], []
    for index, candidate in enumerate(candidates):
        identifier = f'cv{index:03d}'
        ink = candidate.pop('ink')
        np.save(out/(identifier+'-ink.npy'), ink)
        result = classify_accidental(ink) if args.classify else None
        record = {**candidate,'id':identifier,'classification':result}
        records.append(record)
        x0,y0,x1,y1 = candidate['box'];head=heads[candidate['head_index']]
        patch = image[max(0,y0-12):min(len(image),y1+12), max(0,x0-8):min(image.shape[1],max(x1+8,round(head['center'][0]+14)))]
        panel = np.full((140,260,3),255,np.uint8)
        scale = min(245/patch.shape[1],110/patch.shape[0])
        patch = cv2.resize(patch,(round(patch.shape[1]*scale),round(patch.shape[0]*scale)))
        panel[25:25+patch.shape[0],:patch.shape[1]] = patch
        cv2.putText(panel,identifier+(' '+str(result['kind']) if result else ''),(3,18),cv2.FONT_HERSHEY_SIMPLEX,.45,(0,0,180),1)
        panels.append(panel)
    if panels:
        while len(panels)%5:
            panels.append(np.full((140,260,3),255,np.uint8))
        cv2.imwrite(str(out/'raw-cv-contact.png'),np.vstack([np.hstack(panels[i:i+5]) for i in range(0,len(panels),5)]))
    result = {'source_image_sha256':prior['source_image_sha256'], 'candidates':records,
              'module_sha256':sha(ROOT/'web/src/py/accidental_glyphs.py'), 'count':len(records)}
    if args.labels:
        labels = json.loads(Path(args.labels).read_text())
        hits = []
        for label in labels:
            x,y = label['point']
            matches = [c for c in records if c['box'][0]-3 <= x <= c['box'][2]+3 and c['box'][1]-3 <= y <= c['box'][3]+3]
            hits.append({'label':label,'matched':[c['id'] for c in matches],
                         'classified_correct':any(c['classification'] and c['classification']['kind']==label['kind'] for c in matches)})
        result['visual_label_sha256'] = sha(args.labels)
        result['coverage'] = {'n':len(hits),'covered':sum(bool(h['matched']) for h in hits),'hits':hits,
                              'classified_correct':sum(h['classified_correct'] for h in hits) if args.classify else None}
    if args.classify:
        result['model_sha256'] = sha(ROOT/'web/src/py/accidental_classifier.json')
    (out/'raw-cv-probe.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('count','coverage') if k in result},indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--prediction', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--raw-cv',action='store_true',help='Reuse saved actual head/staff detector receipt; no second segmentation')
    parser.add_argument('--classify',action='store_true')
    parser.add_argument('--labels',type=Path,help='Optional source-image visual points, never reference MusicXML')
    arguments = parser.parse_args()
    (raw_candidates if arguments.raw_cv else run)(arguments)
