// Actual Chromium renderer + Pyodide extraction + unchanged browser readNumber.
// node bench/probe_multirests_browser.mjs /tmp/multirest-browser [--render-only]
import fs from 'node:fs/promises'
import path from 'node:path'
import http from 'node:http'
import {pathToFileURL,fileURLToPath} from 'node:url'
import {createHash} from 'node:crypto'
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),out=path.resolve(process.argv[2]||'/tmp/multirest-browser')
const {chromium}=await import(pathToFileURL(path.join(root,'web/node_modules/playwright/index.mjs')))
const createVerovioModule=(await import(pathToFileURL(path.join(root,'web/node_modules/verovio/dist/verovio-module.mjs')))).default
const {VerovioToolkit}=await import(pathToFileURL(path.join(root,'web/node_modules/verovio/dist/verovio.mjs')))
await fs.mkdir(out,{recursive:true})
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'})
const page=await browser.newPage({viewport:{width:1653,height:2339}}),tk=new VerovioToolkit(await createVerovioModule()),cases=[]
try {
 for(const font of ['Bravura','Leipzig']) for(const style of ['symbols','H']){
  const source=path.join(root,'bench/fixtures/multirest-families',style+'.musicxml'),xml=await fs.readFile(source,'utf8')
  tk.resetOptions();tk.setOptions({pageWidth:2100,pageHeight:2970,scale:45,breaks:'encoded',font,adjustPageHeight:false,xmlIdSeed:2121})
  tk.loadData(xml)
  const spec=JSON.parse(await fs.readFile(path.join(root,'bench/fixtures/multirest-families',style+'-spec.json'),'utf8'))
  for(let p=1;p<=tk.getPageCount();p++){
   const svg=tk.renderToSVG(p),name=font+'-'+style+'-'+p
   await fs.writeFile(path.join(out,name+'.svg'),svg)
   await page.setContent(`<style>body{margin:0;background:white}svg{display:block;width:1653px;height:2339px}</style>${svg}`)
   const boxes=await page.evaluate(()=>{const pieces=[...document.querySelectorAll('g.staff')].map(staff=>{
    const lines=[...staff.children].filter(e=>e.tagName.toLowerCase()==='path').map(e=>e.getBoundingClientRect()).filter(b=>b.width>60&&b.height<2).sort((a,b)=>a.top-b.top)
    return lines.length>=5?[Math.round(lines[0].left),Math.round(lines[0].top),Math.round(lines[0].right),Math.round(lines[4].top)]:null
   }).filter(Boolean);const merged=[];for(const b of pieces){const match=merged.find(a=>Math.abs(a[1]-b[1])<=1&&Math.abs(a[3]-b[3])<=1);if(match){match[0]=Math.min(match[0],b[0]);match[2]=Math.max(match[2],b[2])}else merged.push([...b])}return merged})
   const image=path.join(out,name+'.png');await page.screenshot({path:image})
   cases.push({name,image,boxes,counts:spec.slice(0,boxes.length).map(s=>s.count),source_sha256:createHash('sha256').update(xml).digest('hex'),image_sha256:createHash('sha256').update(await fs.readFile(image)).digest('hex')})
  }
 }
 await fs.writeFile(path.join(out,'rendered.json'),JSON.stringify(cases,null,2)+'\n')
 if(process.argv.includes('--render-only')){console.log(JSON.stringify(cases,null,2));process.exitCode=0}
 else {
  const observed=path.join(root,'dev-samples/independent-eval/validated-v3/browser-v8/rests-v3-render-corrected/input-1.png')
  const reading=await fs.readFile(path.join(root,'dev-samples/independent-eval/validated-v3/browser-v8/rests-v3-render-corrected/worker-0-result.musicxml'),'utf8')
  const text=reading.match(/<miscellaneous-field name="staff-layout">([^<]+)</)?.[1]
  cases.push({name:'observed-corrected-v3',image:observed,boxes:JSON.parse(text)[0]})
  const html=`<!doctype html><script type="module">
import {loadPyodide} from '/pyodide/pyodide.mjs';import {readNumber} from '/ocr.js';
try {const py=await loadPyodide({indexURL:'/pyodide/'});await py.loadPackage(['numpy','opencv-python']);py.FS.mkdirTree('/work');py.FS.writeFile('/work/score_numbers.py',await(await fetch('/score_numbers.py')).text());py.runPython("import sys;sys.path.insert(0,'/work');import cv2,json;from score_numbers import read_multirest_regions");const cases=await(await fetch('/cases.json')).json(),results=[];
for(let i=0;i<cases.length;i++){const bytes=new Uint8Array(await(await fetch('/image/'+i)).arrayBuffer());py.FS.writeFile('/work/input.png',bytes);py.globals.set('boxes_json',JSON.stringify(cases[i].boxes));const regions=JSON.parse(py.runPython("json.dumps(read_multirest_regions(cv2.imread('/work/input.png'),json.loads(boxes_json)))"));for(const region of regions){region.reading=await readNumber({png:bytes},region.numberBox);if(!region.reading){const staff=cases[i].boxes[region.staff],unit=(staff[3]-staff[1])/4;region.paddingTrials=[];for(const margin of [.5,1,2]){const [a,b,c,d]=region.numberBox,box=[Math.max(0,Math.round(a-margin*unit)),Math.max(0,Math.round(b-.3*unit)),Math.round(c+margin*unit),d];region.paddingTrials.push({margin,box,reading:await readNumber({png:bytes},box)});}}}results.push({name:cases[i].name,regions});console.log(JSON.stringify(results.at(-1)));}window.result={pyodide:py.version,browser:navigator.userAgent,results};}catch(e){window.error=String(e.stack||e);}</script>`
  const exists=async p=>{try{await fs.access(p);return true}catch{return false}}
  const server=http.createServer(async(req,res)=>{let file;
   if(req.url==='/'){res.setHeader('Content-Type','text/html');res.end(html);return}
   if(req.url==='/cases.json'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify(cases));return}
   if(req.url.startsWith('/image/'))file=cases[Number(req.url.split('/').at(-1))]?.image
   else if(req.url==='/score_numbers.py')file=path.join(root,'web/src/py/score_numbers.py')
   else if(req.url==='/ocr.js')file=path.join(root,'web/src/ocr.js')
   else if(req.url.startsWith('/pyodide/')){const name=path.basename(req.url),cache=path.join('/tmp/tuplet-glyph-run/pyodide',name);file=await exists(cache)?cache:path.join(root,'web/node_modules/pyodide',name)}
   if(!file||!await exists(file)){res.statusCode=404;res.end('missing');return}
   res.setHeader('Content-Type',file.endsWith('.mjs')||file.endsWith('.js')?'text/javascript':file.endsWith('.wasm')?'application/wasm':'application/octet-stream');res.end(await fs.readFile(file))
  });await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve))
  try {const test=await browser.newPage();test.on('console',m=>console.log('browser:',m.text()));test.on('pageerror',e=>console.error(e));await test.goto('http://127.0.0.1:'+server.address().port+'/');await test.waitForFunction(()=>window.result||window.error,null,{timeout:600000});const result=await test.evaluate(()=>({result:window.result,error:window.error}));if(result.error)throw Error(result.error);result.result.module_sha256=createHash('sha256').update(await fs.readFile(path.join(root,'web/src/py/score_numbers.py'))).digest('hex');result.result.ocr_sha256=createHash('sha256').update(await fs.readFile(path.join(root,'web/src/ocr.js'))).digest('hex');await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify(result.result,null,2)+'\n');console.log(JSON.stringify(result.result,null,2))}finally{server.close()}
 }
}finally {await browser.close()}
