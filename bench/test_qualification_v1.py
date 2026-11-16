"""Semantic qualification counterexamples, independent of recognizer output."""
import copy
import unittest
import xml.etree.ElementTree as E

from qualification_v1 import compare


def score():
    root = E.fromstring('''<score-partwise version="4.0"><part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>1</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes><note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>quarter</type></note></measure><measure number="2"><note><pitch><step>D</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>quarter</type></note></measure></part></score-partwise>''')
    return root


def direction(root, bar, attrs=None, words=None, symbol=None):
    d = E.SubElement(root.findall('part/measure')[bar], 'direction')
    if words is not None:
        E.SubElement(E.SubElement(d, 'direction-type'), 'words').text = words
    if symbol:
        E.SubElement(E.SubElement(d, 'direction-type'), symbol)
    if attrs:
        E.SubElement(d, 'sound', attrs)
    return d


class QualificationTests(unittest.TestCase):
    def test_wrong_key_preserves_core_but_fails_semantic_layer(self):
        a, b = score(), score(); b.find('.//fifths').text = '-1'
        r = compare(a, b)
        self.assertTrue(r['coreGate']['passes']); self.assertFalse(r['performanceGateV1Passes'])
        self.assertFalse(r['headers']['categories']['key']['matches'])

    def test_wrong_clef_and_octave_preserve_core_but_fail(self):
        for tag, text in [('sign', 'F'), ('clef-octave-change', '-1')]:
            a, b = score(), score(); clef = b.find('.//clef'); node = clef.find(tag)
            if node is None:
                node = E.SubElement(clef, tag)
            node.text = text
            r = compare(a, b)
            self.assertTrue(r['coreGate']['passes']); self.assertFalse(r['performanceGateV1Passes'])

    def test_missing_dc_jump_preserves_core_but_fails(self):
        a, b = score(), score(); direction(a, 1, {'dacapo': 'yes'})
        r = compare(a, b)
        self.assertTrue(r['coreGate']['passes']); self.assertFalse(r['performanceGateV1Passes'])

    def test_beam_omission_is_fidelity_diagnostic_not_wrong_rhythm(self):
        a, b = score(), score()
        E.SubElement(a.find('.//note'), 'beam', number='1').text = 'begin'
        r = compare(a, b)
        self.assertTrue(r['coreGate']['passes']); self.assertTrue(r['performanceGateV1Passes'])
        self.assertFalse(r['notationFidelity']['explicitBeamsMatch'])
        self.assertEqual(r['notationFidelity']['beamStatus'], 'omitted-explicit-beams-auto-beaming-possible')

    def test_redundant_inherited_headers_are_equivalent(self):
        a, b = score(), score()
        b.findall('part/measure')[1].insert(0, copy.deepcopy(b.find('.//attributes')))
        self.assertTrue(compare(a, b)['performanceGateV1Passes'])

    def test_equivalent_key_encodings_and_chromatic_transpose_spellings(self):
        a, b = score(), score(); key = b.find('.//key'); key.clear()
        E.SubElement(key, 'key-step').text = 'F'; E.SubElement(key, 'key-alter').text = '1'
        self.assertTrue(compare(a, b)['performanceGateV1Passes'])
        for root, chromatic, octave in [(a, '-12', '1'), (b, '0', '0')]:
            node = E.SubElement(root.find('.//attributes'), 'transpose')
            E.SubElement(node, 'chromatic').text = chromatic
            E.SubElement(node, 'octave-change').text = octave
        self.assertTrue(compare(a, b)['performanceGateV1Passes'])

    def test_midmeasure_key_change_not_lost(self):
        a, b = score(), score()
        attrs = E.SubElement(b.find('part/measure'), 'attributes')
        E.SubElement(E.SubElement(attrs, 'key'), 'fifths').text = '2'
        self.assertFalse(compare(a, b)['performanceGateV1Passes'])

    def test_arbitrary_voice_part_and_segno_tokens_do_not_change_semantics(self):
        a = score(); direction(a, 0, {'segno': 'S1'}, symbol='segno'); direction(a, 1, {'dalsegno': 'S1'})
        b = copy.deepcopy(a); b.find('part').set('id', 'OtherPartId')
        for n in b.findall('.//voice'):
            n.text = 'arbitrary'
        for sound in b.findall('.//sound'):
            for name in ('segno', 'dalsegno'):
                if name in sound.attrib:
                    sound.set(name, 'RenamedSegno')
        r = compare(a, b)
        self.assertTrue(r['performanceGateV1Passes']); self.assertTrue(r['notationFidelity']['explicitBeamsMatch'])

    def test_bad_jump_reference_is_not_silently_repaired(self):
        a = score(); direction(a, 0, {'segno': 'S1'}); direction(a, 1, {'dalsegno': 'S1'})
        b = copy.deepcopy(a); b.find('.//sound[@dalsegno]').set('dalsegno', 'wrong')
        r = compare(a, b)
        self.assertFalse(r['supported']); self.assertFalse(r['performanceGateV1Passes'])

    def test_different_coda_target_or_repeat_iteration_is_wrong(self):
        a = score(); direction(a, 0, {'tocoda': 'C1'}); direction(a, 1, {'coda': 'C1'})
        b = copy.deepcopy(a); b.find('.//sound[@tocoda]').set('time-only', '1')
        self.assertFalse(compare(a, b)['performanceGateV1Passes'])

    def test_visual_words_and_sound_dc_are_equivalent(self):
        a, b = score(), score(); direction(a, 1, {'dacapo': 'yes'}); direction(b, 1, words='D.C.')
        self.assertTrue(compare(a, b)['performanceGateV1Passes'])

    def test_fine_duration_is_not_an_arbitrary_label(self):
        a = score(); direction(a, 1, {'fine': '1'})
        b = copy.deepcopy(a); b.find('.//sound').set('fine', '2')
        self.assertFalse(compare(a, b)['performanceGateV1Passes'])

    def test_octave_shift_number_is_label_but_span_and_direction_matter(self):
        a = score()
        for bar, typ in [(0, 'down'), (1, 'stop')]:
            d = direction(a, bar); E.SubElement(E.SubElement(d, 'direction-type'), 'octave-shift', type=typ, number='1', size='8')
        b = copy.deepcopy(a)
        for node in b.findall('.//octave-shift'):
            node.set('number', '6')
        self.assertTrue(compare(a, b)['performanceGateV1Passes'])
        b.find('.//octave-shift').set('type', 'up')
        self.assertFalse(compare(a, b)['performanceGateV1Passes'])

    def test_transpose_and_unknown_context_cannot_qualify(self):
        a, b = score(), score(); t = E.SubElement(b.find('.//attributes'), 'transpose'); E.SubElement(t, 'chromatic').text = '-9'
        self.assertFalse(compare(a, b)['performanceGateV1Passes'])
        a.find('.//attributes').remove(a.find('.//clef')); b = copy.deepcopy(a)
        r = compare(a, b); self.assertFalse(r['truthHasKnownKeyAndClef']); self.assertFalse(r['performanceGateV1Passes'])


if __name__ == '__main__':
    unittest.main()
