import assert from 'node:assert/strict'
import test from 'node:test'
import { readTempos, tokens } from '../src/annotate.js'

const token = (str, x = 0) => ({ str, x, y: 100, w: str.length*10, h: 20 })

test('multiple tempo marks on a grouped text line remain separate', () => {
  const a = token('q=88', 10), b = token('q=104', 600)
  const readings = readTempos([a, b])
  assert.deepEqual(readings.map(t => [t.bpm, t.x]), [[88, 10], [104, 600]])
  assert.deepEqual(readings.map(t => t.tokens), [[a], [b]])
})

test('OCR fragments preserve the dotted beat unit and ignore trailing lyrics', () => {
  const parts = [token('q.', 10), token('=', 30), token('ca.', 50), token('60', 90), token('hello', 300)]
  const [reading] = readTempos(parts)
  assert.equal(reading.bpm, 60)
  assert.equal(reading.unit, 'quarter')
  assert.equal(reading.dotted, true)
  assert.equal(reading.tokens.length, 4)
})

test('a tempo word alone never invents exact BPM', () => {
  const [reading] = readTempos([token('Allegro ma non troppo')])
  assert.equal(reading.bpm, null)
  assert.equal(reading.words, 'Allegro ma non troppo')
})

test('PDF SMuFL quarter glyph is joined to its numeric marking', () => {
  const line = tokens([{ str: '\uECA5', x: 10, y: 100, h: 40, w: 12 }, token('= 88', 26)])
  assert.equal(readTempos(line)[0].bpm, 88)
  assert.equal(readTempos(line)[0].unit, 'quarter')
})

test('bar counts and unsupported four-digit values are not tempos', () => {
  assert.deepEqual(readTempos([token('11'), token('104')]), [])
  assert.deepEqual(readTempos([token('q=1040')]), [])
})

test('two marks inside one OCR text box have separate positions', () => {
  const readings = readTempos([token('q=88 q=104', 10)])
  assert.equal(readings.length, 2)
  assert.ok(readings[1].x > readings[0].x)
})
