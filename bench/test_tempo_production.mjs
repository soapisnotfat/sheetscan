// Production static app/SDK regression. Private inputs and expectations are CLI-only.
// node bench/test_tempo_production.mjs --app=DIST --sdk=DIST --cases=LOCAL_JSON --out=DIR [--baseline]
import fs from 'node:fs/promises'
import path from 'node:path'
import http from 'node:http'
import {fileURLToPath,pathToFileURL} from 'node:url'
import {createHash} from 'node:crypto'
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
const arg=n=>process.argv.find(a=>a.startsWith('--'+n+'='))?.slice(n.length+3)
const app=path.resolve(arg('app')),sdk=arg('sdk')&&path.resolve(arg('sdk')),out=path.resolve(arg('out'))
const cases=JSON.parse(await fs.readFile(path.resolve(arg('cases')),'utf8')),baseline=process.argv.includes('--baseline')
const {chromium}=await import(pathToFileURL(path.join(root,'web/node_modules/playwright/index.mjs')))
const hash=b=>createHash('sha256').update(b).digest('hex')
const mime={'.js':'text/javascript','.mjs':'text/javascript','.html':'text/html','.css':'text/css','.json':'application/json','.wasm':'application/wasm','.png':'image/png'}
const requests=[]
const server=http.createServer(async(req,res)=>{
 requests.push({method:req.method,url:req.url})
 res.setHeader('Cross-Origin-Opener-Policy','same-origin');res.setHeader('Cross-Origin-Embedder-Policy','require-corp')
 try{
  if(req.method!=='GET'){res.writeHead(405);res.end();return}
  const url=new URL(req.url,'http://localhost'),isSDK=url.pathname.startsWith('/sdk/'),dir=isSDK?sdk:app
  if(url.pathname==='/sdk/host'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>Retained host</title>');return}
  const rel=decodeURIComponent(url.pathname.replace(isSDK?/^\/sdk\//:/^\//,''))||'index.html',file=path.resolve(dir,rel)
  if(!file.startsWith(dir+path.sep))throw Error('outside dist')
  res.setHeader('Content-Type',mime[path.extname(file)]??'application/octet-stream');res.end(await fs.readFile(file))
 }catch{res.writeHead(404);res.end()}
})
await new Promise(r=>server.listen(0,'127.0.0.1',r))
const base='http://127.0.0.1:'+server.address().port,browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'})
const inspect=(page,xml)=>page.evaluate(xml=>{
 const d=new DOMParser().parseFromString(xml,'application/xml')
 // Score's app editor may normalize redundant printed <accidental> tags. Pitch
 // <alter> remains in this signature; display tags are reported separately.
 const core=[...d.querySelectorAll('score-partwise > part')].map(p=>({id:p.id,measures:[...p.querySelectorAll(':scope > measure')].map(m=>({number:m.getAttribute('number'),implicit:m.getAttribute('implicit'),events:[...m.children].filter(e=>['note','attributes','backup','forward','barline'].includes(e.tagName)).map(e=>{const copy=e.cloneNode(true);if(e.tagName==='note')copy.querySelectorAll(':scope > accidental').forEach(a=>a.remove());return copy.outerHTML})}))}))
 return {core,displayAccidentals:[...d.querySelectorAll('note > accidental')].map(e=>({id:e.parentNode.id,value:e.textContent})),tempos:[...d.querySelectorAll('part > measure > direction:has(metronome)')].map(e=>({part:e.closest('part').id,measure:e.closest('measure').getAttribute('number'),measureIndex:[...e.closest('part').querySelectorAll(':scope > measure')].indexOf(e.closest('measure'))+1,unit:e.querySelector('beat-unit').textContent,dotted:!!e.querySelector('beat-unit-dot'),bpm:+e.querySelector('per-minute').textContent,quarterSound:+e.querySelector('sound')?.getAttribute('tempo')})),metadata:JSON.parse(d.querySelector('miscellaneous-field[name="metadata-audit"]')?.textContent??'[]')}
},xml)
const receipt={browser:browser.version(),baseline,runs:[],requests}
try{
 for(let i=0;i<cases.length;i++){
  const c=cases[i],dir=path.join(out,String(i));await fs.mkdir(dir,{recursive:true})
  const input=c.sourcePDF??c.file,bytes=await fs.readFile(input),page=await browser.newPage(),network=[]
  page.on('request',r=>network.push({method:r.method(),url:r.url(),type:r.resourceType()}))
  await page.goto(base+'/?printed-tuplets=1');await page.setInputFiles('#files',input)
  await page.waitForFunction(()=>(document.body.dataset.view==='work'&&window.sheetscan?.xml)||document.getElementById('unsupported')?.textContent,null,{timeout:900000})
  const xml=await page.evaluate(()=>window.sheetscan.xml);if(!xml)throw Error(await page.locator('#unsupported').textContent())
  await fs.writeFile(path.join(dir,'app.musicxml'),xml)
  const observed=await inspect(page,xml),run={case:c.case??c.name,inputSHA256:hash(bytes),appSHA256:hash(xml),app:observed,network}
  if(!baseline){
   const old=await fs.readFile(path.join(arg('base-results'),String(i),'app.musicxml'),'utf8'),before=await inspect(page,old)
   run.coreUnchanged=JSON.stringify(before.core)===JSON.stringify(observed.core);if(!run.coreUnchanged)throw Error('Written core changed: '+i)
  }
  run.coreSHA256=hash(JSON.stringify(observed.core));delete observed.core
  await page.close()
  if(sdk&&!baseline){
   const host=await browser.newPage();host.on('request',r=>network.push({method:r.method(),url:r.url(),type:r.resourceType()}));await host.goto(base+'/sdk/host')
   const result=await host.evaluate(async({bytes,name})=>{
    const {createScoreConverter}=await import('/sdk/sheetscan.js'),file=new File([Uint8Array.from(atob(bytes),c=>c.charCodeAt(0))],name,{type:'application/pdf'})
    const converter=createScoreConverter(),before=location.href,sw=(await navigator.serviceWorker.getRegistrations()).length;window.hostProject={retained:7}
    let cancelled=false
    try{await converter.convert([file],{onProgress:p=>{if(p.phase==='recognizing')converter.cancel()}})}catch(e){cancelled=e.name==='AbortError'}
    if(!cancelled)throw Error('Cancellation failed')
    const phases=[];try{
     const r=await converter.convert([file],{onProgress:p=>{if(phases.at(-1)!==p.phase)phases.push(p.phase)}})
     return {xml:r.musicxml,audit:r.audit,bridge:r.bridge,phases,cancelledAndRetried:cancelled,hostUnchanged:before===location.href&&window.hostProject.retained===7,serviceWorkersAdded:(await navigator.serviceWorker.getRegistrations()).length-sw}
    }finally{converter.close()}
   },{bytes:bytes.toString('base64'),name:path.basename(input)})
   await fs.writeFile(path.join(dir,'sdk.musicxml'),result.xml);const sdkObserved=await inspect(host,result.xml)
   if(hash(JSON.stringify(sdkObserved.core))!==run.coreSHA256)throw Error('SDK changed written core: '+i)
   delete sdkObserved.core;run.sdk={...result,xml:undefined,...sdkObserved};run.sdkSHA256=hash(result.xml)
   run.displayAccidentalsMatchApp=JSON.stringify(run.app.displayAccidentals)===JSON.stringify(run.sdk.displayAccidentals)
   if(!result.hostUnchanged||result.serviceWorkersAdded)throw Error('SDK host changed')
   if(JSON.stringify(run.app.tempos)!==JSON.stringify(run.sdk.tempos))throw Error('App/SDK tempo mismatch')
   await host.close()
  }
  if(!baseline&&c.expectedPrintedTempos){
   const expected=c.expectedPrintedTempos.map(t=>({measureIndex:t.measureIndex,unit:t.unit,dotted:t.dotted,bpm:+t.bpm,quarterSound:+t.quarterSound}))
   const actual=run.app.tempos.map(({measureIndex,unit,dotted,bpm,quarterSound})=>({measureIndex,unit,dotted,bpm,quarterSound}))
   run.expectedMatches=JSON.stringify(expected)===JSON.stringify(actual)
  }
  receipt.runs.push(run);await fs.writeFile(path.join(out,'production.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify({case:run.case,core:run.coreSHA256,tempos:run.app.tempos,expected:run.expectedMatches}))
  if(run.expectedMatches===false&&!process.argv.includes('--allow-unobservable'))throw Error('Source tempo expectation failed: '+i)
 }
 if(requests.some(r=>r.method!=='GET'))throw Error('Local request was not static GET')
 receipt.staticGETOnly=true;receipt.appBuild=JSON.parse(await fs.readFile(path.join(app,'public-build.json'),'utf8'))
 if(sdk)receipt.sdkBuild=JSON.parse(await fs.readFile(path.join(sdk,'public-build.json'),'utf8'))
 await fs.writeFile(path.join(out,'production.json'),JSON.stringify(receipt,null,2)+'\n')
}finally{await browser.close();await new Promise(r=>server.close(r))}
