"""Paired same-pixel crop experiment. Neither model receives reference XML."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
import xml.etree.ElementTree as E
from practice_metrics import compare
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('baseline',type=Path);p.add_argument('candidate',type=Path);args=p.parse_args()
    manifest=json.loads((args.root/'manifest.json').read_text());rows=[]
    for case in manifest['cases']:
        folder=args.root/case['id'];images=sorted(folder.glob('input-*.png'))
        row={'case':case['id'],'font':case['font'],'dpi':case['dpi'],'truthSha256':hashlib.sha256((folder/'truth.musicxml').read_bytes()).hexdigest(),
             'inputs':[{'file':str(i.resolve()),'sha256':hashlib.sha256(i.read_bytes()).hexdigest()} for i in images]}
        for label,source in [('baseline',args.baseline),('candidate',args.candidate)]:
            output=folder/(label+'.musicxml')
            env={**os.environ,'SHEETSCAN_SOURCE_DIR':str(source.resolve())}
            with (folder/(label+'.log')).open('w') as log:
                subprocess.run([sys.executable,str(ROOT/'bench/recognize_case.py'),str(output),*[str(i) for i in images],'--printed-tuplets'],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
            result=E.parse(output).getroot();metrics=compare(E.parse(folder/'truth.musicxml').getroot(),result)
            (folder/(label+'.metrics.json')).write_text(json.dumps(metrics,indent=2)+'\n')
            audit=json.loads(result.findtext('.//miscellaneous-field[@name="conversion-audit"]','{}'))
            row[label]={'events':metrics['events'],'bars':metrics['readingMeasuresByPart'],'structureMatches':metrics['structureMatches'],'meterMatches':metrics['meterMatches'],'formMatches':metrics['formMatches'],'coverageChanges':audit.get('staffCoverageChanges',[]),'run':json.loads(output.with_suffix('.run.json').read_text())}
        rows.append(row);(args.root/'paired-results.json').write_text(json.dumps({'scope':manifest['scope'],'cases':rows},indent=2)+'\n')
        print(json.dumps({'case':case['id'],'baseline':row['baseline']['events'],'candidate':row['candidate']['events'],'changedCrops':len(row['candidate']['coverageChanges'])}),flush=True)


if __name__=='__main__':main()
