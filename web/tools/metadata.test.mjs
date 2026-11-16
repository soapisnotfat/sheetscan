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
