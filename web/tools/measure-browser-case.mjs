// Isolated desktop browser measurement; RSS sums are sampled, not unique-memory accounting.
// CDP process discovery: https://chromedevtools.github.io/devtools-protocol/tot/SystemInfo/#method-getProcessInfo
// Usage: node tools/measure-browser-case.mjs URL INPUT.pdf OUTPUT_DIRECTORY
import {chromium} from 'playwright'
import {mkdir,writeFile,readFile} from 'node:fs/promises'
import {resolve,join} from 'node:path'
import {createHash} from 'node:crypto'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import os from 'node:os'

const run=promisify(execFile),url=process.argv[2],input=resolve(process.argv[3]),out=resolve(process.argv[4])
await mkdir(out,{recursive:true})
const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||undefined})
const browserSession=await browser.newBrowserCDPSession()
const context=await browser.newContext(),page=await context.newPage()
const errors=[];page.on('pageerror',error=>errors.push(error.message))
const result={scope:'single desktop cold/warm run; no mobile claim; parallel work not controlled',
 sourceUrl:url,inputSha256:createHash('sha256').update(await readFile(input)).digest('hex'),
 browser:browser.version(),status:'running',hardware:{platform:os.platform(),arch:os.arch(),cpu:os.cpus()[0]?.model,logicalCpus:os.cpus().length,physicalMemoryBytes:os.totalmem(),initialLoad:os.loadavg()},
 rssMethod:'1-second samples of sum RSS from CDP-listed processes of this isolated browser. Shared pages can be double-counted; observed peak is not a bound or WASM-only measure.',runs:[]}
try{
 await page.goto(url)
 result.features=await page.evaluate(()=>({jspi:typeof WebAssembly.Suspending==='function',isolated:crossOriginIsolated,logicalCpus:navigator.hardwareConcurrency,deviceMemoryGiB:navigator.deviceMemory}))
 for(const mode of ['cold','warm']){
  if(mode==='warm')await page.click('#again')
  const samples=[];let timer,busy=false
  async function sample(){
   if(busy)return;busy=true
   try{
    const {processInfo}=await browserSession.send('SystemInfo.getProcessInfo')
    const ids=processInfo.map(p=>p.id).filter(Number.isInteger)
    const {stdout}=await run('ps',['-o','rss=','-p',ids.join(',')])
    const rssKiB=stdout.trim().split(/\s+/).filter(Boolean).reduce((sum,n)=>sum+Number(n),0)
    const heap=await page.evaluate(()=>performance.memory?{usedJSHeapBytes:performance.memory.usedJSHeapSize,totalJSHeapBytes:performance.memory.totalJSHeapSize}:null)
    samples.push({time:Date.now(),rssKiB,processCount:ids.length,heap})
   }catch(error){samples.push({time:Date.now(),measurementError:error.message})}finally{busy=false}
  }
  await sample();timer=setInterval(()=>void sample(),1000)
  const started=Date.now()
  try{
   await page.setInputFiles('#files',[]);await page.setInputFiles('#files',input)
   await page.waitForFunction(()=>document.body.dataset.view==='work'||(!document.getElementById('unsupported').hidden&&document.getElementById('unsupported').textContent),null,{timeout:300000})
   const state=await page.evaluate(()=>({view:document.body.dataset.view,error:document.getElementById('unsupported').textContent,xml:window.sheetscan.xml,bridge:window.sheetscan.bridge,recognitionSeconds:window.sheetscan.seconds}))
   if(state.view!=='work'||!state.xml)throw Error(state.error||'Recognition did not complete')
   await writeFile(join(out,`${mode}.musicxml`),state.xml)
   await sample()
   const rss=samples.map(s=>s.rssKiB).filter(Number.isFinite)
   const row={mode,totalMilliseconds:Date.now()-started,recognitionSeconds:state.recognitionSeconds,bridge:state.bridge,peakSampledRssKiB:rss.length?Math.max(...rss):null,sampleCount:samples.length,samples,outputSha256:createHash('sha256').update(state.xml).digest('hex')};result.runs.push(row)
   await writeFile(join(out,'measurement.json'),JSON.stringify(result,null,2)+'\n')
   console.log(JSON.stringify({mode,totalMilliseconds:row.totalMilliseconds,recognitionSeconds:row.recognitionSeconds,peakSampledRssMiB:row.peakSampledRssKiB/1024,samples:row.sampleCount}))
  }finally{clearInterval(timer)}
 }
 result.status='complete';result.errors=errors;result.finalLoad=os.loadavg()
 await writeFile(join(out,'measurement.json'),JSON.stringify(result,null,2)+'\n')
}catch(error){
 result.status='failed';result.failure=error.message;result.errors=errors
 await writeFile(join(out,'measurement.json'),JSON.stringify(result,null,2)+'\n')
 throw error
}finally{await context.close();await browser.close()}
