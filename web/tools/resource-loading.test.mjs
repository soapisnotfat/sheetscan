import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..'),lock=JSON.parse(await readFile(resolve(root,'runtime-lock.json'),'utf8'))
const asset=lock.assets.find(asset=>asset.path==='ort/LICENSE'),cacheRoot=process.argv[2]
if(!cacheRoot)throw Error('Pass the verified runtime cache directory')
const bytes=await readFile(resolve(cacheRoot,asset.sha256)),url='https://static.example/sdk/runtime/ort/LICENSE'
let mode='slow',attempts=0,cacheMode='unavailable'
globalThis.caches={open:async()=>{if(cacheMode==='unavailable')throw new Error('Quota unavailable');return {match:async()=>cacheMode==='corrupt'?new Response('partial cache'):undefined,delete:async()=>true,put:async()=>{throw new Error('Quota exceeded')}}}}
globalThis.fetch=async(_url,{signal})=>{
 attempts++
 let timer,offset=0,streamController
 const stream=new ReadableStream({start(controller){streamController=controller
  const pump=()=>{if(signal.aborted)return;if(mode==='stalled'&&offset)return;const end=Math.min(bytes.length,offset+128);controller.enqueue(bytes.subarray(offset,end));offset=end;if(offset===bytes.length)controller.close();else timer=setTimeout(pump,8)}
  pump();signal.addEventListener('abort',()=>{clearTimeout(timer);controller.error(signal.reason)},{once:true})
 },cancel(){clearTimeout(timer)}})
 return new Response(stream,{headers:{'content-length':String(bytes.length)}})
}
const {createResourceClient}=await import('../src/resources.js')
const progress=[]
let client=createResourceClient('https://static.example/sdk/',{idleTimeoutMs:20,totalTimeoutMs:1000,onProgress:event=>progress.push(event)})
assert.deepEqual(new Uint8Array(await client.assetBytes(url)),new Uint8Array(bytes))
assert.equal(attempts,1);assert.ok(progress.filter(event=>event.done>0).length>4)
console.log('Sustained slow streaming survives several idle-timeout durations while bytes keep arriving')
mode='stalled';attempts=0
client=createResourceClient('https://static.example/sdk/',{idleTimeoutMs:15,totalTimeoutMs:200})
await assert.rejects(client.assetBytes(url),error=>error.code==='RESOURCE_IDLE_TIMEOUT'&&error.attempts===3&&error.resourceURL===url)
assert.equal(attempts,3)
console.log('Stalled streams fail with a precise resource after exactly three bounded attempts')
mode='slow';attempts=0
client=createResourceClient('https://static.example/sdk/',{idleTimeoutMs:100,totalTimeoutMs:15})
await assert.rejects(client.assetBytes(url),error=>error.code==='RESOURCE_TOTAL_TIMEOUT'&&error.attempts===3)
console.log('The separate total cap remains bounded for an excessively long download')
mode='slow';cacheMode='corrupt';attempts=0
client=createResourceClient('https://static.example/sdk/',{idleTimeoutMs:30,totalTimeoutMs:1000,onProgress:event=>progress.push(event)})
assert.deepEqual(new Uint8Array(await client.assetBytes(url)),new Uint8Array(bytes));assert.equal(attempts,1)
assert.ok(progress.some(event=>event.warning==='CACHE_CHECKSUM_MISMATCH'));assert.ok(progress.some(event=>event.warning==='CACHE_WRITE_FAILED'))
console.log('A corrupt cache is refetched, and cache write failure retains verified usable bytes')
const controller=new AbortController();attempts=0;mode='stalled'
client=createResourceClient('https://static.example/sdk/',{signal:controller.signal,idleTimeoutMs:200,totalTimeoutMs:1000})
const downloading=client.assetBytes(url);setTimeout(()=>controller.abort(new DOMException('Cancelled','AbortError')),5)
await assert.rejects(downloading,error=>error.name==='AbortError');assert.equal(attempts,1)
console.log('Manual cancellation interrupts a stalled download without starting retries')
