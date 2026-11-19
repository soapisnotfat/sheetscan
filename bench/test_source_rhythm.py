"""Source association and abstention tests; no score-specific answers."""
import copy,sys,unittest
from pathlib import Path
from fractions import Fraction
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'web/src/py'))
from source_rhythm import constrain,mark_staff
from homr.transformer.vocabulary import EncodedSymbol

def event(x,y,staff,pitch='E4',rhythm='note_8'):
 s=EncodedSymbol(rhythm,pitch=pitch,position='upper' if staff==0 else 'lower');s._source_staff=staff;s._source_clef_offset=int(pitch[1])*7+'CDEFGAB'.index(pitch[0]);s.image_coordinates=(x,y);return s

def setup():
 upper=[event(30,40,0),event(60,40,0)];lower=[event(x,140,1,pitch='E3',rhythm='note_12')for x in [30,50,70]]
 marker=EncodedSymbol('chord')
 symbols=[upper[0],marker,lower[0],lower[1],upper[1],lower[2]]
 def stem(s):return {'x':s.image_coordinates[0],'heads':[{'center':list(s.image_coordinates),'staffPosition':0,'positionResidual':0}]}
 context={'page':0,'boxes':[[0,20,100,60],[0,120,100,160]],'toInput':lambda p:p,
  'descriptors':[{'system':0,'slot':0,'lane':lane}for lane in ['upper','lower']],
  'meters':[{'staff':0,'x':10,'numerator':3,'denominator':8}],
  'tuplets':[{'staff':0,'number':2,'x':45,'y':80}],
  'beams':[{'staff':i,'eventCount':len(notes),'beamCount':1,'stems':[stem(s)for s in notes]}for i,notes in enumerate([upper,lower])],
  'changes':[],'diagnostics':[]}
 return symbols,context

class SourcePolicyTests(unittest.TestCase):
 def test_source_duplet_and_plain_counterpart_preserve_identity(self):
  s,c=setup();before=[(v.rhythm,v.pitch,v.lift,v.position)for v in s];out=constrain(s,c)
  self.assertEqual([v.get_duration().fraction for v in out if v.rhythm.startswith('note')],[Fraction(3,16),Fraction(1,8),Fraction(1,8),Fraction(3,16),Fraction(1,8)])
  self.assertEqual(before,[(v.rhythm,v.pitch,v.lift,v.position)for v in out]);self.assertEqual(len(c['changes']),2)
  self.assertEqual(s[0].get_duration().fraction,Fraction(1,8))
 def test_equal_voice_totals_do_not_hide_bad_chord_order(self):
  s,c=setup();s[3],s[4]=s[4],s[3];self.assertEqual(constrain(s,c),s)
  self.assertEqual(c['diagnostics'][0]['status'],'inconsistent-global-chord-timeline')
 def test_correct_relative_intervals_with_wrong_absolute_pitches_abstain(self):
  s,c=setup()
  for stem in c['beams'][0]['stems']:stem['heads'][0]['staffPosition']=1
  self.assertEqual(constrain(s,c),s)
 def test_vertical_attention_drift_needs_absolute_source_pitch(self):
  s,c=setup();s[0].image_coordinates=(30,95);out=constrain(s,c)
  self.assertEqual(out[0].get_duration().fraction,Fraction(3,16))
 def test_wrong_clef_counterpart_abstains(self):
  s,c=setup();s[2]._source_clef_offset=999;self.assertEqual(constrain(s,c),s)
 def test_no_printed_two_abstains(self):
  s,c=setup();c['tuplets']=[];self.assertEqual(constrain(s,c),s);self.assertEqual(c['changes'],[])
 def test_printed_two_on_other_staff_does_not_bind(self):
  s,c=setup();c['tuplets'][0]['staff']=1;self.assertEqual(constrain(s,c),s)
 def test_missing_source_head_abstains(self):
  s,c=setup();c['beams'][0]['stems'][0]['heads']=[];self.assertEqual(constrain(s,c),s)
 def test_ambiguous_source_group_abstains(self):
  s,c=setup();c['beams'].append(copy.deepcopy(c['beams'][0]));self.assertEqual(constrain(s,c),s)
 def test_true_triplet_mark_prevents_plain_counterpart(self):
  s,c=setup();c['tuplets'].append({'staff':1,'number':3,'x':50,'y':180});self.assertEqual(constrain(s,c),s)
 def test_source_onset_order_contradiction_abstains(self):
  s,c=setup();c['beams'][1]['stems'][2]['heads'][0]['center'][0]=45;c['beams'][1]['stems'][2]['x']=45;s[-1].image_coordinates=(45,140)
  self.assertEqual(constrain(s,c),s);self.assertEqual(c['diagnostics'][0]['status'],'source-onset-order-unknown-or-contradictory')
 def test_wrong_printed_meter_is_not_force_filled(self):
  s,c=setup();c['meters'][0]['numerator']=6;self.assertEqual(constrain(s,c),s)
 def test_dotted_source_values_are_not_silently_undotted(self):
  s,c=setup();s[0].rhythm='note_8.';self.assertEqual(constrain(s,c),s)
 def test_repeated_printed_number_is_ambiguous(self):
  s,c=setup();c['tuplets'].append(copy.deepcopy(c['tuplets'][0]));self.assertEqual(constrain(s,c),s)

if __name__=='__main__':unittest.main()
