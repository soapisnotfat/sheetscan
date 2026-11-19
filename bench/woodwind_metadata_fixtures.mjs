// Original source-text/XML matrix. This does not run or score image recognition.
import { annotate, tokens } from '../web/src/annotate.js'
import { sourceInstrumentMetadata, tempoDirection, quarterTempo } from '../web/src/metadata.js'

const check = (ok, message) => { if (!ok) throw Error(message) }
const token = (str, x = 70, y = 80, h = 24) => ({ str, x, y, h, w: str.length * 10, source: 'authored-metadata-matrix' })
const layout = [[[40, 200, 640, 256, 0]]]
const note = (id, step, octave, duration = 24) => `<note id="${id}"><pitch><step>${step}</step><octave>${octave}</octave></pitch><duration>${duration}</duration><voice>1</voice><type>half</type></note>`

function score(row = {}) {
  const name = row.name ?? 'Voice', parts = row.parts ?? 1,
    transpose = row.explicitTranspose ? `<transpose><diatonic>${row.explicitTranspose[0]}</diatonic><chromatic>${row.explicitTranspose[1]}</chromatic></transpose>` : '',
    forPart = row.forPart ? '<for-part><part-transpose><diatonic>0</diatonic><chromatic>0</chromatic></part-transpose></for-part>' : '',
    definitions = Array.from({ length: parts }, (_, i) => `<score-part id="P${i + 1}"><part-name>${name}</part-name>${(row.instrumentNames ?? []).map((name, j) => `<score-instrument id="original-${j}"><instrument-name>${name}</instrument-name></score-instrument>`).join('')}</score-part>`).join(''),
    music = Array.from({ length: parts }, (_, i) => `<part id="P${i + 1}"><measure number="0" implicit="yes"><attributes><divisions>12</divisions><key><fifths>1</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef>${transpose}${forPart}</attributes>${note(`pickup-${i}-p0-180-225`, 'C', 5, 12)}</measure><measure number="1">${note(`body-${i}-p0-420-225`, 'D', 5)}${note(`body-${i}-p0-520-225`, 'E', 5)}</measure></part>`).join('')
  return new DOMParser().parseFromString(`<score-partwise version="4.0">${row.concertXml ? '<defaults><concert-score/></defaults>' : ''}<part-list>${definitions}</part-list>${music}</score-partwise>`, 'application/xml')
}

function evidence(row) {
  const pages = row.pages ?? [row.header ?? null]
  return pages.map((header, page) => {
    const items = row.headerTokens
      ? row.headerTokens.map((str, i) => token(str, 40 + i * 100, row.headerY ?? 80))
      : header ? [token(header, 40, row.headerY ?? 80)] : []
    if (row.extraHeader) items.push(token(row.extraHeader, 40, 120))
    if (row.partLabel) items.push(token(row.partLabel, -180, 228))
    return items
  })
}

const written = doc => [...doc.querySelectorAll('note,attributes > key,attributes > time,attributes > divisions,attributes > clef')].map(node => node.outerHTML).join('')
const serialize = doc => new XMLSerializer().serializeToString(doc)

export function runWoodwindMetadataMatrix(matrix) {
  const results = []
  for (const row of matrix.instrumentCases) {
    const doc = score(row), text = evidence(row), layouts = text.map(() => layout[0]),
      before = written(doc), prior = serialize(doc),
      result = sourceInstrumentMetadata(doc, text, layouts)
    check(result.status === row.expectedStatus, `${row.id}: ${JSON.stringify(result)}`)
    if (row.expectedReason) check(result.reason === row.expectedReason, `${row.id}: unexpected reason ${result.reason}`)
    check(written(doc) === before, `${row.id}: written pitch, duration, key, meter, or clef changed`)
    if (row.expectedStatus !== 'applied') check(serialize(doc) === prior, `${row.id}: rejected/preserved source changed XML`)
    if (row.expectedTranspose) {
      const transposes = [...doc.querySelectorAll('attributes > transpose')]
      check(transposes.length === 1, `${row.id}: expected exactly one transpose`)
      check(+transposes[0].querySelector('diatonic').textContent === row.expectedTranspose[0] && +transposes[0].querySelector('chromatic').textContent === row.expectedTranspose[1], `${row.id}: wrong written-to-sounding interval`)
      check(doc.querySelector('score-instrument > instrument-name')?.textContent === row.expectedInstrument, `${row.id}: wrong source instrument`)
      if (row.instrumentNames?.length === 1) check(doc.querySelector('score-instrument').id === 'original-0', `${row.id}: original instrument identity replaced`)
      // Export/reparse and repeated source annotation cannot double-transpose.
      const exported = serialize(doc), restored = new DOMParser().parseFromString(exported, 'application/xml')
      check(sourceInstrumentMetadata(restored, text, layouts).reason === 'explicit-transpose', `${row.id}: repeat did not preserve declaration`)
      check(serialize(restored) === exported, `${row.id}: export/reparse changed metadata`)
    }
    results.push({ id: row.id, status: result.status, reason: result.reason ?? null, transpose: row.expectedTranspose ?? null, musicxml: serialize(doc) })
  }
  for (const row of matrix.tempoCases) {
    const doc = score(), before = written(doc), direction = tempoDirection(doc, row)
    doc.querySelector('measure').append(direction)
    check(quarterTempo(row) === row.quarterBpm, `${row.unit}/${row.dotted}: wrong quarter BPM`)
    check(direction.querySelector('beat-unit').textContent === row.unit, `${row.unit}: printed beat unit changed`)
    check(!!direction.querySelector('beat-unit-dot') === row.dotted, `${row.unit}: dot changed`)
    check(+direction.querySelector('per-minute').textContent === row.bpm, `${row.unit}: printed BPM changed`)
    check(+direction.querySelector('sound').getAttribute('tempo') === row.quarterBpm, `${row.unit}: playback BPM changed`)
    check(written(doc) === before, `${row.unit}: tempo emission changed written music`)
    results.push({ id: `tempo-${row.unit}-${row.dotted}`, quarterBpm: row.quarterBpm })
  }
  // Exercise the actual annotation entrypoint and retain a genuine later change.
  const doc = score(), later = tempoDirection(doc, { unit: 'quarter', bpm: 112 })
  doc.querySelectorAll('measure')[1].prepend(later)
  const before = written(doc), laterXml = later.outerHTML,
    result = annotate(doc, [tokens([token('For Tenor Saxophone', 40, 80), token('h. = 61', 160, 170)])], { layout })
  check(result.instrument.status === 'applied', 'annotation entrypoint did not apply explicit tenor metadata')
  check(written(doc) === before, 'annotation entrypoint changed written music/pickup')
  check(doc.querySelectorAll('measure')[1].querySelector('direction').outerHTML === laterXml, 'later tempo change mutated')
  check(doc.querySelector('measure metronome beat-unit').textContent === 'half' && doc.querySelector('measure metronome beat-unit-dot'), 'annotation lost printed dotted-half unit')
  check(doc.querySelector('measure sound').getAttribute('tempo') === '183', 'annotation lost quarter-equivalent playback tempo')
  results.push({ id: 'annotation-entrypoint-pickup-and-later-tempo', quarterBpm: 183, laterQuarterBpm: 112 })
  return results
}
