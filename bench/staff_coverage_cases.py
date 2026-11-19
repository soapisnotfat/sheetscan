"""CC0 source-authored range/adjacent-staff crop regressions, not blind tests."""
import hashlib,json,random,sys
from pathlib import Path
import xml.etree.ElementTree as E


def add(parent,tag,text=None,**attrs):
    node=E.SubElement(parent,tag,{k:str(v) for k,v in attrs.items()})
    if text is not None:node.text=str(text)
    return node


def make(name,ranges,font,dpi,out):
    r=E.Element('score-partwise',version='4.0');add(add(r,'work'),'work-title',name+' 2026')
    pl=add(r,'part-list');add(add(pl,'score-part',id='P1'),'part-name','Piano' if len(ranges)==2 else 'Flute')
    part=add(r,'part',id='P1');rng=random.Random(90411+sum(map(ord,name)))
    for bar in range(1,9):
        m=add(part,'measure',number=bar)
        if bar==1:
            a=add(m,'attributes');add(a,'divisions',4);add(add(a,'key'),'fifths',0)
            t=add(a,'time');add(t,'beats',4);add(t,'beat-type',4)
            if len(ranges)==2:add(a,'staves',2)
            for staff,base in enumerate(ranges,1):
                clef=add(a,'clef',number=staff) if len(ranges)==2 else add(a,'clef')
                add(clef,'sign','F' if staff==2 else 'G');add(clef,'line',4 if staff==2 else 2)
        for staff,choices in enumerate(ranges,1):
            if staff>1:add(add(m,'backup'),'duration',16)
            for beat in range(4):
                pitch=rng.choice(choices);n=add(m,'note');p=add(n,'pitch')
                add(p,'step',pitch[0]);add(p,'octave',int(pitch[1:]));add(n,'duration',4)
                add(n,'voice',staff);add(n,'type','quarter');add(n,'staff',staff)
    dest=out/name;dest.mkdir(parents=True,exist_ok=True)
    truth=dest/'truth.musicxml';E.ElementTree(r).write(truth,encoding='utf-8',xml_declaration=True)
    return {'id':name,'split':'range-dev','font':font,'dpi':dpi,'layout':'auto','seed':90411,'truth':'truth.musicxml','truthSha256':hashlib.sha256(truth.read_bytes()).hexdigest()}


def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    cases=[('mono-high',[['C6','D6','E6','F6','G6','A6','B6']],'Leipzig',160),
           ('mono-low',[['C3','D3','E3','F3','G3','A3']],'Bravura',220),
           ('mono-mixed',[['C3','E3','G3','C4','E4','C5','G5','C6','E6','G6']],'Leipzig',190),
           ('grand-outer',[['C6','D6','E6','G6','A6'],['C1','D1','E1','G1','A1']],'Bravura',200),
           ('grand-inward',[['C3','D3','E3','G3','A3'],['C4','D4','E4','G4','A4']],'Leipzig',180),
           ('grand-mixed',[['C3','E4','G5','A6'],['C1','E2','G3','C4']],'Bravura',240)]
    manifest={'scope':'new self-authored CC0 development range regression; paired identical rasters; not independent blind accuracy','cases':[make(*case,out) for case in cases]}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':main()
