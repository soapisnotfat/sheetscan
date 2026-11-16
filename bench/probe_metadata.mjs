// Original PDF text/OCR evidence probe. No reference score/target metadata read.
// node bench/probe_metadata.mjs /tmp/metadata-probe [--no-ocr]
import fs from 'node:fs/promises'
import path from 'node:path'
import {fileURLToPath,pathToFileURL} from 'node:url'
import {createHash} from 'node:crypto'
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),out=path.resolve(process.argv[2]||'/tmp/metadata-probe')
await fs.mkdir(out,{recursive:true})
const {createServer}=await import(pathToFileURL(path.join(root,'web/node_modules/vite/dist/node/index.js')))
const {chromium}=await import(pathToFileURL(path.join(root,'web/node_modules/playwright/index.mjs')))
// Private source paths are supplied in a local JSON file, never bundled here.
const sourceArg=process.argv.find(a=>a.startsWith('--sources='))?.slice(10)
if(!sourceArg)throw Error('Pass --sources=LOCAL_JSON with [{name,file}]; no private source path is bundled')
const sources=JSON.parse(await fs.readFile(path.resolve(sourceArg),'utf8'))
const html=`<!doctype html><script type="module">
import {loadPages} from '/src/input.js';
import {tokens,readTempos} from '/src/annotate.js';
try {const sources=await(await fetch('/metadata-sources')).json();let worker;
if(!${process.argv.includes('--no-ocr')}){const tess=await import('https://cdn.jsdelivr.net/npm/tesseract.js@7.0.0/dist/tesseract.esm.min.js');worker=await(tess.default??tess).createWorker(['eng','deu']);await worker.setParameters({tessedit_pageseg_mode:'11'});}
const results=[];
for(let i=0;i<sources.length;i++){const bytes=await(await fetch('/metadata-input/'+i)).arrayBuffer(),file=new File([bytes],sources[i].filename,{type:sources[i].filename.endsWith('.pdf')?'application/pdf':'image/png'}),pages=await loadPages([file]);
for(let p=0;p<pages.length;p++){const page=pages[p];await fetch('/metadata-save/'+sources[i].name+'-'+p+'.png',{method:'POST',body:page.png});const raw=worker?await worker.recognize(page.url,{}, {blocks:true}):null;
const words=(raw?.data.blocks??[]).flatMap(b=>b.paragraphs??[]).flatMap(p=>p.lines??[]).flatMap(l=>l.words??[]).map(w=>({str:w.text,confidence:w.confidence,x:w.bbox.x0,y:w.bbox.y1,w:w.bbox.x1-w.bbox.x0,h:w.bbox.y1-w.bbox.y0}));
results.push({name:sources[i].name,page:p,width:page.width,height:page.height,pdfText:page.text,ocrText:raw?.data.text??null,ocrWords:words,pdfTokens:tokens(page.text),pdfTempoLines:page.text.filter(w=>/93|104|92|96|=|Saxophone|Alto/i.test(w.str))});console.log(sources[i].name,p);}}
if(worker)await worker.terminate();window.result={results};}catch(e){window.error=String(e.stack||e);}</script>`
const middleware=async(req,res,next)=>{
 try {if(req.url==='/metadata-probe'){res.setHeader('Content-Type','text/html');res.end(html);return}
 if(req.url==='/metadata-sources'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify(sources.map(s=>({name:s.name,filename:path.basename(s.file)}))));return}
 if(req.url.startsWith('/metadata-input/')){res.end(await fs.readFile(sources[Number(req.url.split('/').at(-1))].file));return}
 if(req.url.startsWith('/metadata-save/')&&req.method==='POST'){const name=path.basename(req.url);if(!/^[a-z]+-\d+\.png$/.test(name))throw Error('invalid output name');const chunks=[];for await(const chunk of req)chunks.push(chunk);await fs.writeFile(path.join(out,name),Buffer.concat(chunks));res.end('ok');return}
 next()}catch(e){res.statusCode=500;res.end(String(e))}
}
const server=await createServer({root:path.join(root,'web'),configFile:false,
 plugins:[{name:'local-metadata-probe',configureServer(server){server.middlewares.use(middleware)}}],
 server:{port:0,host:'127.0.0.1',fs:{allow:[root]}}})
await server.listen();const address=server.httpServer.address(),browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'})
try {const page=await browser.newPage();page.on('console',m=>console.log(m.text()));page.on('pageerror',e=>console.error(e));await page.goto('http://127.0.0.1:'+address.port+'/metadata-probe');await page.waitForFunction(()=>window.result||window.error,null,{timeout:600000});const answer=await page.evaluate(()=>({result:window.result,error:window.error}));if(answer.error)throw Error(answer.error);answer.result.sources=await Promise.all(sources.map(async s=>({...s,sha256:createHash('sha256').update(await fs.readFile(s.file)).digest('hex')})));answer.result.source_sha256=Object.fromEntries(await Promise.all(['input.js','annotate.js','ocr.js'].map(async f=>[f,createHash('sha256').update(await fs.readFile(path.join(root,'web/src',f))).digest('hex')])));await fs.writeFile(path.join(out,'evidence.json'),JSON.stringify(answer.result,null,2)+'\n');console.log('Saved',out)}finally{await browser.close();await server.close()}
