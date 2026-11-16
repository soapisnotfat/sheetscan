// Independent full-app evaluation. No XML injection, GT reads, score edits or repairs by this harness.
// Usage: node tools/evaluate-cohort.mjs URL JOBS.json OUTPUT_DIR [--nojspi]
import {chromium} from 'playwright'
import {readFile,writeFile,mkdir} from 'node:fs/promises'
import {resolve,join} from 'node:path'
import {createHash} from 'node:crypto'

const digest = data => createHash('sha256').update(data).digest('hex')
const [url,jobsFile,outArg] = process.argv.slice(2)
const out = resolve(outArg), jobs = JSON.parse(await readFile(jobsFile,'utf8'))
await mkdir(out,{recursive:true})
const browser = await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||undefined})
const context = await browser.newContext(), page = await context.newPage()
const result = {harnessSha256:digest(await readFile(new URL(import.meta.url))),jobsSha256:digest(await readFile(jobsFile)),
 sourceUrl:url,browser:browser.version(),policy:'actual file import, automatic OCR/text/rest-count pipeline, no manual edits or GT reads',status:'running',cases:[]}
let currentErrors = [], currentRequests = []
page.on('pageerror',error=>currentErrors.push(error.message))
page.on('requestfailed',request=>currentRequests.push({url:request.url(),failure:request.failure()?.errorText}))
try {
 await page.addInitScript(()=>{
  window.__capturedOMR=[]
  const OriginalWorker=window.Worker
  window.Worker=class extends OriginalWorker {
   constructor(...args){super(...args);this.addEventListener('message',event=>{
    const data=event.data
    if(data?.xml&&['result','rests-repaired'].includes(data.type))window.__capturedOMR.push({type:data.type,xml:data.xml,bridge:data.bridge})
   })}
  }
 })
 const target = new URL(url)
 if(process.argv.includes('--nojspi'))target.searchParams.set('nojspi','1')
 await page.goto(target.href)
 result.features=await page.evaluate(()=>({jspi:typeof WebAssembly.Suspending==='function',isolated:crossOriginIsolated,logicalCpus:navigator.hardwareConcurrency}))
 for(const job of jobs.cases){
  currentErrors=[];currentRequests=[]
  const dest=join(out,job.id);await mkdir(dest,{recursive:true})
  if(await page.evaluate(()=>document.body.dataset.view==='work'))await page.click('#again')
  else if(result.cases.length)await page.goto(target.href)
  const row={id:job.id,cohort:job.cohort,inputs:[],status:'running'}
  for(const file of job.files)row.inputs.push({file:resolve(file),sha256:digest(await readFile(resolve(file)))})
  const started=Date.now()
  await page.evaluate(()=>{window.__capturedOMR=[]})
  try{
   await page.setInputFiles('#files',[])
   await page.setInputFiles('#files',job.files.map(file=>resolve(file)))
   await page.waitForFunction(()=>document.body.dataset.view==='work'||(!document.getElementById('unsupported').hidden&&document.getElementById('unsupported').textContent),null,{timeout:300000})
   const state=await page.evaluate(()=>({view:document.body.dataset.view,error:document.getElementById('unsupported').textContent,xml:window.sheetscan.xml,bridge:window.sheetscan.bridge,recognitionSeconds:window.sheetscan.seconds}))
   if(state.view!=='work'||!state.xml)throw Error(state.error||'No MusicXML output')
   row.status='read';row.bridge=state.bridge;row.recognitionSeconds=state.recognitionSeconds;row.outputSha256=digest(state.xml)
   await writeFile(join(dest,'reading.musicxml'),state.xml)
   const captures=await page.evaluate(()=>window.__capturedOMR||[])
   row.workerCaptures=[]
   for(let i=0;i<captures.length;i++){
    const capture=captures[i],file=join(dest,`worker-${i}-${capture.type}.musicxml`)
    await writeFile(file,capture.xml);row.workerCaptures.push({type:capture.type,file,sha256:digest(capture.xml)})
   }
   await page.evaluate(async()=>Promise.all([...document.querySelectorAll('#scan .page > img')].map(img=>img.decode())))
   const rasters=await page.evaluate(async()=>Promise.all([...document.querySelectorAll('#scan .page > img')].map(async img=>({width:img.naturalWidth,height:img.naturalHeight,bytes:[...new Uint8Array(await(await fetch(img.src)).arrayBuffer())]}))))
   row.rasters=[]
   for(let i=0;i<rasters.length;i++){
    const raster=rasters[i],bytes=Buffer.from(raster.bytes),file=join(dest,`input-${i+1}.png`)
    await writeFile(file,bytes);row.rasters.push({file,page:i+1,width:raster.width,height:raster.height,sha256:digest(bytes)})
   }
  }catch(error){row.status='failed';row.error=error.message}
  row.milliseconds=Date.now()-started;row.pageErrors=[...currentErrors];row.failedRequests=[...currentRequests]
  await writeFile(join(dest,'browser-run.json'),JSON.stringify(row,null,2)+'\n')
  result.cases.push(row);await writeFile(join(out,'browser-results.json'),JSON.stringify(result,null,2)+'\n')
  console.log(JSON.stringify({id:row.id,cohort:row.cohort,status:row.status,milliseconds:row.milliseconds,pageErrors:row.pageErrors.length,error:row.error}))
 }
 result.status='complete';await writeFile(join(out,'browser-results.json'),JSON.stringify(result,null,2)+'\n')
}finally{await context.close();await browser.close()}
