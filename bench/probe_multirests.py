"""Source-only multirest evidence and frozen raw-decoder diagnostic.

No reference score is read. --raw invokes unchanged frozen recognition source
and saves original staff/model inputs plus decoder output before postprocessing.
Default mode only calls the current source-region API and optional local OCR.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def raw(args):
    source=Path(args.source).resolve();sys.path.insert(0,str(source))
    import pipeline
    from homr.transformer.decoder_inference import ScoreDecoder
    from homr.transformer.encoder_inference import Encoder
    from homr.segmentation.config import segnet_path_onnx
    report={'input_sha256':sha(args.image),'source':str(source),
            'source_sha256':{p.name:sha(p) for p in source.iterdir() if p.suffix in ('.py','.json')},
            'scope':'raw decoder output before staff filtering/codec/XML; no output correction or reference score',
            'homr_version':importlib.metadata.version('homr'),
            'native_models_sha256':{Path(p).name:sha(p) for p in [segnet_path_onnx,pipeline._TRANSFORMER.filepaths.encoder_path,pipeline._TRANSFORMER.filepaths.decoder_path]},
            'staffs':[],'encoder_inputs':[],'raw_decoder':[]}
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    def flush():(out/'raw-probe.json').write_text(json.dumps(report,indent=2)+'\n')
    base_parse=pipeline.staff_parsing.parse_staff_tromr
    def parse(*,staff_image,staff,config):
        index=len(report['staffs']);im=np.asarray(staff_image)
        display=np.rint(im*255).astype(np.uint8) if im.dtype.kind=='f' and im.max()<=1 else im
        cv2.imwrite(str(out/f'staff-{index}.png'),display)
        report['staffs'].append({'index':index,'shape':list(im.shape),'raw_sha256':hashlib.sha256(im.tobytes()).hexdigest(),
                                'unit':float(staff.average_unit_size)})
        flush();return base_parse(staff_image=staff_image,staff=staff,config=config)
    pipeline.staff_parsing.parse_staff_tromr=parse
    base_encoder=Encoder.generate
    def encode(self,x,*a,**kw):
        index=len(report['encoder_inputs']);array=np.asarray(x);np.save(out/f'encoder-{index}.npy',array)
        report['encoder_inputs'].append({'index':index,'shape':list(array.shape),'dtype':str(array.dtype),'sha256':hashlib.sha256(array.tobytes()).hexdigest()})
        flush();return base_encoder(self,x,*a,**kw)
    Encoder.generate=encode
    base_generate=ScoreDecoder.generate
    def generate(self,*a,**kw):
        decoded=base_generate(self,*a,**kw)
        report['raw_decoder'].append([{'rhythm':s.rhythm,'pitch':s.pitch,'lift':s.lift,'position':s.position,
                                      'coordinates':[float(x) for x in s.coordinates] if s.coordinates is not None else None}
                                     for s in decoded]);flush();return decoded
    ScoreDecoder.generate=generate
    xml=pipeline.scan([str(args.image)],printed_tuplets=True)
    (out/'reading.musicxml').write_text(xml);report['output_sha256']=sha(out/'reading.musicxml');flush()
    print(json.dumps({'staffs':len(report['staffs']),'rests':[[s['rhythm'] for s in row if s['rhythm'].startswith('rest')] for row in report['raw_decoder']]},indent=2))


def regions(args):
    sys.path.insert(0,str(ROOT/'web/src/py'))
    from score_numbers import read_multirest_regions
    from number_ocr import read_number
    image=cv2.imread(str(args.image));boxes=json.loads(Path(args.boxes).read_text())
    result=read_multirest_regions(image,boxes)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    for i,item in enumerate(result):
        left,top,right,bottom=item['numberBox'];crop=image[top:bottom,left:right]
        cv2.imwrite(str(out/f'number-{i}.png'),crop)
        if args.ocr:item['reading']=read_number(crop)
    report={'source_sha256':sha(args.image),'module_sha256':sha(ROOT/'web/src/py/score_numbers.py'),'boxes':boxes,'regions':result}
    (out/'regions.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--image',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--raw',action='store_true');p.add_argument('--source',type=Path,default=ROOT/'dev-samples/candidates/v8-bounded-fragments/source')
    p.add_argument('--boxes',type=Path);p.add_argument('--ocr',action='store_true');args=p.parse_args();(raw if args.raw else regions)(args)
