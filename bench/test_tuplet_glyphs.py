# SPDX-License-Identifier: OFL-1.1
"""Runtime checks plus optional PyTorch-to-browser-NumPy parity evidence.

  ../.venv/bin/python bench/test_tuplet_glyphs.py
  ../.copisteria-venv/bin/python bench/test_tuplet_glyphs.py --run /tmp/tuplet-glyph-run

The optional parity mode reads only the synthetic development archive generated
by train_tuplet_glyphs.py. It never reads score images or independent-eval files.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest
import subprocess

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'web/src/py'))
from tuplet_glyphs import _convolution, _pool, classify_glyph, glyph_logits, normalize_ink


class RuntimeTests(unittest.TestCase):
    def test_normalization_is_same_for_byte_and_unit_ink(self):
        array = np.zeros((17, 13), np.uint8)
        array[2:15, 3:8] = 255
        self.assertTrue(np.array_equal(normalize_ink(array), normalize_ink(array/255.)))
        self.assertEqual(normalize_ink(array).shape, (32, 24))
        overshoot = np.ones((32, 24), np.float32)*(1+np.finfo(np.float32).eps)
        self.assertEqual(float(normalize_ink(overshoot).min()), 1.)

    def test_invalid_input_rejected(self):
        for array in (np.zeros((2, 2, 3)), np.zeros((0, 2)), np.array([[np.nan]])):
            with self.assertRaises(ValueError):
                classify_glyph(array)

    def test_zero_and_notehead_rejected(self):
        array = np.zeros((20, 24), np.float32)
        cv2.ellipse(array, (12, 10), (11, 6), -25, 0, 360, 1, -1)
        for ink in (np.zeros((32, 24)), array):
            answer = classify_glyph(ink)
            self.assertTrue(answer['unknown'], answer)
            self.assertIsNone(answer['number'])
            self.assertTrue(np.isfinite(answer['score']))
            self.assertGreaterEqual(answer['margin'], 0)

    def test_convolution_and_pool_reference(self):
        array = np.arange(48, dtype=np.float32).reshape(2, 4, 6)/20
        weight = np.ones((3, 2, 3, 3), np.float32)
        actual = _convolution(array, weight, np.array([-1, 0, 1], np.float32))
        padded = np.pad(array, ((0, 0), (1, 1), (1, 1)))
        for channel in range(3):
            for y in range(4):
                for x in range(6):
                    expected = max(0, padded[:, y:y+3, x:x+3].sum()+channel-1)
                    self.assertAlmostEqual(float(actual[channel, y, x]), float(expected), places=4)
        pooled = _pool(array)
        self.assertEqual(pooled.shape, (2, 2, 3))
        self.assertEqual(pooled[0, 0, 0], array[0, :2, :2].max())


def parity(run):
    import torch
    from train_tuplet_glyphs import model_class
    torch.set_num_threads(2)
    path = ROOT/'web/src/py/tuplet_classifier.json'
    metadata = json.loads(path.read_text())
    net = model_class()()
    net.load_state_dict({key: torch.from_numpy(np.frombuffer(base64.b64decode(value['data']), '<f2').astype(np.float32).reshape(value['shape'])) for key, value in metadata['weights'].items()})
    net.eval()
    dataset = np.load(Path(run)/'dev.npz')
    indices = np.random.default_rng(128903).choice(len(dataset['x']), 128, replace=False)
    sample = dataset['x'][indices]
    started = time.perf_counter()
    actual = np.asarray([glyph_logits(ink[0]) for ink in sample])
    elapsed = time.perf_counter()-started
    with torch.no_grad():
        expected = net(torch.from_numpy(sample)).numpy()
    maximum = float(np.max(np.abs(actual-expected)))
    if maximum > .0002 or not np.array_equal(actual.argmax(1), expected.argmax(1)):
        raise AssertionError(f'NumPy export parity failed: maximum logit error={maximum}')
    result = {'model_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'synthetic_dev_samples': len(sample),
              'maximum_absolute_logit_error': maximum, 'argmax_agreement': 1.,
              'numpy_inference_ms_per_crop': elapsed/len(sample)*1000,
              'scope': 'CPython NumPy/cv2; browser WASM runtime not measured here'}
    (Path(run)/'runtime-parity.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


def browser_parity(run):
    """Test real Pyodide in Chrome; wheels must be cached under RUN/pyodide.

    Cache numpy/opencv-python wheels from the exact pyodide-lock.json URL at
    https://cdn.jsdelivr.net/pyodide/v314.0.7/full/ before running. The browser
    test serves local files only, including the installed pyodide JS/WASM.
    """
    run = Path(run).resolve()
    dataset = np.load(run/'dev.npz')
    indices = np.random.default_rng(128903).choice(len(dataset['x']), 128, replace=False)
    sample = dataset['x'][indices, 0]
    fixture = {'ink': sample.tolist(), 'expected_logits': [glyph_logits(ink).tolist() for ink in sample]}
    (run/'browser-samples.json').write_text(json.dumps(fixture, separators=(',', ':')))
    script = r'''
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { pathToFileURL } from 'node:url';
const [root, run] = process.argv.slice(2);
const { chromium } = await import(pathToFileURL(path.join(root, 'web/node_modules/playwright/index.mjs')));
const html = `<!doctype html><title>Tuplet glyph WASM parity</title><script type="module">
import {loadPyodide} from '/pyodide/pyodide.mjs';
try {
const py = await loadPyodide({indexURL: '/pyodide/'});
await py.loadPackage(['numpy','opencv-python']);
py.FS.mkdirTree('/work');
for (const name of ['tuplet_glyphs.py','tuplet_classifier.json']) py.FS.writeFile('/work/'+name, await (await fetch('/'+name)).text());
const fixture = await (await fetch('/samples.json')).json();
py.globals.set('sample_json', JSON.stringify(fixture.ink));
window.result = JSON.parse(py.runPython(${JSON.stringify([
"import sys,json,time,numpy as np", "sys.path.insert(0,'/work')",
"from tuplet_glyphs import glyph_logits,classify_glyph",
"samples=np.array(json.loads(sample_json),dtype=np.float32)",
"started=time.perf_counter()", "logits=[glyph_logits(s).tolist() for s in samples]",
"elapsed=time.perf_counter()-started",
"json.dumps({'logits':logits,'elapsed_seconds':elapsed,'predictions':[classify_glyph(s)['number'] for s in samples]})"
].join('\n'))}));
let maximum=0, matches=0;
for(let i=0;i<fixture.ink.length;i++) {
 const a=window.result.logits[i], b=fixture.expected_logits[i];
 for(let j=0;j<a.length;j++) maximum=Math.max(maximum,Math.abs(a[j]-b[j]));
 if(a.indexOf(Math.max(...a))===b.indexOf(Math.max(...b))) matches++;
}
window.result = {samples:fixture.ink.length, maximum_absolute_logit_error:maximum,argmax_agreement:matches/fixture.ink.length,
 wasm_inference_ms_per_crop:window.result.elapsed_seconds/fixture.ink.length*1000,
 pyodide_version:py.version, browser:navigator.userAgent};
} catch (e) {window.error=String(e.stack||e);}
</script>`;
const server=http.createServer((req,res)=>{
 let file;
 if(req.url==='/') {res.setHeader('Content-Type','text/html');res.end(html);return;}
 if(req.url==='/samples.json') file=path.join(run,'browser-samples.json');
 else if(req.url==='/tuplet_glyphs.py'||req.url==='/tuplet_classifier.json') file=path.join(root,'web/src/py',path.basename(req.url));
 else if(req.url.startsWith('/pyodide/')) {
   const name=path.basename(req.url);
   file=fs.existsSync(path.join(run,'pyodide',name))?path.join(run,'pyodide',name):path.join(root,'web/node_modules/pyodide',name);
 }
 if(!file||!fs.existsSync(file)) {res.statusCode=404;res.end('missing');return;}
 res.setHeader('Content-Type',file.endsWith('.mjs')?'text/javascript':file.endsWith('.wasm')?'application/wasm':'application/octet-stream');
 fs.createReadStream(file).pipe(res);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try {
 browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage();
 page.on('console', message=>console.log('browser:',message.text()));
 page.on('pageerror', error=>console.error('pageerror:',error));
 await page.goto('http://127.0.0.1:'+server.address().port+'/');
 await page.waitForFunction(()=>window.result||window.error,null,{timeout:180000});
 const result=await page.evaluate(()=>({result:window.result,error:window.error}));
 if(result.error) throw Error(result.error);
 if(result.result.maximum_absolute_logit_error>.0002||result.result.argmax_agreement!==1) throw Error(JSON.stringify(result.result));
 fs.writeFileSync(path.join(run,'browser-parity.json'),JSON.stringify(result.result,null,2)+'\n');
 console.log(JSON.stringify(result.result,null,2));
} finally {if(browser) await browser.close();server.close();}
'''
    (run/'browser-parity.mjs').write_text(script)
    subprocess.run(['node', str(run/'browser-parity.mjs'), str(ROOT), str(run)], check=True)


def template_baseline(run):
    """Optional post-freeze comparison using the original 2/5 template gates."""
    run = Path(run)
    model = ROOT/'web/src/py/tuplet_classifier.json'
    receipt = json.loads((run/'freeze.json').read_text())
    if hashlib.sha256(model.read_bytes()).hexdigest() != receipt['frozen_model_sha256']:
        raise ValueError('Refusing a baseline after model bytes changed')
    path = ROOT/'web/src/py/tuplet_templates.json'
    archive = np.load(run/'unseen-test.npz')
    x, labels = archive['x'][:, 0], archive['y']
    actual = np.array([0 if value == 0 else int(receipt['dev']['labels'][value]) for value in labels])
    scores = {}
    for item in json.loads(path.read_text()):
        template = np.frombuffer(base64.b64decode(item['raster']), np.uint8).reshape(32, 24).astype(np.float32)/255
        similarity = np.sum(x*template, axis=(1, 2))/np.sqrt(np.maximum(np.sum(x*x, axis=(1, 2))*np.sum(template*template), 1e-12))
        number = item['number']
        scores[number] = np.maximum(scores.get(number, np.zeros(len(x))), similarity)
    numbers = sorted(scores)
    matrix = np.stack([scores[number] for number in numbers], axis=1)
    order = np.argsort(matrix, axis=1)[:, ::-1]
    predicted = []
    for index, row in enumerate(order):
        number = numbers[row[0]]
        score, margin = matrix[index, row[0]], matrix[index, row[0]]-matrix[index, row[1]]
        minimum, separation = (.85, .06) if number == 5 else (.8, .12)
        predicted.append(number if number in (2, 5) and score >= minimum and margin >= separation else 0)
    predicted = np.asarray(predicted)
    positive, negative, accepted = np.isin(actual, [2, 5]), actual == 0, predicted != 0
    result = {'scope': 'Frozen unseen crops, original cosine bank with 2/5 gates; no candidate-extraction comparison',
              'template_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'samples_2_or_5': int(sum(positive)), 'recall_2_or_5': float(np.mean(predicted[positive] == actual[positive])),
              'negative_rejection': float(np.mean(predicted[negative] == 0)),
              'accepted_precision': float(np.mean(predicted[accepted] == actual[accepted])),
              'per_digit': {str(number): {'n': int(sum(actual == number)), 'correct': int(sum((actual == number) & (predicted == number)))} for number in [2, 5]}}
    (run/'template-baseline.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run')
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--template-baseline', action='store_true')
    args, remaining = parser.parse_known_args()
    tests = unittest.main(argv=[sys.argv[0]]+remaining, exit=False)
    if not tests.result.wasSuccessful():
        raise SystemExit(1)
    if args.run:
        parity(args.run)
        if args.browser:
            browser_parity(args.run)
        if args.template_baseline:
            template_baseline(args.run)
