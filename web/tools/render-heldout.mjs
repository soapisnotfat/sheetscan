// Independent corpus renderer; source truth and profiles are frozen before inference.
//   PLAYWRIGHT_CHANNEL=chrome node tools/render-heldout.mjs ../dev-samples/independent-eval/frozen-manifest.json
import {readFile, writeFile, mkdir} from 'node:fs/promises'
import {resolve,dirname,join} from 'node:path'
import {createHash} from 'node:crypto'
import createVerovioModule from 'verovio/wasm'
import {VerovioToolkit} from 'verovio/esm'
import {chromium} from 'playwright'
const manifestPath=resolve(process.argv[2]),root=dirname(manifestPath),manifest=JSON.parse(await readFile(manifestPath,'utf8'))
const filter=process.argv.find(arg=>arg.startsWith('--split='))?.split('=')[1]
const auditOnly=process.argv.includes('--audit-existing')
const tk=new VerovioToolkit(await createVerovioModule())
const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||undefined})
const results=[]
try {
 const page=await browser.newPage({viewport:{width:1653,height:2339}})
 for(const profile of manifest.cases.filter(row=>!filter||row.split===filter)){
  const out=join(root,profile.id);await mkdir(out,{recursive:true})
  tk.resetOptions();tk.setOptions({pageWidth:2100,pageHeight:2970,scale:45,breaks:profile.layout||'encoded',adjustPageHeight:false,font:profile.font,fontTextLiberation:profile.split==='holdout',xmlIdSeed:profile.seed})
  tk.loadData(await readFile(join(out,profile.truth),'utf8'))
  const svgs=[]
  for(let i=1;i<=tk.getPageCount();i++){
   const svg=auditOnly?await readFile(join(out,`p${i}.svg`),'utf8'):tk.renderToSVG(i);svgs.push(svg)
   if(!auditOnly)await writeFile(join(out,`p${i}.svg`),svg)
  }
  const geometry=[]
  for(let i=0;i<svgs.length;i++){
   await page.setContent(`<style>body{margin:0;background:white}.page>svg{display:block;width:210mm;height:297mm}</style><div class="page">${svgs[i]}</div>`)
   const bounds=await page.evaluate(()=>{const root=document.querySelector('.page>svg'),paper=root.getBoundingClientRect();const items=[...root.querySelectorAll('g.system')].map((s,i)=>{const b=s.getBoundingClientRect();return{system:i+1,left:b.left-paper.left,top:b.top-paper.top,right:b.right-paper.left,bottom:b.bottom-paper.top,inside:b.left>=paper.left-1&&b.top>=paper.top-1&&b.right<=paper.right+1&&b.bottom<=paper.bottom+1}});return{paper:{width:paper.width,height:paper.height},systems:items,measureGroups:root.querySelectorAll('g.measure').length,valid:items.length>0&&items.every(s=>s.inside)}})
   geometry.push({page:i+1,...bounds})
  }
  const valid=geometry.every(g=>g.valid)
  const result={id:profile.id,split:profile.split,font:profile.font,dpi:profile.dpi,layout:profile.layout||'encoded',pages:svgs.length,validGeometry:valid,geometry,rendererSha256:createHash('sha256').update(await readFile(new URL(import.meta.url))).digest('hex')}
  if(!auditOnly){
   if(!valid)throw Error(`${profile.id}: music systems exceed printable page bounds; reject raster`)
   await page.setContent(`<style>@page{size:A4;margin:0}body{margin:0;background:white}.page{break-after:page}.page:last-child{break-after:auto}.page>svg{display:block;width:210mm;height:297mm}</style>${svgs.map(svg=>`<div class="page">${svg}</div>`).join('')}`)
   const pdf=await page.pdf({preferCSSPageSize:true,printBackground:true});await writeFile(join(out,'score.pdf'),pdf)
   result.pdfSha256=createHash('sha256').update(pdf).digest('hex')
  }
  results.push(result);console.log(JSON.stringify({id:result.id,pages:result.pages,layout:result.layout,validGeometry:valid,systems:geometry.map(g=>g.systems.length)}))
 }
 await writeFile(join(root,`${auditOnly?'geometry-audit':'rendered'}-${filter||'all'}.json`),JSON.stringify(results,null,2)+'\n')
}finally{await browser.close()}
