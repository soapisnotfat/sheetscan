// Fresh, source-authored metadata fixtures. No existing score/GT is consulted.
import { annotate, tokens } from '../web/src/annotate.js'
import { prepareMetadata, detectTempoRegions, quarterTempo } from '../web/src/metadata.js'

const check=(ok,message)=>{if(!ok)throw Error(message)}
const token=(str,x=100,y=170,h=24)=>({str,x,y,h,w:str.length*12,source:'fixture-text'})
function score({parts=1,transpose=null,name='Voice'}={}) {
  const def=Array.from({length:parts},(_,i)=>`<score-part id="P${i+1}"><part-name>${name}</part-name></score-part>`).join('')
  const music=Array.from({length:parts},(_,i)=>`<part id="P${i+1}"><measure number="1"><attributes><divisions>12</divisions><key><fifths>1</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time>${transpose??''}</attributes><note id="n${i}-p0-180-${220+i*190}"><pitch><step>F</step><alter>1</alter><octave>4</octave></pitch><duration>48</duration><type>whole</type></note></measure><measure number="2"><note id="n${i+8}-p0-420-${220+i*190}"><pitch><step>C</step><octave>5</octave></pitch><duration>48</duration><type>whole</type></note></measure></part>`).join('')
  return new DOMParser().parseFromString(`<score-partwise version="4.0"><part-list>${def}</part-list>${music}</score-partwise>`,'application/xml')
}
const layout=[[[30,200,560,256,0],[30,390,560,446,1]]]
const notes=doc=>JSON.stringify([...doc.querySelectorAll('note > pitch,attributes > key')].map(e=>e.outerHTML))
function apply(doc,text,options={}) {const before=notes(doc),result=annotate(doc,[tokens(text)],{layout,...options});check(notes(doc)===before,'Written pitch/key mutated');return result}

async function graphic({unit='quarter',dotted=false,bpm=83,negative=null}={}) {
  const canvas=document.createElement('canvas');canvas.width=600;canvas.height=500;const c=canvas.getContext('2d');c.fillStyle='#fff';c.fillRect(0,0,600,500);c.fillStyle='#000';c.strokeStyle='#000'
  for(let y=200;y<=256;y+=14){c.beginPath();c.moveTo(30,y);c.lineTo(560,y);c.stroke()}
  if(!['digits-only','equality-only','letter'].includes(negative)) {
    c.lineWidth=2;c.beginPath();c.ellipse(105,177,7,4,-.3,0,2*Math.PI);unit==='half'?c.stroke():c.fill()
    c.lineWidth=2;c.beginPath();c.moveTo(111,176);c.lineTo(111,139);c.stroke()
    if(unit==='eighth'){c.beginPath();c.moveTo(111,139);c.bezierCurveTo(113,147,130,147,119,163);c.bezierCurveTo(126,150,114,153,111,148);c.fill()}
    if(dotted){c.beginPath();c.arc(124,177,2,0,2*Math.PI);c.fill()}
  }
  if(negative==='letter'){c.font='28px serif';c.fillText('d',99,182)}
  if(negative!=='digits-only'&&negative!=='note-only'){c.fillRect(134,164,20,3);c.fillRect(134,173,20,3)}
  if(negative!=='note-only'){c.font='bold 28px serif';c.fillText(String(bpm),170,182)}
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'))
  return {png:await blob.arrayBuffer(),width:600,height:500,text:[]}
}

export async function runMetadataFixtures() {
  const passed=[]
  let doc=score();apply(doc,[token('h. = 61')]);let m=doc.querySelector('metronome')
  check(m.querySelector('beat-unit').textContent==='half'&&m.querySelector('beat-unit-dot'),'Dotted half lost');check(doc.querySelector('sound').getAttribute('tempo')==='183','Dotted-half quarter BPM wrong');passed.push('dotted-half')
  doc=score();apply(doc,[token('e. = 61')]);check(doc.querySelector('sound').getAttribute('tempo')==='45.75','Fractional dotted-eighth BPM rounded');passed.push('dotted-eighth-exact')
  doc=score();apply(doc,[token('q=77',100),token('q=131',400)]);check([...doc.querySelectorAll('sound')].map(e=>e.getAttribute('tempo')).join(',')==='77,131','Same-line tempos merged');passed.push('same-line-multiple-tempos')
  doc=score();apply(doc,[token('93'),token('=104',400)]);check(!doc.querySelector('sound'),'Bare numbers became tempo');passed.push('numbers-and-unknown-unit-rejected')
  doc=score();apply(doc,[token('Allegro')]);check(!doc.querySelector('sound'),'Tempo word invented BPM');passed.push('no-default120')
  doc=score();doc.querySelectorAll('note').forEach(n=>n.removeAttribute('id'));apply(doc,[token('q=131',400)]);check(!doc.querySelector('sound'),'Coordinate-free middle tempo guessed first measure');passed.push('legacy-middle-without-coordinates-unknown')
  doc=score();apply(doc,[token('For Alto Saxophone',40,80)]);check(doc.querySelector('transpose > diatonic').textContent==='-5'&&doc.querySelector('transpose > chromatic').textContent==='-9','Source alto missing transpose');check(doc.querySelector('score-instrument > instrument-name').textContent==='Alto Saxophone','Score instrument missing');passed.push('explicit-alto-source')
  doc=score();const generic=doc.createElement('score-instrument');generic.setAttribute('id','retained-instrument-id');generic.appendChild(doc.createElement('instrument-name')).textContent='Voice';doc.querySelector('score-part').append(generic);apply(doc,[token('For Alto Saxophone',40,80)]);check(doc.querySelector('score-instrument').getAttribute('id')==='retained-instrument-id'&&doc.querySelector('instrument-name').textContent==='Alto Saxophone','Generic existing instrument was not updated in place');passed.push('existing-generic-instrument-name')
  for(const [kind,options,text] of [
    ['no-source',{},[]],['multipart',{parts:2},[token('For Alto Saxophone',40,80)]],
    ['concert',{},[token('For Alto Saxophone',40,80),token('Concert Score',40,110)]],
    ['multiple-source-instruments',{},[token('For Alto Saxophone and Piano',40,80)]],
    ['conflicting-part',{name:'Piano'},[token('For Alto Saxophone',40,80)]],
  ]) {doc=score(options);apply(doc,text);check(!doc.querySelector('transpose'),kind+' guessed transpose');passed.push(kind)}
  doc=score({transpose:'<transpose><diatonic>0</diatonic><chromatic>0</chromatic></transpose>'});apply(doc,[token('For Alto Saxophone',40,80)]);check(doc.querySelectorAll('transpose').length===1&&doc.querySelector('chromatic').textContent==='0','Explicit transpose overwritten');passed.push('explicit-transpose-preserved')
  doc=score();const defaults=doc.createElement('defaults');defaults.append(doc.createElement('concert-score'));doc.documentElement.insertBefore(defaults,doc.querySelector('part-list'));apply(doc,[token('For Alto Saxophone',40,80)]);check(!doc.querySelector('transpose')&&doc.querySelector('defaults > concert-score'),'XML concert-score was overridden');passed.push('xml-concert-score-preserved')
  doc=score();const forPart=doc.createElement('for-part'),partTranspose=forPart.appendChild(doc.createElement('part-transpose'));partTranspose.appendChild(doc.createElement('chromatic')).textContent='0';doc.querySelector('attributes').append(forPart);const preserved=forPart.outerHTML;apply(doc,[token('For Alto Saxophone',40,80)]);check(!doc.querySelector('attributes > transpose')&&doc.querySelector('for-part').outerHTML===preserved,'Existing for-part interpretation was overridden');passed.push('xml-for-part-preserved')
  doc=score({parts:2});apply(doc,[token('q=81',100,170),token('q=127',100,360)]);check(doc.querySelector('#P1 sound')?.getAttribute('tempo')==='81'&&doc.querySelector('#P2 sound')?.getAttribute('tempo')==='127','Multipart staff association failed');passed.push('multipart-tempo-staff-binding')
  for(const unit of ['quarter','half','eighth']) {
    const page=await graphic({unit,dotted:true,bpm:83}),regions=await detectTempoRegions(page,layout[0]);check(regions.length===1,unit+' source graphic not located '+JSON.stringify(regions));check(regions[0].unit===unit&&regions[0].dotted,unit+' beat or dot lost '+JSON.stringify(regions));
    doc=score();const prepared=await prepareMetadata([page],[[]],doc);annotate(doc,prepared.text.map(tokens),prepared);check(+doc.querySelector('sound')?.getAttribute('tempo')===quarterTempo({unit,dotted:true,bpm:83}),unit+' source graphic tempo failed');passed.push('source-graphic-'+unit)
  }
  for(const negative of ['digits-only','equality-only','note-only','letter']) {
    const page=await graphic({negative,bpm:104}),regions=await detectTempoRegions(page,layout[0]);check(regions.length===0,'Ordinary '+negative+' accepted '+JSON.stringify(regions));passed.push('graphic-negative-'+negative)
  }
  return passed
}
