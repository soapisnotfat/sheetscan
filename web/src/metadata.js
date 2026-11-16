// Source-only metadata preprocessing. All image/OCR work stays on this device.
// This module never reads reference pitches, target tempos or expected bar IDs.
import { readNumber } from './ocr.js'

const BEATS = { whole: 4, half: 2, quarter: 1, eighth: .5, '16th': .25, '32nd': .125, '64th': .0625 }
const UNIT_TEXT = { quarter: 'q', half: 'h', eighth: 'e' }

export function quarterTempo({ bpm, unit, dotted = false }) {
  return bpm > 0 && BEATS[unit] ? bpm * BEATS[unit] * (dotted ? 1.5 : 1) : null
}

/** Preserve the printed beat and dot; sound is exact quarter-note BPM. */
export function tempoDirection(doc, { bpm, unit, dotted = false, words }) {
  const el = (name, text) => Object.assign(doc.createElement(name), text == null ? {} : { textContent: String(text) })
  const direction = el('direction')
  direction.setAttribute('placement', 'above')
  if (words) direction.appendChild(el('direction-type')).append(el('words', words))
  const soundTempo = quarterTempo({ bpm, unit, dotted })
  if (soundTempo != null) {
    const mark = direction.appendChild(el('direction-type')).appendChild(el('metronome'))
    mark.append(el('beat-unit', unit), ...(dotted ? [el('beat-unit-dot')] : []), el('per-minute', bpm))
    const sound = direction.appendChild(el('sound'))
    sound.setAttribute('tempo', String(Number(soundTempo.toFixed(8))))
  }
  return direction
}

function componentImage(data, width, height, box) {
  const [left, top, right, bottom] = box.map(Math.round), w = right-left, h = bottom-top
  const ink = new Uint8Array(w*h), seen = new Uint8Array(w*h), components = []
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const at = ((top+y)*width+left+x)*4
    ink[y*w+x] = data[at+3] > 128 && data[at]+data[at+1]+data[at+2] < 480 ? 1 : 0
  }
  for (let start = 0; start < ink.length; start++) {
    if (!ink[start] || seen[start]) continue
    const todo = [start], pixels = []
    let x0 = w, y0 = h, x1 = 0, y1 = 0
    seen[start] = 1
    while (todo.length) {
      const i = todo.pop(), x = i%w, y = Math.floor(i/w)
      pixels.push(i); x0=Math.min(x0,x); y0=Math.min(y0,y); x1=Math.max(x1,x); y1=Math.max(y1,y)
      for (const [dx,dy] of [[-1,0],[1,0],[0,-1],[0,1]]) {
        const nx=x+dx, ny=y+dy, next=ny*w+nx
        if (nx>=0 && nx<w && ny>=0 && ny<h && ink[next] && !seen[next]) { seen[next]=1; todo.push(next) }
      }
    }
    components.push({ x:left+x0, y:top+y0, w:x1-x0+1, h:y1-y0+1, area:pixels.length })
  }
  return { ink, components, left, top, w, h }
}

function closedHoles(get, box) {
  const [left,top,right,bottom] = box.map(Math.round), w=right-left, h=bottom-top
  const seen=new Uint8Array(w*h), holes=[]
  for (let start=0;start<w*h;start++) {
    const sx=start%w,sy=Math.floor(start/w)
    if (seen[start] || get(left+sx,top+sy)) continue
    const todo=[start];seen[start]=1;let area=0,edge=false
    while(todo.length) {
      const i=todo.pop(),x=i%w,y=Math.floor(i/w);area++;edge ||= x===0||y===0||x===w-1||y===h-1
      for(const [dx,dy] of [[-1,0],[1,0],[0,-1],[0,1]]) {
        const nx=x+dx,ny=y+dy,next=ny*w+nx
        if(nx>=0&&nx<w&&ny>=0&&ny<h&&!seen[next]&&!get(left+nx,top+ny)){seen[next]=1;todo.push(next)}
      }
    }
    if(!edge)holes.push(area)
  }
  return holes
}

/** Geometry supports upright quarter/half/eighth metronome note glyphs only. */
function beatGlyph(component, image, unit) {
  const { x,y,w,h } = component
  if (w<.25*unit || w>2.3*unit || h<1.3*unit || h>3.7*unit) return null
  const get=(xx,yy)=>image.ink[(Math.round(yy)-image.top)*image.w+Math.round(xx)-image.left] ?? 0
  let stem=-1,best=0
  for(let xx=x;xx<x+w;xx++) {
    let run=0,longest=0
    for(let yy=y;yy<y+h;yy++){run=get(xx,yy)?run+1:0;longest=Math.max(longest,run)}
    if(longest>=best){best=longest;stem=xx}
  }
  if(best<.65*h || stem<x+.4*w) return null
  const headTop=y+Math.round(.6*h), headBottom=y+h,headRight=Math.min(x+w,stem+Math.max(1,Math.round(.12*unit)))
  let filled=0
  for(let yy=headTop;yy<headBottom;yy++)for(let xx=x;xx<headRight;xx++)filled+=get(xx,yy)
  const density=filled/((headRight-x)*(headBottom-headTop)), holes=closedHoles(get,[x-1,headTop-1,headRight+1,headBottom+1])
  const hollow=holes.some(a=>a>=Math.max(2,.025*unit*unit))
  let flagInk=0
  for(let yy=y;yy<y+.55*h;yy++)for(let xx=Math.round(stem+.18*unit);xx<x+w;xx++)flagInk+=get(xx,yy)
  const flagged=flagInk>Math.max(3,.04*unit*unit)
  if(!flagged && w/h>.6) return null
  if(hollow && flagged) return null
  if(!hollow && density<.3) return null
  return { unit:hollow?'half':flagged?'eighth':'quarter', headDensity:density, holeAreas:holes, flagInk,
    glyphBox:[x,y,x+w,y+h],stemX:stem }
}

const pagePixels = new WeakMap()
async function pixels(page) {
  if (!pagePixels.has(page)) pagePixels.set(page,(async()=>{
    const bitmap=await createImageBitmap(new Blob([page.png],{type:'image/png'})), canvas=document.createElement('canvas')
    canvas.width=bitmap.width;canvas.height=bitmap.height;const context=canvas.getContext('2d',{willReadFrequently:true})
    context.drawImage(bitmap,0,0);bitmap.close()
    return { data:context.getImageData(0,0,canvas.width,canvas.height).data,width:canvas.width,height:canvas.height }
  })())
  return pagePixels.get(page)
}

/** Read-only fallback for coordinate-free legacy XML, not score reconstruction. */
export async function imageStaffBoxes(page) {
  const {data,width,height}=await pixels(page),rows=[]
  for(let y=0;y<height;y++) {
    let run=0,start=0,best=0,left=0,right=0
    for(let x=0;x<width;x++) {
      const i=(y*width+x)*4,dark=data[i]+data[i+1]+data[i+2]<480
      if(dark){if(!run)start=x;run++;if(run>best){best=run;left=start;right=x+1}}else run=0
    }
    if(best<Math.max(80,.22*width))continue
    const previous=rows.at(-1)
    if(previous&&y-previous.bottom<=2){previous.bottom=y;previous.left=Math.min(previous.left,left);previous.right=Math.max(previous.right,right)}
    else rows.push({top:y,bottom:y,left,right})
  }
  const boxes=[]
  for(let i=0;i+4<rows.length;) {
    const five=rows.slice(i,i+5),ys=five.map(r=>(r.top+r.bottom)/2),gaps=ys.slice(1).map((y,j)=>y-ys[j]),unit=(ys[4]-ys[0])/4
    if(unit>=3&&unit<=45&&gaps.every(g=>Math.abs(g-unit)<.22*unit)) {
      boxes.push([Math.max(...five.map(r=>r.left)),Math.round(ys[0]),Math.min(...five.map(r=>r.right)),Math.round(ys[4]),boxes.length]);i+=5
    }else i++
  }
  return boxes
}

/** Source glyph + two equality strokes + right-hand number, all above one staff. */
export async function detectTempoRegions(page, staffs) {
  const image=await pixels(page), found=[]
  for(let staff=0;staff<staffs.length;staff++) {
    const [left,top,right,bottom]=staffs[staff],u=(bottom-top)/4
    if(u<3)continue
    const roi=[Math.max(0,Math.round(left-2*u)),Math.max(0,Math.round(top-7*u)),Math.min(image.width,Math.round(right)),Math.max(0,Math.round(top-.1*u))]
    if(roi[3]<=roi[1])continue
    const scene=componentImage(image.data,image.width,image.height,roi),comps=scene.components
    const bars=comps.filter(c=>c.w>=.5*u&&c.w<=2*u&&c.h>=1&&c.h<=.3*u&&c.w>=2.5*c.h)
    for(let a=0;a<bars.length;a++)for(let b=a+1;b<bars.length;b++) {
      let first=bars[a],second=bars[b];if(first.y>second.y)[first,second]=[second,first]
      if(Math.abs(first.x-second.x)>.18*u || Math.min(first.w,second.w)/Math.max(first.w,second.w)<.7 || second.y-first.y-first.h<.13*u || second.y-first.y>.95*u)continue
      const eq=[Math.min(first.x,second.x),first.y,Math.max(first.x+first.w,second.x+second.w),second.y+second.h],cy=(eq[1]+eq[3])/2
      const candidates=comps.filter(c=>c.x+c.w<eq[0]-.03*u&&eq[0]-(c.x+c.w)<2.3*u&&Math.abs((c.y+c.h)-eq[3])<1.15*u)
        .map(c=>beatGlyph(c,scene,u)).filter(Boolean).sort((a,b)=>eq[0]-a.glyphBox[2]-(eq[0]-b.glyphBox[2]))
      if(!candidates.length)continue
      // Old-style figures can descend below the equality baseline (notably 7).
      // Keep the full connected digit while retaining the same local mark ROI.
      const beat=candidates[0],digits=comps.filter(c=>c.x>eq[2]&&c.x-eq[2]<5*u&&c.h>=.65*u&&c.h<=2.7*u&&c.w>=.12*u&&c.w<=4.2*u&&Math.abs(c.y+c.h-eq[3])<1.25*u).sort((a,b)=>a.x-b.x)
      if(!digits.length || digits[0].x-eq[2]>1.3*u)continue
      const grouped=[digits[0]]
      for(const digit of digits.slice(1)){const prev=grouped.at(-1);if(digit.x-prev.x-prev.w>1.1*u)break;grouped.push(digit)}
      const dots=comps.filter(c=>c.x>beat.stemX+.1*u&&c.x+c.w<eq[0]&&c.w>=.1*u&&c.w<=.45*u&&c.h>=.1*u&&c.h<=.45*u&&c.w/c.h>.6&&c.w/c.h<1.6&&Math.abs(c.y+c.h/2-(beat.glyphBox[3]-.15*(beat.glyphBox[3]-beat.glyphBox[1])))<.5*u)
      if(dots.length>1)continue
      const pad=Math.max(2,Math.round(.2*u)),x0=grouped[0].x,y0=Math.min(...grouped.map(c=>c.y)),x1=Math.max(...grouped.map(c=>c.x+c.w)),y1=Math.max(...grouped.map(c=>c.y+c.h))
      if(x1-x0>6*u)continue
      const region={staff,...beat,dotted:dots.length===1,equalityBox:eq,numberBox:[Math.max(0,x0-pad),Math.max(0,y0-pad),Math.min(image.width,x1+pad),Math.min(image.height,y1+pad)],
        x:beat.glyphBox[0],y:y1,h:y1-y0,w:x1-beat.glyphBox[0],source:'image-note-equality-number'}
      if(!found.some(r=>r.staff===staff&&Math.abs(r.x-region.x)<u))found.push(region)
    }
  }
  return found
}

/** Optional async stage; annotate itself remains synchronous and deterministic. */
export async function prepareMetadata(pages, rawText, doc, { readTempoNumber=readNumber } = {}) {
  const layout=JSON.parse(doc.querySelector('miscellaneous-field[name="staff-layout"]')?.textContent??'[]')
  const text=pages.map((page,i)=>(rawText?.[i]??page.text??[]).map(t=>({...t,requiresUnitGlyph:true}))),audit=[]
  for(let page=0;page<pages.length;page++) {
    if(!layout[page]?.length){layout[page]=await imageStaffBoxes(pages[page]);audit.push({page,kind:'staff-evidence',source:'horizontal-five-line-image',count:layout[page].length})}
    if(!layout[page]?.length){audit.push({page,kind:'tempo-image',status:'unknown',reason:'no-staff-layout'});continue}
    const regions=await detectTempoRegions(pages[page],layout[page])
    audit.push({page,kind:'tempo-image-scan',regionCount:regions.length})
    for(const region of regions) {
      // Evidence belongs to this mark, not every mark on the page. A readable
      // PDF beat elsewhere must not suppress a different image-only metronome.
      const sourceBeat=(pages[page].text??[]).find(t=>/[\uECA2-\uECAE\uE1D3\uE1D5\uE1D7\uF071\uF068\uF065]/u.test(t.str)
        &&Math.abs(t.x-region.x)<region.h&&Math.abs(t.y-region.y)<Math.max(t.h,region.h))
      const sourceNumber=sourceBeat&&text[page].some(t=>/=\s*(?:c(?:irc)?a\.?\s*)?\d{2,3}/.test(t.str)
        &&t.x<=region.numberBox[2]&&t.x+t.w>=region.equalityBox[0]&&Math.abs(t.y-region.y)<Math.max(t.h,region.h))
      if(sourceNumber){audit.push({page,kind:'tempo-image',status:'text-covered',region});continue}
      const conflict=text[page].some(t=>{
        const match=/^\s*([^\s=]+)\s*=\s*\d{2,3}\s*$/.exec(t.str)
        return match&&/[\p{L}\p{N}]/u.test(match[1])&&!/^[qhe]\.?$/.test(match[1])&&t.x<=region.equalityBox[0]&&t.x+t.w>=region.numberBox[0]&&Math.abs(t.y-region.y)<Math.max(t.h,region.h)
      })
      if(conflict){audit.push({page,kind:'tempo-image',status:'unknown',reason:'text-unit-conflict',region});continue}
      const reading=await readTempoNumber(pages[page],region.numberBox)
      const accepted=reading?.value>=20&&reading.value<=400&&reading.agreement>=2
      audit.push({page,kind:'tempo-image',status:accepted?'read':'unknown',region,reading:reading??null})
      if(!accepted)continue
      // Replace an OCR view of the same digits, preserving the original words
      // in the caller's evidence. Otherwise a wide neighboring OCR box can
      // merge "q=92" and the original "92" into the invalid "q=9292".
      const [a,b,c,d]=region.numberBox
      text[page]=text[page].filter(t=>!/^\s*(?:\d{1,3}|[^\s=]{0,3}\s*=\s*\d{2,3})\s*$/.test(t.str)
        || Math.min(t.x+t.w,c)-Math.max(t.x,a)<.5*t.w || Math.min(t.y,d)-Math.max(t.y-t.h,b)<.4*t.h)
      text[page].push({str:`${UNIT_TEXT[region.unit]}${region.dotted?'.':''}=${reading.value}`,x:region.x,y:region.y,h:region.h,w:region.w,
        source:'verified-image-tempo',requiresUnitGlyph:true,tempoEvidence:{...region,reading}})
    }
  }
  return {text,layout,sourceAudit:audit}
}

/** Explicit source instrument evidence, unique part only; written music untouched. */
export function sourceInstrumentMetadata(doc, text, layout) {
  const parts=[...doc.querySelectorAll('score-partwise > part')],scoreParts=[...doc.querySelectorAll('part-list > score-part')]
  if(doc.querySelector('score-partwise > defaults > concert-score'))return {status:'preserved',reason:'explicit-concert-score-xml'}
  const all=text.flat(),joined=all.map(t=>t.str).join(' ')
  if(/\bconcert\s+(?:score|pitch)\b|\bin\s+concert\s+pitch\b|实音谱/i.test(joined))return {status:'unknown',reason:'explicit-concert-score'}
  if(/\bfor\s+(?:the\s+)?alto\s+saxophone\s+(?:and|with|&)\s+(?:piano|organ|orchestra|band)\b/i.test(joined))return {status:'unknown',reason:'multiple-source-instruments'}
  const evidence=[]
  text.forEach((items,page)=>{
    const first=layout[page]?.[0]
    if(!first)return
    const header=items.filter(t=>t.y<first[1]&&t.y>0).sort((a,b)=>a.y-b.y||a.x-b.x)
    const lines=[]
    for(const t of header){const line=lines.find(l=>Math.abs(l[0].y-t.y)<.55*Math.max(l[0].h,t.h));if(line)line.push(t);else lines.push([t])}
    for(const line of lines){line.sort((a,b)=>a.x-b.x);if(/\bfor\s+(?:the\s+)?alto\s+saxophone\b/i.test(line.map(t=>t.str).join(' ')))evidence.push({page,kind:'for-alto-header',tokens:line})}
    const label=items.find(t=>/^alto\s+saxophone$/i.test(t.str.trim())&&t.x+t.w<first[0]+.5*(first[3]-first[1])&&Math.abs(t.y-(first[1]+first[3])/2)<first[3]-first[1])
    if(label)evidence.push({page,kind:'explicit-part-label',tokens:[label]})
  })
  if(!evidence.length)return {status:'unknown',reason:'no-explicit-alto-source'}
  if(parts.length!==1||scoreParts.length!==1)return {status:'unknown',reason:'no-unique-part',evidence}
  const part=parts[0],definition=scoreParts[0]
  if(part.querySelector('attributes > for-part'))return {status:'preserved',reason:'explicit-for-part',evidence}
  if(part.querySelector('transpose'))return {status:'preserved',reason:'explicit-transpose',evidence}
  const instruments=[...definition.querySelectorAll(':scope > score-instrument')]
  if(instruments.length>1)return {status:'unknown',reason:'no-unique-instrument-record',evidence}
  const names=[...definition.querySelectorAll('part-name,instrument-name')].map(x=>x.textContent.trim()).filter(Boolean)
  if(names.some(name=>!/^alto\s+sax(?:ophone)?$/i.test(name)&&!/^(?:voice|music|part(?:\s*\d+)?)$/i.test(name)))return {status:'unknown',reason:'conflicting-instrument-name',evidence}
  const measure=part.querySelector(':scope > measure')
  if(!measure)return {status:'unknown',reason:'no-measure',evidence}
  let attributes=measure.querySelector(':scope > attributes')
  if(!attributes){attributes=doc.createElement('attributes');measure.insertBefore(attributes,measure.firstChild)}
  const transpose=doc.createElement('transpose')
  for(const [tag,value] of [['diatonic','-5'],['chromatic','-9']]){const el=doc.createElement(tag);el.textContent=value;transpose.append(el)}
  attributes.insertBefore(transpose,[...attributes.children].find(c=>['for-part','directive','measure-style'].includes(c.tagName))??null)
  if(instruments.length===1) {
    let name=instruments[0].querySelector(':scope > instrument-name')
    if(!name){name=doc.createElement('instrument-name');instruments[0].insertBefore(name,instruments[0].firstChild)}
    if(!name.textContent.trim()||/^(?:voice|music|part(?:\s*\d+)?)$/i.test(name.textContent.trim()))name.textContent='Alto Saxophone'
  } else {
    const instrument=doc.createElement('score-instrument');instrument.setAttribute('id',part.getAttribute('id')+'-source-alto')
    const name=doc.createElement('instrument-name');name.textContent='Alto Saxophone';instrument.append(name)
    definition.insertBefore(instrument,[...definition.children].find(c=>['midi-device','midi-instrument'].includes(c.tagName))??null)
  }
  return {status:'applied',part:part.getAttribute('id'),diatonic:-5,chromatic:-9,
    derivation:'standard-alto-instrument-convention',evidenceType:evidence[0].kind,writtenMusicChanged:false,evidence}
}
