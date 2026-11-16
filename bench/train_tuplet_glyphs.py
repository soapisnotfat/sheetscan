# SPDX-License-Identifier: OFL-1.1
"""Reproducible synthetic-only training, dev gate selection, frozen font test.

Requires Pillow/NumPy/cv2 and (only for train) torch. No score images or ground
truth are read. All input font paths and bytes are SHA256 recorded. Download
the exact public OFL files listed in bench/tuplet-fonts/manifest.json first.

Example (repository root, environment with torch + cv2 + Pillow):
  ../.copisteria-venv/bin/python bench/train_tuplet_glyphs.py train --fonts /tmp/tuplet-glyph-fonts --out /tmp/tuplet-glyph-run
  ../.copisteria-venv/bin/python bench/train_tuplet_glyphs.py test --fonts /tmp/tuplet-glyph-fonts --out /tmp/tuplet-glyph-run

test never selects thresholds or changes model bytes. A freeze receipt hashes
the exported model before the unseen font is rasterized for the first time.
"""
import argparse
import base64
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'web/src/py'))
from tuplet_glyphs import normalize_ink

LABELS = ['unknown', '2', '3', '5', '6', '7', '9']
TRAIN_FONTS = ['Bravura', 'Leipzig', 'Leland']
TEST_FONTS = ['Sebastian']
SEEDS = {'train': 405132, 'dev': 405133, 'test': 405134}
COUNTS = {'train': (2200, 10000), 'dev': (500, 3000), 'test': (700, 4200)}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_fonts(directory, names):
    manifest = json.loads((ROOT/'bench/tuplet-fonts/manifest.json').read_text())
    for item in manifest['fonts']:
        if item['name'] in names and sha(font_path(directory, item['name'])) != item['sha256']:
            raise RuntimeError(f"Font bytes differ from frozen input: {item['name']}")


def prepare(args):
    directory = Path(args.fonts)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT/'bench/tuplet-fonts/manifest.json').read_text())
    for item in manifest['fonts']:
        target = directory/item['filename']
        if not target.exists():
            with urllib.request.urlopen(item['url'], timeout=60) as response:
                target.write_bytes(response.read())
        if sha(target) != item['sha256']:
            raise RuntimeError(f'Input SHA256 mismatch: {target}')
        print(item['name'], item['sha256'])


def font_path(directory, name):
    path = Path(directory)/(name+('.ttf' if name == 'NotoSans' else '.otf'))
    if not path.exists() and name in ('Bravura', 'Leipzig'):
        path = ROOT.parent/'fonts'/(name+'.otf')
    return path


@lru_cache(None)
def raster(path, codepoint):
    font = ImageFont.truetype(path, 200)
    character = chr(codepoint)
    if bytes(font.getmask(character)) == bytes(font.getmask(chr(0x10FFFD))):
        return None
    left, top, right, bottom = font.getbbox(character)
    image = Image.new('L', (right-left+16, bottom-top+16), 0)
    ImageDraw.Draw(image).text((8-left, 8-top), character, font=font, fill=255)
    ink = np.asarray(image)
    points = cv2.findNonZero((ink > 32).astype(np.uint8))
    if points is None:
        return None
    x, y, width, height = cv2.boundingRect(points)
    return ink[y:y+height, x:x+width].astype(np.float32)/255.


def available(directory, fonts, codes):
    result = []
    for name in fonts:
        path = str(font_path(directory, name))
        for codepoint in codes:
            value = raster(path, codepoint)
            if value is not None:
                result.append((name, codepoint, value))
    if not result:
        raise RuntimeError('No available font glyphs')
    return result


def distort(value, rng, staff=False):
    height = int(rng.integers(10, 37))
    ratio = value.shape[1]/value.shape[0]*rng.uniform(.84, 1.16)
    width = max(4, round(height*ratio))
    small = cv2.resize(value, (width, height), interpolation=cv2.INTER_AREA)
    # Printer/scanner sampling, small skew, and real binary component input.
    canvas = np.zeros((height+12, width+24), np.float32)
    canvas[6:6+height, 12:12+width] = small
    transform = cv2.getRotationMatrix2D((canvas.shape[1]/2, canvas.shape[0]/2), rng.uniform(-3.5, 3.5), 1)
    canvas = cv2.warpAffine(canvas, transform, (canvas.shape[1], canvas.shape[0]))
    if rng.random() < .35:
        canvas = cv2.GaussianBlur(canvas, (3, 3), rng.uniform(.15, .55))
    ink = (canvas > rng.uniform(.26, .65)).astype(np.uint8)
    if staff:
        # Staff lines are added BEFORE the exact production-like opening and
        # vertical closing. This deliberately erases coincident digit strokes.
        unit = height/rng.uniform(.8, 1.85)
        expanded = np.zeros((ink.shape[0], max(ink.shape[1], round(unit*13))), np.uint8)
        start = (expanded.shape[1]-ink.shape[1])//2
        expanded[:, start:start+ink.shape[1]] = ink
        yy = int(rng.integers(6, height+6))
        thickness = int(rng.choice([1, 1, 1, 2]))
        expanded[yy:yy+thickness, :] = 1
        for offset in (-1, 1):
            yline = round(yy+offset*unit)
            if 0 <= yline < len(expanded):
                expanded[yline:yline+thickness, :] = 1
        lines = cv2.morphologyEx(expanded, cv2.MORPH_OPEN, np.ones((1, max(12, round(unit*8))), np.uint8))
        expanded = cv2.morphologyEx(expanded-lines, cv2.MORPH_CLOSE, np.ones((3, 1), np.uint8))
        ink = expanded[:, start:start+ink.shape[1]]
    elif rng.random() < .12:
        # Small ink dropout is independent of the explicit line-overlap suite.
        yy = int(rng.integers(7, height+5))
        ink[yy, :] = 0
        ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((3, 1), np.uint8))
    points = cv2.findNonZero(ink)
    if points is None:
        return np.zeros((32, 24), np.float32)
    x, y, width, height = cv2.boundingRect(points)
    return normalize_ink(ink[y:y+height, x:x+width])


def primitive(rng):
    canvas = np.zeros((48, 48), np.float32)
    style = int(rng.integers(5))
    if style in (0, 1, 2):
        cv2.ellipse(canvas, (24, 29), (int(rng.integers(7, 13)), int(rng.integers(4, 8))),
                    float(rng.uniform(-35, -10)), 0, 360, 1, -1 if style != 1 else 2)
        if style == 2:
            cv2.line(canvas, (34, 29), (34, 2), 1, int(rng.integers(1, 3)))
    elif style == 3:
        cv2.line(canvas, (18, 5), (18, 41), 1, int(rng.integers(1, 4)))
        cv2.line(canvas, (18, 7), (38, 13), 1, int(rng.integers(2, 6)))
    else:
        for _ in range(int(rng.integers(1, 4))):
            cv2.line(canvas, tuple(rng.integers(4, 44, 2)), tuple(rng.integers(4, 44, 2)), 1, int(rng.integers(1, 4)))
    return canvas


def dataset(directory, split):
    rng = np.random.default_rng(SEEDS[split])
    names = TEST_FONTS if split == 'test' else TRAIN_FONTS
    per_class, negatives = COUNTS[split]
    samples, labels, groups = [], [], []
    for label in LABELS[1:]:
        number = int(label)
        bank = available(directory, names, [0xe880+number, 0xf4cc+number])
        for index in range(per_class):
            font, codepoint, value = bank[int(rng.integers(len(bank)))]
            staff = index % 2 == 0
            samples.append(distort(value, rng, staff))
            labels.append(LABELS.index(label))
            groups.append(f'{font}:positive:{"staff" if staff else "clean"}')
    # Noteheads, rests, accidentals, articulations, dynamics, time signature
    # digits, unsupported tuplet digits and ordinary alphanumeric text.
    music_codes = (list(range(0xe0a0, 0xe0ba))+list(range(0xe4e2, 0xe4ec))+
                   list(range(0xe260, 0xe26a))+list(range(0xe4a0, 0xe4c0))+
                   list(range(0xe520, 0xe52d))+list(range(0xe080, 0xe08a))+
                   [0xe880+i for i in (0, 1, 4, 8)])
    music = available(directory, names, music_codes)
    text = available(directory, ['NotoSans'], list(map(ord, '0123456789ABCDEFGHabcdefgmpfrsxyz')))
    for index in range(negatives):
        source = index % 4
        if source == 0:
            value, kind = primitive(rng), 'notehead-stem-primitive'
        else:
            bank = text if source == 1 else music
            font, codepoint, value = bank[int(rng.integers(len(bank)))]
            kind = 'text' if source == 1 else ('notehead' if 0xe0a0 <= codepoint < 0xe0ba else 'music-other')
        samples.append(distort(value, rng, index % 2 == 0))
        labels.append(0)
        groups.append('negative:'+kind)
    x = np.asarray(samples, dtype=np.float32)[:, None]
    y = np.asarray(labels, dtype=np.int64)
    digest = hashlib.sha256(x.tobytes()+y.tobytes()+'\n'.join(groups).encode()).hexdigest()
    return x, y, groups, digest


def model_class():
    import torch
    class Net(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = torch.nn.Conv2d(1, 8, 3, padding=1)
            self.conv2 = torch.nn.Conv2d(8, 16, 3, padding=1)
            self.fc1 = torch.nn.Linear(16*8*6, 32)
            self.fc2 = torch.nn.Linear(32, len(LABELS))

        def forward(self, x):
            x = torch.nn.functional.max_pool2d(torch.relu(self.conv1(x)), 2)
            x = torch.nn.functional.max_pool2d(torch.relu(self.conv2(x)), 2)
            return self.fc2(torch.relu(self.fc1(x.flatten(1))))
    return Net


def accept(logits, gates):
    order = np.argsort(logits, axis=1)[:, ::-1]
    predicted = order[:, 0].copy()
    score = logits[np.arange(len(logits)), predicted]
    margin = score-logits[np.arange(len(logits)), order[:, 1]]
    for index, label in enumerate(LABELS[1:], 1):
        gate = gates[label]
        reject = (predicted == index) & ((score < gate['score']) | (margin < gate['margin']))
        predicted[reject] = 0
    return predicted


def choose_gates(logits, labels):
    # Maximize retained true positives under <=0.1% dev-negative false positives
    # per digit, and <=0.5% wrong-digit rate among accepted detections.
    gates = {}
    negative_count = int(np.sum(labels == 0))
    for index, label in enumerate(LABELS[1:], 1):
        best = None
        for score in [0., 1., 2., 3., 4., 5., 6., 8.]:
            for margin in [.5, 1., 1.5, 2., 3., 4., 5., 6., 8.]:
                temporary = {item: {'score': score, 'margin': margin} for item in LABELS[1:]}
                pred = accept(logits, temporary)
                chosen = pred == index
                tp = int(np.sum(chosen & (labels == index)))
                fp = int(np.sum(chosen & (labels != index)))
                negative_fp = int(np.sum(chosen & (labels == 0)))
                if negative_fp > negative_count*.001 or fp > max(1, tp*.005):
                    continue
                objective = (tp, -fp, -score-margin)
                if best is None or objective > best[0]:
                    best = objective, {'score': score, 'margin': margin}
        gates[label] = best[1] if best else {'score': 1e6, 'margin': 1e6}
    return gates


def report(logits, labels, groups, gates, data_hash):
    prediction = accept(logits, gates)
    confusion = np.zeros((len(LABELS), len(LABELS)), dtype=int)
    for expected, got in zip(labels, prediction):
        confusion[expected, got] += 1
    positive, negative = labels != 0, labels == 0
    result = {'data_sha256': data_hash, 'samples': len(labels), 'labels': LABELS,
              'confusion_rows_expected_columns_predicted': confusion.tolist(),
              'positive_recall': float(np.mean(prediction[positive] == labels[positive])),
              'negative_rejection': float(np.mean(prediction[negative] == 0)),
              'accepted_precision': float(np.mean(prediction[prediction != 0] == labels[prediction != 0])),
              'per_class': {}, 'groups': {}}
    for index, label in enumerate(LABELS[1:], 1):
        actual = labels == index
        selected = prediction == index
        result['per_class'][label] = {'n': int(sum(actual)), 'recall': float(np.mean(prediction[actual] == index)),
                                     'precision': float(np.mean(labels[selected] == index)) if sum(selected) else None}
    for group in sorted(set(groups)):
        mask = np.asarray(groups) == group
        result['groups'][group] = {'n': int(sum(mask)), 'correct': int(sum(prediction[mask] == labels[mask])),
                                   'accepted_wrong': int(sum((prediction[mask] != 0) & (prediction[mask] != labels[mask])))}
    return result


def train(args):
    import torch
    torch.set_num_threads(4)
    torch.manual_seed(78124)
    np.random.seed(78124)
    verify_fonts(args.fonts, TRAIN_FONTS+['NotoSans'])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    x, y, groups, train_hash = dataset(args.fonts, 'train')
    dx, dy, dgroups, dev_hash = dataset(args.fonts, 'dev')
    np.savez_compressed(out/'dev.npz', x=dx, y=dy, groups=dgroups)
    net = model_class()()
    optimizer = torch.optim.AdamW(net.parameters(), lr=.0015, weight_decay=.0003)
    weights = torch.tensor([.55, 1, 1, 1, 1, 1, 1.])
    loss_function = torch.nn.CrossEntropyLoss(weight=weights)
    data = torch.utils.data.TensorDataset(torch.from_numpy(x), torch.from_numpy(y))
    loader = torch.utils.data.DataLoader(data, batch_size=256, shuffle=True, num_workers=0)
    started = time.time()
    history = []
    for epoch in range(args.epochs):
        net.train()
        losses = []
        for bx, by in loader:
            optimizer.zero_grad()
            loss = loss_function(net(bx), by)
            loss.backward()
            optimizer.step()
            losses.append(float(loss))
        net.eval()
        with torch.no_grad():
            logits = torch.cat([net(batch) for batch in torch.from_numpy(dx).split(512)]).numpy()
        accuracy = float(np.mean(logits.argmax(1) == dy))
        item = {'epoch': epoch+1, 'loss': float(np.mean(losses)), 'dev_argmax_accuracy': accuracy}
        history.append(item)
        print(json.dumps(item), flush=True)
    gates = choose_gates(logits, dy)
    metadata = {'format': 'tuplet-cnn-f16-v1', 'labels': LABELS, 'input_shape': [1, 32, 24],
                'score_semantics': 'raw logits, not calibrated confidence', 'gates': gates,
                'training_seed': 78124, 'split_seeds': SEEDS, 'train_fonts': TRAIN_FONTS,
                'unseen_test_fonts': TEST_FONTS, 'train_data_sha256': train_hash,
                'dev_data_sha256': dev_hash, 'weights': {}}
    for key, value in net.state_dict().items():
        array = value.numpy().astype('<f2')
        metadata['weights'][key] = {'shape': list(array.shape), 'data': base64.b64encode(array.tobytes()).decode()}
    model_path = ROOT/'web/src/py/tuplet_classifier.json'
    model_path.write_text(json.dumps(metadata, separators=(',', ':'))+'\n')
    torch.save(net.state_dict(), out/'training-only.pt')
    # Evaluate actual exported float16 weights through torch after roundtrip.
    for key in net.state_dict():
        net.state_dict()[key].copy_(torch.from_numpy(np.frombuffer(base64.b64decode(metadata['weights'][key]['data']), '<f2').astype(np.float32).reshape(metadata['weights'][key]['shape'])))
    with torch.no_grad():
        logits = torch.cat([net(batch) for batch in torch.from_numpy(dx).split(512)]).numpy()
    receipt = {'frozen_model_sha256': sha(model_path), 'model_bytes': model_path.stat().st_size,
               'train_data_sha256': train_hash, 'dev_data_sha256': dev_hash,
               'font_sha256': {name: sha(font_path(args.fonts, name)) for name in TRAIN_FONTS+['NotoSans']},
               'gates': gates, 'epochs': args.epochs, 'elapsed_seconds': time.time()-started,
               'history': history, 'dev': report(logits, dy, dgroups, gates, dev_hash),
               'hold_font_test_accessed': False}
    (out/'freeze.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({key: receipt[key] for key in ('frozen_model_sha256', 'model_bytes', 'elapsed_seconds', 'dev')}, indent=2))


def test(args):
    import torch
    torch.set_num_threads(4)
    out = Path(args.out)
    verify_fonts(args.fonts, TEST_FONTS+['NotoSans'])
    receipt = json.loads((out/'freeze.json').read_text())
    model_path = ROOT/'web/src/py/tuplet_classifier.json'
    if sha(model_path) != receipt['frozen_model_sha256']:
        raise RuntimeError('Model changed after freeze; unseen-font results invalid')
    metadata = json.loads(model_path.read_text())
    net = model_class()()
    state = {key: torch.from_numpy(np.frombuffer(base64.b64decode(value['data']), '<f2').astype(np.float32).reshape(value['shape'])) for key, value in metadata['weights'].items()}
    net.load_state_dict(state)
    net.eval()
    x, y, groups, data_hash = dataset(args.fonts, 'test')
    with torch.no_grad():
        logits = torch.cat([net(batch) for batch in torch.from_numpy(x).split(512)]).numpy()
    result = {'frozen_model_sha256': sha(model_path), 'test_font_sha256': {name: sha(font_path(args.fonts, name)) for name in TEST_FONTS},
              'test': report(logits, y, groups, metadata['gates'], data_hash)}
    (out/'unseen-font-test.json').write_text(json.dumps(result, indent=2)+'\n')
    np.savez_compressed(out/'unseen-test.npz', x=x, y=y, groups=groups, logits=logits)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('mode', choices=['prepare', 'train', 'test'])
    parser.add_argument('--fonts', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--epochs', type=int, default=22)
    arguments = parser.parse_args()
    {'prepare': prepare, 'train': train, 'test': test}[arguments.mode](arguments)
