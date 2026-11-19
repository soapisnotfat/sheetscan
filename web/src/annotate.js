// Puts the text found on the pages into the score: title, composer, tempo, lyrics, chord symbols.
// Text is a list of {str, x, y, h, w} per page (baseline start, font height, width, in
// page-image pixels) from the PDF's text layer or from OCR. Staff positions come from
// the recogniser (the "staff-layout" field), note positions from the note ids.

import { tempoDirection, quarterTempo, sourceInstrumentMetadata } from './metadata.js'

// A root, a quality built from the usual pieces only (so words like "Der" don't match), a bass.
const CHORD = /^([A-G])([#b♯♭]?)((?:maj|min|dim|aug|sus|add|omit|no|m|M|\d|[#b♯♭+°ø△()\-,])*)(?:\/([A-G])([#b♯♭]?))?$/
const KINDS = {
  '': 'major', m: 'minor', min: 'minor', '-': 'minor', 7: 'dominant', maj7: 'major-seventh', M7: 'major-seventh',
  m7: 'minor-seventh', min7: 'minor-seventh', dim: 'diminished', '°': 'diminished', dim7: 'diminished-seventh',
  aug: 'augmented', '+': 'augmented', sus: 'suspended-fourth', sus4: 'suspended-fourth', sus2: 'suspended-second',
  6: 'major-sixth', m6: 'minor-sixth', 9: 'dominant-ninth', m9: 'minor-ninth', maj9: 'major-ninth',
  m7b5: 'half-diminished', 'ø': 'half-diminished', 5: 'power',
}
const ALTER = { '#': 1, '♯': 1, b: -1, '♭': -1 }

// Music fonts keep their glyphs in the private-use area. A few matter inside text: the
// sharp and flat of chord symbols and the note of a metronome mark (Finale's Maestro
// layout first, then SMuFL). They survive only when they join real text.
const GLYPHS = {
  '\uF023': '#', '\uF062': 'b', '\uF071': 'q', '\uF068': 'h', '\uF065': 'e', '\uF06B': '.',
  '\uE1D5': 'q', '\uECA5': 'q', '\uECA6': 'q', '\uE1D3': 'h', '\uECA3': 'h', '\uECA4': 'h', '\uE1D7': 'e', '\uECA7': 'e', '\uECA8': 'e', '\uE1E7': '.', '\uECB7': '.',
  '\uECA2': 'w', '\uECA9': 'n16', '\uECAA': 'n16', '\uECAB': 'n32', '\uECAC': 'n32', '\uECAD': 'n64', '\uECAE': 'n64',
  '♩': 'q', '𝅘𝅥': 'q', '𝅗𝅥': 'h', '♪': 'e', '𝅘𝅥𝅮': 'e', '𝅝': 'w', '𝅘𝅥𝅯': 'n16', '𝅘𝅥𝅰': 'n32', '𝅘𝅥𝅱': 'n64',
}
const UNITS = { q: 'quarter', h: 'half', e: 'eighth', w: 'whole', n16: '16th', n32: '32nd', n64: '64th' }
// "q = 156" (the note glyph mapped above), "(q. = ca. 60)", and what OCR makes of the
// note: "J=156", "d = 156". Their beat unit stays unknown until source pixels
// establish a metronome glyph; ordinary equations must not become quarter BPM.
const METRONOME = /(?:\b(q|h|e|w|n16|n32|n64)\s*(\.?))?\s*=\s*(?:c(?:irc)?a\.?\s*)?(\d{2,3})(?!\d)/
const TEMPO_WORDS = ['grave', 'largo', 'larghetto', 'lento', 'adagio', 'andante', 'andantino', 'moderato',
  'allegretto', 'allegro', 'vivace', 'presto', 'prestissimo']
const TEMPO_WORD = new RegExp(`\\b(${TEMPO_WORDS.join('|')})\\b`, 'i')

/** Every tempo on a line, keeping the source tokens for each mark separate.
 * A word such as Allegro does not specify an exact numeric BPM.
 */
export function readTempos(line) {
  let text = ''
  const spans = line.map(token => {
    if (text) text += ' '
    const start = text.length
    text += token.str
    return { token, start, end: text.length }
  })
  const found = []
  for (const match of text.matchAll(new RegExp(METRONOME.source, 'g'))) {
    if (+match[3] <= 0) continue
    const matching = spans.filter(span => span.end > match.index && span.start < match.index + match[0].length)
    const covered = matching.map(span => span.token), first = matching[0]
    const unitAt=match[1] ? match.index+match[0].indexOf(match[1]) : -1
    const glyphUnit=matching.some(span=>(span.token.unitProofs??[]).some(proof=>span.start+proof.at===unitAt&&proof.unit===UNITS[match[1]]))
    const x = first.token.x + first.token.w * Math.max(0, match.index-first.start) / first.token.str.length
    const word = line.filter(token => TEMPO_WORD.test(token.str) && token.x <= x
      && x-token.x-token.w < 3*token.h).at(-1)
    found.push({ tokens: [...new Set([...covered, ...(word ? [word] : [])])], x,
      bpm: +match[3], unit: UNITS[match[1]] ?? null, dotted: !!match[2],
      unitEvidence: match[1] ? glyphUnit ? 'source-glyph' : 'explicit-unit-text' : 'unknown',
      words: word?.str.replace(/\(?\s*\S?\.?\s*=.*$/, '').trim() })
  }
  if (!found.length) {
    const word = line.find(token => TEMPO_WORD.test(token.str))
    if (word) found.push({ tokens: [word], x: word.x, bpm: null, unit: 'quarter', dotted: false, words: word.str })
  }
  return found
}

/** Join the pieces a PDF splits text into ("C" "sus" "/F") and drop music-font glyphs. */
export function tokens(items) {
  // A metronome font's advance width can leave a larger gap before its separate
  // augmentation dot. Join this small notation group before generic text joining
  // drops isolated music glyphs. The source beat, optional dot and equality must
  // share a baseline and be adjacent; a lone note never becomes text or tempo.
  const used = new Set(), notation = []
  for (const beat of items) {
    const unit = GLYPHS[beat.str.trim()]
    if (!UNITS[unit]) continue
    const adjacent = items.filter(t => t !== beat && t.x >= beat.x + beat.w - .15*beat.h
      && Math.abs(t.y-beat.y) < .35*Math.max(t.h,beat.h)).sort((a,b)=>a.x-b.x)
    let right=beat.x+beat.w, dotted=false, group=[beat], equality
    for (const next of adjacent) {
      if(next.x-right > .55*beat.h)break
      const value=next.str.trim()
      if(!dotted && (GLYPHS[value]==='.' || value==='.')) {dotted=true;group.push(next);right=next.x+next.w;continue}
      if(/^=\s*(?:c(?:irc)?a\.?\s*)?(?:\d{2,3})?$/.test(value)){equality=next;group.push(next)}
      break
    }
    if(!equality)continue
    if(!/\d/.test(equality.str)) {
      const number=adjacent.find(t=>t.x>=equality.x+equality.w-.1*beat.h && t.x-equality.x-equality.w<.55*beat.h && /^\d{2,3}$/.test(t.str.trim()))
      if(!number)continue
      group.push(number)
    }
    group.forEach(t=>used.add(t))
    notation.push({...beat,str:`${unit}${dotted?'.':''} ${group.slice(dotted?2:1).map(t=>t.str).join(' ')}`,
      w:Math.max(...group.map(t=>t.x+t.w))-beat.x, sourceBeat:group.map(t=>({...t}))})
  }
  const clean = [...items.filter(t=>!used.has(t)),...notation]
    .map((it) => {
      let str=''
      const unitProofs=(it.sourceBeat||it.tempoEvidence) ? [{at:0,unit:it.tempoEvidence?.unit??UNITS[it.str.match(/^(q|h|e|w|n16|n32|n64)/)?.[0]]}] : []
      for(const glyph of it.str){
        const mapped=GLYPHS[glyph]??(/[\uE000-\uF8FF]/u.test(glyph)?'':glyph)
        if(UNITS[GLYPHS[glyph]])unitProofs.push({at:str.length,unit:UNITS[GLYPHS[glyph]]})
        str+=mapped
      }
      return {...it,music:!/[^\uE000-\uF8FF\s]/.test(it.str)||/^[♩𝅘𝅥𝅗𝅥♪𝅘𝅥𝅮𝅝𝅘𝅥𝅯𝅘𝅥𝅰𝅘𝅥𝅱]\.?$/u.test(it.str.trim()),str,unitProofs}
    })
    .filter((it) => it.str.trim())
    .sort((a, b) => a.x - b.x)
  const out = []
  for (const it of clean) {
    const gap = (t) => it.x - (t.x + t.w)
    const prev = out.findLast((t) => Math.abs(t.y - it.y) < 0.4 * Math.max(t.h, it.h) && gap(t) < 0.2 * t.h && gap(t) > -0.6 * t.h)
    if (prev) {
      const separator=(it.tempoEvidence||it.sourceBeat||it.music&&/^[qhe]\.?$/.test(it.str))&&prev.str.length>1?' ':''
      const offset=prev.str.length+separator.length
      Object.assign(prev,{str:prev.str+separator+it.str,unitProofs:[...prev.unitProofs,...it.unitProofs.map(p=>({...p,at:p.at+offset}))],
        requiresUnitGlyph:prev.requiresUnitGlyph||it.requiresUnitGlyph,w:it.x+it.w-prev.x,music:prev.music&&it.music,
        ...(it.tempoEvidence?{tempoEvidence:it.tempoEvidence,source:it.source}:{})})
    }
    else out.push({ ...it })
  }
  return out
    .filter((t) => !t.music)
    .map((t) => {
      const compact = t.str.replace(/\s+/g, '') // chord symbols come as "F" + " sus"
      return { ...t, str: CHORD.test(compact) ? compact : t.str.replace(/\s+/g, ' ').trim(),
        unitProofs:t.unitProofs.map(p=>({...p,at:t.str.slice(0,p.at).replace(/\s+/g,' ').trimStart().length})) }
    })
}

function element(doc, name, text, attrs = {}) {
  const el = doc.createElement(name)
  if (text != null) el.textContent = text
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v)
  return el
}

function harmony(doc, [, step, alter, kind, bassStep, bassAlter], offset) {
  const el = element(doc, 'harmony')
  const root = el.appendChild(element(doc, 'root'))
  root.append(element(doc, 'root-step', step))
  if (alter) root.append(element(doc, 'root-alter', ALTER[alter]))
  el.append(element(doc, 'kind', KINDS[kind] ?? 'other', { text: kind }))
  if (bassStep) {
    const bass = el.appendChild(element(doc, 'bass'))
    bass.append(element(doc, 'bass-step', bassStep))
    if (bassAlter) bass.append(element(doc, 'bass-alter', ALTER[bassAlter]))
  }
  if (offset) el.append(element(doc, 'offset', offset))
  return el
}

const place = (id) => {
  const m = /-p(\d+)-(\d+)-(\d+)$/.exec(id ?? '')
  return m && { page: +m[1], x: +m[2], y: +m[3] }
}

/**
 * Annotate the MusicXML document in place. Returns what it added: {title, lyrics, chords}.
 * `text[p]` is the token list of page p.
 */
export function annotate(doc, text, options = {}) {
  const field = doc.querySelector('miscellaneous-field[name="staff-layout"]')
  const layout = options.layout ?? JSON.parse(field?.textContent ?? '[]')
  const container = field?.parentNode
  field?.remove()
  if (container && !container.children.length) container.remove()
  const added = { title: '', lyrics: 0, chords: 0, tempo: 0 }
  const audit = [...(options.sourceAudit ?? [])]
  const instrument = sourceInstrumentMetadata(doc, text, layout)
  added.instrument = instrument
  audit.push({ kind: 'instrument', ...instrument })
  const firstMusicPage = layout.findIndex(staffs => staffs?.length)

  // Every note and rest with a known place, filed under the staff it lies closest to.
  const byStaff = new Map() // "page/staff index" -> [{el, x}]
  for (const el of doc.querySelectorAll('note[id]')) {
    const at = place(el.getAttribute('id'))
    const staffs = at && layout[at.page]
    if (!staffs?.length || el.querySelector(':scope > chord, :scope > grace')) continue
    const distance = ([, top, , bottom]) => Math.max(top - at.y, at.y - bottom, 0)
    const index = staffs.reduce((best, s, i) => (distance(s) < distance(staffs[best]) ? i : best), 0)
    const key = `${at.page}/${index}`
    byStaff.set(key, [...(byStaff.get(key) ?? []), { el, x: at.x, pitched: !!el.querySelector(':scope > pitch') }])
  }
  for (const notes of byStaff.values()) notes.sort((a, b) => a.x - b.x)

  /** The note or rest sounding where a chord symbol stands at x, and how far into it. */
  function under(anchors, x, reach) {
    // A whole-bar rest is printed mid-bar: its time starts half a bar to the left.
    const starts = anchors.map((a, i) => {
      const wholeBar = a.el.querySelector(':scope > rest[measure]') || !a.el.querySelector(':scope > type')
      const width = ((anchors[i + 1]?.x ?? a.x) - (anchors[i - 1]?.x ?? a.x)) / (anchors[i + 1] && anchors[i - 1] ? 2 : 1)
      return wholeBar && !a.pitched ? a.x - width / 2 : a.x
    })
    let i = starts.findLastIndex((start) => start <= x + reach)
    if (i < 0) i = 0
    const end = starts[i + 1] ?? starts[i] + 2 * (starts[i] - (starts[i - 1] ?? starts[i]))
    const duration = +(anchors[i].el.querySelector(':scope > duration')?.textContent ?? 0)
    const beat = +(anchors[i].el.closest('part').querySelector('divisions')?.textContent ?? 1)
    const into = end > starts[i] ? Math.min(Math.max((x - starts[i]) / (end - starts[i]), 0), 0.95) : 0
    return { anchor: anchors[i], offset: Math.round((into * duration) / beat) * beat }
  }

  layout.forEach((staffs, page) => {
    const all = text[page] ?? []
    if (!staffs.length || !all.length) return
    const middle = (t) => t.y - 0.35 * t.h
    const inStaff = (t) => staffs.some(([, top, , bottom]) => middle(t) > top && middle(t) < bottom)

    if (!added.title) {
      // The largest text above the first staff is the title; text at the right, the composer.
      const head = all.filter((t) => t.y < staffs[0][1] - (staffs[0][3] - staffs[0][1]) && t.str.length > 1)
      const largest = head.reduce((best, t) => (!best || t.h > best.h ? t : best), null)
      // OCR gives a title word by word: take its whole line.
      const title = largest && {
        ...largest,
        str: head.filter((t) => Math.abs(t.y - largest.y) < 0.5 * largest.h && t.h > 0.7 * largest.h)
          .sort((a, b) => a.x - b.x).map((t) => t.str).join(' '),
      }
      if (title && page === Math.min(...layout.map((s, i) => (s.length ? i : Infinity)))) {
        added.title = title.str
        const composer = head.filter((t) => t.h < 0.7 * title.h && t.x + t.w / 2 > (staffs[0][0] + staffs[0][2]) / 2)
          .reduce((best, t) => (!best || t.y > best.y ? t : best), null)
        const root = doc.documentElement
        root.querySelector(':scope > work')?.remove()
        root.insertBefore(element(doc, 'work'), root.firstChild).append(element(doc, 'work-title', title.str))
        if (composer) root.querySelector(':scope > identification').prepend(element(doc, 'creator', composer.str, { type: 'composer' }))
      }
    }

    // Lines of text between the staves: chord symbols belong to the staff below,
    // lyrics to the staff above.
    // OCR gives each word its own box, so baselines and heights wobble: group generously.
    const heights = all.map((t) => t.h).sort((a, b) => a - b)
    const typical = heights[heights.length >> 1]
    const lines = []
    for (const t of all.filter((t) => !inStaff(t)).sort((a, b) => a.y - b.y)) {
      const line = lines.at(-1)
      if (line && t.y - line[0].y < 0.5 * Math.max(t.h, typical)) line.push(t)
      else lines.push([t])
    }
    const verses = new Map() // staff index -> lyric lines so far
    for (const line of lines) {
      line.sort((a, b) => a.x - b.x)
      const y = middle(line[0])
      const above = staffs.map((s, i) => [y - s[3], i]).filter(([d]) => d > 0).sort((a, b) => a[0] - b[0])[0]
      const below = staffs.map((s, i) => [s[1] - y, i]).filter(([d]) => d > 0).sort((a, b) => a[0] - b[0])[0]
      const unit = (i) => (staffs[i][3] - staffs[i][1]) / 4
      const nearerBelow = below && (!above || below[0] < above[0])

      // A tempo stands above its staff, perhaps beside other text on the same line.
      // Metronome glyph font boxes can be much taller than their visible ink.
      // Use the mark's own baseline and the staff below it, rather than the
      // lyric/chord center heuristic which can assign it to the previous staff.
      const tempos = readTempos(line)
      if (tempos.length) {
        const used = new Set()
        for (const tempo of tempos) {
          if (tempo.bpm && !tempo.unit) { audit.push({kind:'tempo',page,status:'unknown',reason:'unit-unknown',bpm:tempo.bpm}); continue }
          if(tempo.bpm&&tempo.tokens.some(t=>t.requiresUnitGlyph)&&tempo.unitEvidence!=='source-glyph') {
            audit.push({kind:'tempo',page,status:'unknown',reason:'unit-not-source-verified',bpm:tempo.bpm});continue
          }
          const ys = tempo.tokens.map(t => t.y).sort((a,b)=>a-b), baseline=ys[ys.length>>1]
          const eligible = staffs.map((s,i)=>[s[1]-baseline,i]).filter(([gap,i])=>gap>=-.1*unit(i)&&gap<12*unit(i)).sort((a,b)=>a[0]-b[0])
          const target = tempo.bpm ? eligible[0] : nearerBelow && below?.[0]<12*unit(below[1]) ? below : null
          if (!target) { audit.push({kind:'tempo',page,status:'unknown',reason:'no-staff-below',bpm:tempo.bpm}); continue }
          const tempoAnchors = byStaff.get(`${page}/${target[1]}`) ?? []
          // Tempo text often starts before its onset (before a changed meter).
          // Chord placement's "last onset to the left" would attach it to the old bar.
          const anchor = tempoAnchors.length ? tempoAnchors.reduce((best, current) => Math.abs(current.x-tempo.x) < Math.abs(best.x-tempo.x) ? current : best) : null
          let measure=anchor?.el.parentNode, before=anchor?.el, binding='source-coordinate'
          const openingEvidence=tempo.tokens.some(t=>t.tempoEvidence?.staff===0)
            && tempo.x<=staffs[0][0]+16*unit(0)
          if(!measure && openingEvidence && page===firstMusicPage && target[1]===0 && doc.querySelectorAll('score-partwise > part').length===1) {
            measure=doc.querySelector('score-partwise > part > measure');before=measure?.querySelector(':scope > note');binding='opening-source-first-staff'
          }
          if(!measure) {audit.push({kind:'tempo',page,staff:target[1],status:'unknown',reason:'no-source-anchor',bpm:tempo.bpm});continue}
          const duplicate=[...measure.querySelectorAll(':scope > direction > direction-type > metronome')].some(m=>
            +(m.querySelector('per-minute')?.textContent)===tempo.bpm&&m.querySelector('beat-unit')?.textContent===tempo.unit&&!!m.querySelector('beat-unit-dot')===tempo.dotted)
          if(duplicate){tempo.tokens.forEach(token=>used.add(token));continue}
          measure.insertBefore(tempoDirection(doc, tempo), before ?? null)
          added.tempo++
          audit.push({kind:'tempo',page,staff:target[1],measure:measure.getAttribute('number'),part:measure.parentNode.getAttribute('id'),status:'applied',binding,
            bpm:tempo.bpm,unit:tempo.unit,dotted:tempo.dotted,quarterBpm:quarterTempo(tempo),source:tempo.tokens.map(t=>({str:t.str,x:t.x,y:t.y,w:t.w,h:t.h,source:t.source}))})
          tempo.tokens.forEach(token => used.add(token))
        }
        line.splice(0, line.length, ...line.filter(token => !used.has(token)))
        if (!line.length) continue
      }

      const anchors = byStaff.get(`${page}/${below?.[1]}`) ?? []

      const chords = line.map((t) => CHORD.exec(t.str))
      // Chord symbols sit close above their staff, lyrics close below theirs: the nearer
      // staff says which a line is. (Its words alone don't: OCR garbles some chords, and
      // "A" or "Am" can be a syllable.)
      const found = chords.filter(Boolean).length

      if (nearerBelow) {
        if (below[0] > 8 * unit(below[1]) || found < Math.min(2, line.length)) continue
        // Rehearsal letters match too, but are set in another size than the chords.
        const sizes = line.filter((t, i) => chords[i]).map((t) => t.h).sort((a, b) => a - b)
        const size = sizes[sizes.length >> 1]
        line.forEach((t, i) => {
          if (!chords[i] || !anchors.length || Math.abs(t.h - size) > 0.12 * size) return
          const { anchor, offset } = under(anchors, t.x, unit(below[1]))
          anchor.el.parentNode.insertBefore(harmony(doc, chords[i], offset), anchor.el)
          added.chords++
        })
      } else if (above[0] < 10 * unit(above[1]) && found < 0.5 * line.length) {
        // Other programs write several words as one piece of text: place each by its share.
        const words = line
          .flatMap((t) => {
            let at = 0
            return t.str.split(/ |(?<=\p{L}[-‐])(?=\p{L})/u).map((str) => {  // "Danc-ing" is two syllables
              const word = { ...t, str, x: t.x + (t.w * at) / t.str.length, w: (t.w * str.length) / t.str.length }
              at += str.length + 1
              return word
            })
          })
          .filter((t) => t.str && !/^[\d.,()]+$/.test(t.str))
        if (words.filter((t) => !/^[-‐–—_]+$/.test(t.str)).length < 3) continue
        const verse = (verses.get(above[1]) ?? 0) + 1
        verses.set(above[1], verse)
        const free = (byStaff.get(`${page}/${above[1]}`) ?? []).filter((a) => a.pitched)
        const reach = 3 * unit(above[1])
        let joined = false // the syllable before ended in a hyphen
        for (let i = 0; i < words.length; i++) {
          const raw = words[i].str
          if (/^[-‐]+$/.test(raw)) { joined = true; continue }
          if (/^[–—_]+$/.test(raw)) continue // a line which extends a syllable
          const syllable = raw.replace(/^[-‐]+|[-‐–—_]+$/g, '')
          const next = words[i + 1]?.str ?? ''
          const joins = /[-‐]$/.test(raw) || /^[-‐]/.test(next)
          const centre = words[i].x + words[i].w / 2
          const note = free.reduce((best, a) => (!best || Math.abs(a.x - centre) < Math.abs(best.x - centre) ? a : best), null)
          if (syllable && note && Math.abs(note.x - centre) < reach) {
            free.splice(free.indexOf(note), 1)
            const lyric = note.el.appendChild(element(doc, 'lyric', null, { number: verse }))
            lyric.append(element(doc, 'syllabic', joined ? (joins ? 'middle' : 'end') : joins ? 'begin' : 'single'), element(doc, 'text', syllable))
            added.lyrics++
          }
          joined = joins
        }
      }
    }
  })
  let identification=doc.querySelector('score-partwise > identification')
  if(!identification){identification=element(doc,'identification');doc.documentElement.insertBefore(identification,doc.querySelector('score-partwise > defaults, score-partwise > credit, score-partwise > part-list, score-partwise > part'))}
  let miscellaneous=identification.querySelector(':scope > miscellaneous')
  if(!miscellaneous)miscellaneous=identification.appendChild(element(doc,'miscellaneous'))
  miscellaneous.querySelector('miscellaneous-field[name="metadata-audit"]')?.remove()
  miscellaneous.append(element(doc,'miscellaneous-field',JSON.stringify(audit),{name:'metadata-audit'}))
  added.metadataAudit=audit
  return added
}
