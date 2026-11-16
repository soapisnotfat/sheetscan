import assert from 'node:assert/strict'
import test from 'node:test'
import { tokens, readTempos } from '../src/annotate.js'
import { quarterTempo } from '../src/metadata.js'

test('separate Unicode beat after a tempo word retains its beat unit',()=>{
  const items=[{str:'Allegro',x:0,y:100,h:20,w:70},{str:'♩',x:72,y:100,h:20,w:12},{str:'=',x:86,y:100,h:20,w:12},{str:'104',x:100,y:100,h:20,w:30}]
  const [tempo]=readTempos(tokens(items))
  assert.equal(tempo.unit,'quarter');assert.equal(tempo.bpm,104)
})
test('an OCR letter or bare equality never establishes the beat unit',()=>{
  for(const str of ['d=104','J=96','=88'])assert.equal(readTempos([{str,x:0,y:100,h:20,w:100}])[0].unit,null)
})
test('source word records remain unchanged by normalization',()=>{
  const items=[{str:'\uECA3',x:10,y:100,h:40,w:12,fontName:'source-font',raw:{str:'\uECA3'}},{str:'=61',x:26,y:100,h:20,w:40}]
  const before=JSON.stringify(items);tokens(items);assert.equal(JSON.stringify(items),before)
})
test('quarter BPM preserves dotted fractional eighth and half',()=>{
  assert.equal(quarterTempo({bpm:61,unit:'eighth',dotted:true}),45.75)
  assert.equal(quarterTempo({bpm:61,unit:'half',dotted:true}),183)
  assert.equal(quarterTempo({bpm:61,unit:null}),null)
})
test('a separated source augmentation dot keeps its preceding metronome glyph',()=>{
  const raw=[{str:'\uECA5',x:100,y:150,h:56,w:24},{str:'\uECB7',x:138,y:150,h:56,w:9},{str:'= 66',x:155,y:150,h:32,w:58}]
  const before=JSON.stringify(raw),[tempo]=readTempos(tokens(raw))
  assert.equal(tempo.unit,'quarter');assert.equal(tempo.dotted,true);assert.equal(tempo.bpm,66)
  assert.equal(JSON.stringify(raw),before)
})
test('a source note on another baseline cannot supply a missing tempo unit',()=>{
  const raw=[{str:'\uECA5',x:100,y:90,h:40,w:15},{str:'= 66',x:130,y:150,h:20,w:50}]
  assert.equal(readTempos(tokens(raw))[0].unit,null)
})
test('unmapped source font glyph zero cannot establish a beat unit',()=>{
  const raw=[{str:'\u0000',x:100,y:150,h:56,w:17},{str:'= 66',x:125,y:150,h:32,w:58}]
  assert.equal(readTempos(tokens(raw))[0].unit,null)
})
