# SPDX-License-Identifier: OFL-1.1
"""Runtime/reference, extraction, and optional actual Chrome/Pyodide parity.

python bench/test_accidental_glyphs.py --run /tmp/accidental-glyph-run --browser
Browser mode uses installed Playwright/Chrome and locally cached NumPy/OpenCV
wheels under RUN/pyodide (same exact packages as the tuplet runtime test).
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'web/src/py'))
from accidental_glyphs import accidental_candidates,accidental_logits,classify_accidental,normalize_ink,read_accidentals


class Tests(unittest.TestCase):
    def test_unit_byte_and_overshoot(self):
        a=np.zeros((19,11),np.uint8);a[2:17,3:7]=255
        np.testing.assert_array_equal(normalize_ink(a),normalize_ink(a/255.))
        self.assertEqual(float(normalize_ink(np.ones((32,24),np.float32)*(1+np.finfo(np.float32).eps)).min()),1)

    def test_invalid(self):
        for a in [np.zeros((1,2,3)),np.zeros((0,1)),np.array([[np.nan]])]:
            with self.assertRaises(ValueError):classify_accidental(a)

    def test_empty_is_unknown(self):
        self.assertIsNone(classify_accidental(np.zeros((32,24)))['kind'])

    def test_staff_crossing_candidate_uses_segmented_head(self):
        im=np.full((90,120),255,np.uint8)
        for y in [20,30,40,50,60]:cv2.line(im,(0,y),(119,y),0,1)
        cv2.line(im,(44,29),(44,62),0,2);cv2.line(im,(53,37),(53,70),0,2)
        cv2.line(im,(44,45),(53,41),0,3);cv2.line(im,(44,58),(53,54),0,3)
        cv2.ellipse(im,(71,52),(7,4),-20,0,360,0,-1)
        candidates=accidental_candidates(im,[[0,20,120,60]],[{'staff':0,'center':[71,52],'position':4}])
        self.assertTrue(any(c['box'][0]<=48<=c['box'][2] and c['box'][1]<=50<=c['box'][3] for c in candidates),candidates)
        self.assertTrue(all(c['head_index']==0 and c['position']==4 for c in candidates))
        typed=read_accidentals(im,[[0,20,120,60]],[{'staff':0,'center':[71,52],'position':np.int64(4),'id':'note-id'}])
        json.dumps(typed)
        self.assertTrue(all(c['head_id']=='note-id' and len(c['center'])==2 for c in typed))


def parity(run,browser=False):
    import torch
    from train_accidental_glyphs import load_export
    torch.set_num_threads(2);run=Path(run).resolve()
    data=np.load(run/'dev.npz');indices=np.random.default_rng(906490).choice(len(data['x']),128,replace=False);x=data['x'][indices]
    model,net=load_export()
    start=time.perf_counter();actual=np.asarray([accidental_logits(a[0]) for a in x]);elapsed=time.perf_counter()-start
    with torch.no_grad():expected=net(torch.from_numpy(x)).numpy()
    maximum=float(np.max(np.abs(actual-expected)));agreement=float(np.mean(actual.argmax(1)==expected.argmax(1)))
    if maximum>.0002 or agreement!=1:raise AssertionError((maximum,agreement))
    result={'model_sha256':hashlib.sha256((ROOT/'web/src/py/accidental_classifier.json').read_bytes()).hexdigest(),
            'samples':128,'maximum_absolute_logit_error':maximum,'argmax_agreement':agreement,'cpython_ms_per_crop':elapsed/128*1000}
    (run/'runtime-parity.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not browser:return
    fixture={'ink':x[:,0].tolist(),'expected_logits':actual.tolist()}
    (run/'browser-samples.json').write_text(json.dumps(fixture,separators=(',',':')))
    script=r'''
import fs from 'node:fs';import path from 'node:path';import http from 'node:http';import {pathToFileURL} from 'node:url';
const [root,run]=process.argv.slice(2);
const {chromium}=await import(pathToFileURL(path.join(root,'web/node_modules/playwright/index.mjs')));
const code=["import sys,json,time,numpy as np","sys.path.insert(0,'/work')","from accidental_glyphs import accidental_logits","samples=np.array(json.loads(sample_json),dtype=np.float32)","start=time.perf_counter()","logits=[accidental_logits(s).tolist() for s in samples]","json.dumps({'logits':logits,'seconds':time.perf_counter()-start})"].join(String.fromCharCode(10));
const html=`<!doctype html><script type="module">
import {loadPyodide} from '/pyodide/pyodide.mjs';
try {const py=await loadPyodide({indexURL:'/pyodide/'});await py.loadPackage(['numpy','opencv-python']);py.FS.mkdirTree('/work');
for(const name of ['accidental_glyphs.py','accidental_classifier.json'])py.FS.writeFile('/work/'+name,await(await fetch('/'+name)).text());
const fixture=await(await fetch('/samples.json')).json();py.globals.set('sample_json',JSON.stringify(fixture.ink));
const answer=JSON.parse(py.runPython(${JSON.stringify(code)}));let maximum=0,matches=0;
for(let i=0;i<fixture.ink.length;i++){const a=answer.logits[i],b=fixture.expected_logits[i];for(let j=0;j<a.length;j++)maximum=Math.max(maximum,Math.abs(a[j]-b[j]));if(a.indexOf(Math.max(...a))===b.indexOf(Math.max(...b)))matches++;}
window.result={samples:fixture.ink.length,maximum_absolute_logit_error:maximum,argmax_agreement:matches/fixture.ink.length,wasm_ms_per_crop:answer.seconds/fixture.ink.length*1000,pyodide_version:py.version,browser:navigator.userAgent};
}catch(e){window.error=String(e.stack||e);}</script>`;
const server=http.createServer((req,res)=>{let file;if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end(html);return;}
if(req.url==='/samples.json')file=path.join(run,'browser-samples.json');
else if(['/accidental_glyphs.py','/accidental_classifier.json'].includes(req.url))file=path.join(root,'web/src/py',path.basename(req.url));
else if(req.url.startsWith('/pyodide/')){const name=path.basename(req.url);file=fs.existsSync(path.join(run,'pyodide',name))?path.join(run,'pyodide',name):path.join(root,'web/node_modules/pyodide',name);}
if(!file||!fs.existsSync(file)){res.statusCode=404;res.end('missing');return;}res.setHeader('Content-Type',file.endsWith('.mjs')?'text/javascript':file.endsWith('.wasm')?'application/wasm':'application/octet-stream');fs.createReadStream(file).pipe(res);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser;
try{browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});const page=await browser.newPage();page.on('pageerror',e=>console.error(e));await page.goto('http://127.0.0.1:'+server.address().port+'/');await page.waitForFunction(()=>window.result||window.error,null,{timeout:180000});const answer=await page.evaluate(()=>({result:window.result,error:window.error}));if(answer.error)throw Error(answer.error);if(answer.result.maximum_absolute_logit_error>.0002||answer.result.argmax_agreement!==1)throw Error(JSON.stringify(answer));fs.writeFileSync(path.join(run,'browser-parity.json'),JSON.stringify(answer.result,null,2)+'\n');console.log(JSON.stringify(answer.result,null,2));}finally{if(browser)await browser.close();server.close();}
'''
    (run/'browser-parity.mjs').write_text(script)
    subprocess.run(['node',str(run/'browser-parity.mjs'),str(ROOT),str(run)],check=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run');p.add_argument('--browser',action='store_true');args,remaining=p.parse_known_args()
    tests=unittest.main(argv=[sys.argv[0]]+remaining,exit=False)
    if not tests.result.wasSuccessful():raise SystemExit(1)
    if args.run:parity(args.run,args.browser)
