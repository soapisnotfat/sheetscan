// SPDX-License-Identifier: CC0-1.0
// Original geometric notation fixtures. No existing score, image or GT is used.
import {annotate,tokens} from '../web/src/annotate.js'
import {prepareMetadata,quarterTempo} from '../web/src/metadata.js'
const check=(ok,m)=>{if(!ok)throw Error(m)}
const text=(str,x,y=176,w=55,h=25)=>({str,x,y,w,h,source:'fixture-pdf-text'})
const glyphs={whole:'\uECA2',half:'\uECA3',quarter:'\uECA5',eighth:'\uECA7','16th':'\uECA9','32nd':'\uECAB','64th':'\uECAD'}
const layout=[[[30,210,650,266,0]]]
function score(){return new DOMParser().parseFromString('<score-partwise><part-list><score-part id="P1"><part-name>Voice</part-name></score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>4</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time></attributes><note id="n1-p0-105-230"><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note></measure><measure number="2"><note id="n2-p0-420-230"><pitch><step>D</step><octave>4</octave></pitch><duration>16</duration><type>whole</type></note></measure></part></score-partwise>','application/xml')}
function mark(c,{x=100,unit='quarter',dotted=false,bpm=87,font='Georgia',negative=null,letter='d',variant=0,dotOffset=25,eqOffset=35,numOffset=68}){
 c.fillStyle='#111';c.strokeStyle='#111';c.lineWidth=1.8
 if(!negative||negative==='note-only'){
  c.beginPath();c.ellipse(x+5,178,variant?6.5:7.5,variant?4.5:3.8,-.32,0,2*Math.PI)
  if(['whole','half'].includes(unit))c.stroke();else c.fill()
  if(unit!=='whole'){
   c.fillRect(x+10,140,2,38)
   const flags={eighth:1,'16th':2,'32nd':3,'64th':4}[unit]??0
   for(let i=0;i<flags;i++){const y=140+i*7;c.beginPath();c.moveTo(x+12,y);c.bezierCurveTo(x+14,y+8,x+31,y+8,x+20,y+25);c.bezierCurveTo(x+27,y+11,x+14,y+14,x+12,y+9);c.fill()}
  }
  if(dotted){c.beginPath();c.arc(x+dotOffset,178,2,0,2*Math.PI);c.fill()}
 }
 if(negative==='letter'){c.font='31px '+font;c.fillText(letter,x,183)}
 if(negative!=='note-only'&&negative!=='digits-only'){c.fillRect(x+eqOffset,164,18,2.5);c.fillRect(x+eqOffset,172,18,2.5)}
 if(negative!=='note-only'){c.font='bold 27px '+font;c.fillText(String(bpm),x+numOffset,183)}
}
async function graphic(marks,scale=1){
 const canvas=document.createElement('canvas');canvas.width=680*scale;canvas.height=310*scale;const c=canvas.getContext('2d');c.scale(scale,scale);c.fillStyle='#fff';c.fillRect(0,0,680,310)
 c.strokeStyle='#333';c.lineWidth=.8;for(let y=210;y<=266;y+=14){c.beginPath();c.moveTo(30,y);c.lineTo(650,y);c.stroke()}
 for(const m of marks)mark(c,m)
 const blob=await new Promise(r=>canvas.toBlob(r,'image/png'));return {png:await blob.arrayBuffer(),width:canvas.width,height:canvas.height,text:[]}
}
function scaled(items,scale){return items.map(t=>({...t,x:t.x*scale,y:t.y*scale,w:t.w*scale,h:t.h*scale}))}
const tempos=d=>[...d.querySelectorAll('metronome')].map(m=>({measure:+m.closest('measure').getAttribute('number'),unit:m.querySelector('beat-unit').textContent,dotted:!!m.querySelector('beat-unit-dot'),bpm:+m.querySelector('per-minute').textContent,sound:+m.closest('direction').querySelector('sound').getAttribute('tempo')}))

export async function runTempoSourceFixtures(freeze){
 const cases=[]
 // Each raw note, augmentation dot and equality is a separate PDF token. The
 // gap exceeds the generic text-joining gap while remaining one notation group.
 for(const unit of Object.keys(glyphs))for(const dotted of [false,true]){
  const page=await graphic([{unit,dotted,bpm:73,dotOffset:32,eqOffset:dotted?47:35,numOffset:dotted?78:68}]),raw=[text(glyphs[unit],100,183,17,48),...(dotted?[text('\uECB7',130,183,5,48)]:[]),text('= 73',dotted?146:130,183)]
  cases.push({id:'separate-'+unit+(dotted?'-dot':''),page,raw,expected:[{measure:1,unit,dotted,bpm:73,sound:quarterTempo({unit,dotted,bpm:73})}]})
 }
 for(const unit of ['quarter','half','eighth'])for(const dotted of [false,true])for(const scale of [1,2]){
  const page=await graphic([{unit,dotted,font:scale===1?'Georgia':'Arial',variant:scale-1}],scale)
  cases.push({id:`pixels-${unit}-${dotted}-${scale}`,page,scale,raw:[],expected:[{measure:1,unit,dotted,bpm:87,sound:quarterTempo({unit,dotted,bpm:87})}]})
 }
 // Two marks on one line: a known PDF glyph must not disable image fallback
 // for the other mark. Its NUL text mimics an unusable source font mapping.
 const mixed=await graphic([{x:100,bpm:73},{x:415,unit:'half',dotted:true,bpm:109}])
 cases.push({id:'same-page-text-and-image',page:mixed,raw:[text('\uECA5',100,183,17,48),text('= 73',130,183),text('\u0000',415,183,17,48),text('= 109',450,183,65)],expected:[{measure:1,unit:'quarter',dotted:false,bpm:73,sound:73},{measure:2,unit:'half',dotted:true,bpm:109,sound:327}]})
 for(const negative of ['digits-only','equality-only','note-only','letter'])cases.push({id:'negative-'+negative,page:await graphic([{negative,bpm:109}]),raw:negative==='letter'?[text('d=109',100,183,130)]:[],expected:[]})
 cases.push({id:'negative-unknown-unit',page:await graphic([]),raw:[text('\u0000',100,183,17,48),text('= 73',130,183)],expected:[]})
 cases.push({id:'negative-separated-lines',page:await graphic([]),raw:[text('\uECA5',100,120,17,48),text('= 73',130,183)],expected:[]})
 for(const letter of ['q','h','e','w','n16'])cases.push({id:'negative-plain-unit-letter-'+letter,page:await graphic([{negative:'letter',letter,bpm:109}]),raw:[text(letter+'=109',100,183,130)],expected:[]})
 cases.push({id:'mixed-inline-glyph-and-plain-letter',page:await graphic([]),raw:[text('\uECA5 =73   e=109',100,183,350,48)],expected:[{measure:1,unit:'quarter',dotted:false,bpm:73,sound:73}]})
 // Freeze every expected value and actual raster byte hash before recognition.
 const frozen=await Promise.all(cases.map(async f=>({id:f.id,expected:f.expected,raw:f.raw,width:f.page.width,height:f.page.height,pngSHA256:Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',f.page.png)),b=>b.toString(16).padStart(2,'0')).join('')})))
 await freeze(frozen,cases.map(({id,page})=>({id,page})))
 const results=[]
 for(const f of cases){
  const doc=score(),scale=f.scale??1
  if(scale!==1)doc.querySelectorAll('note').forEach(n=>n.id=n.id.replace(/-(\d+)-(\d+)$/,(_,x,y)=>`-${+x*scale}-${+y*scale}`))
  const field=doc.createElement('miscellaneous-field');field.setAttribute('name','staff-layout');field.textContent=JSON.stringify(layout.map(ss=>ss.map(s=>s.map((n,i)=>i<4?n*scale:n))))
  const id=doc.createElement('identification'),misc=id.appendChild(doc.createElement('miscellaneous'));misc.append(field);doc.documentElement.prepend(id)
  f.page.text=f.raw
  const before=[...doc.querySelectorAll('note,attributes')].map(e=>e.outerHTML).join(''),prepared=await prepareMetadata([f.page],[f.raw],doc)
  annotate(doc,prepared.text.map(tokens),prepared)
  const observed=tempos(doc),after=[...doc.querySelectorAll('note,attributes')].map(e=>e.outerHTML).join('')
  check(before===after,f.id+' changed written music');check(JSON.stringify(observed)===JSON.stringify(f.expected),f.id+' '+JSON.stringify({observed,expected:f.expected,audit:prepared.sourceAudit}))
  results.push({id:f.id,tempos:observed,audit:prepared.sourceAudit})
 }
 return {frozen,results}
}
