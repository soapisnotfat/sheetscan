# SPDX-License-Identifier: OFL-1.1
"""Synthetic accidental training with a new frozen Eugene font test.

No score image, prediction or visual-label file is read. Font bytes must match
bench/accidental-fonts/manifest.json. Training needs torch; browser inference
uses only NumPy/cv2. Train/dev select gates, then test refuses model-byte drift.
"""
import argparse
import base64
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request

import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'web/src/py'))
from accidental_glyphs import normalize_ink

LABELS=['unknown','natural','sharp','flat','double-sharp','double-flat']
CODES={'natural':0xe261,'sharp':0xe262,'flat':0xe260,'double-sharp':0xe263,'double-flat':0xe264}
TRAIN=['Bravura','Leipzig','Leland','Sebastian']
TEST=['Eugene']
SEEDS={'train':906410,'dev':906411,'test':906412}
COUNTS={'train':(2400,15000),'dev':(500,5000),'test':(700,7000)}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest():
    return json.loads((ROOT/'bench/accidental-fonts/manifest.json').read_text())['fonts']


def font_path(directory,name):
    item=next(i for i in manifest() if i['name']==name)
    path=Path(directory)/item['filename']
    if not path.exists() and name in ('Bravura','Leipzig'):
        path=ROOT.parent/'fonts'/item['filename']
    if not path.exists() and name in ('Leland','Sebastian','NotoSans'):
        path=Path('/tmp/tuplet-glyph-fonts')/item['filename']
    if sha(path)!=item['sha256']:
        raise RuntimeError(f'Font hash mismatch: {name}')
    return path


@lru_cache(None)
def raster(path,codepoint):
    font=ImageFont.truetype(path,200); character=chr(codepoint)
    if bytes(font.getmask(character))==bytes(font.getmask(chr(0x10fffd))):
        return None
    left,top,right,bottom=font.getbbox(character)
    im=Image.new('L',(right-left+16,bottom-top+16),0)
    ImageDraw.Draw(im).text((8-left,8-top),character,font=font,fill=255)
    a=np.asarray(im);points=cv2.findNonZero((a>32).astype(np.uint8))
    if points is None:return None
    x,y,w,h=cv2.boundingRect(points)
    return a[y:y+h,x:x+w].astype(np.float32)/255


def bank(directory,names,codes):
    result=[]
    for name in names:
        path=str(font_path(directory,name))
        for code in codes:
            a=raster(path,code)
            if a is not None:result.append((name,code,a))
    return result


def augment(value,rng,condition,kind=None,negative_mode=None):
    height=int(rng.integers(14,63));width=max(3,round(height*value.shape[1]/value.shape[0]*rng.uniform(.8,1.2)))
    value=cv2.resize(value,(width,height),interpolation=cv2.INTER_AREA)
    canvas=np.zeros((height+18,width+80),np.float32)
    canvas[9:9+height,40:40+width]=value
    unit=height/rng.uniform(2.5,3.5) if kind!='double-sharp' else height/rng.uniform(1,1.8)
    if negative_mode=='merged':
        cv2.ellipse(canvas,(40+width,height//2+9),(max(4,round(unit*.7)),max(3,round(unit*.45))),-20,0,360,1,-1)
    elif negative_mode=='multi-glyph':
        shift=max(2,width//2)
        canvas[9:9+height,40+width+shift:40+2*width+shift]=value[:,:max(0,min(width,canvas.shape[1]-40-width-shift))]
    transform=cv2.getRotationMatrix2D((canvas.shape[1]/2,canvas.shape[0]/2),float(rng.uniform(-3,3)),1)
    canvas=cv2.warpAffine(canvas,transform,(canvas.shape[1],canvas.shape[0]))
    if rng.random()<.3:canvas=cv2.GaussianBlur(canvas,(3,3),rng.uniform(.1,.5))
    ink=(canvas>rng.uniform(.3,.65)).astype(np.uint8)
    if condition in ('staff-removed','staff-raw'):
        y=int(rng.integers(9,height+9));thickness=int(rng.choice([1,1,2]))
        for i in (-2,-1,0,1,2):
            yy=round(y+i*unit)
            if 0<=yy<len(ink):ink[yy:yy+thickness,:]=1
        if condition=='staff-removed':
            lines=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,max(12,round(7*unit))),np.uint8))
            ink=cv2.morphologyEx(ink-lines,cv2.MORPH_CLOSE,np.ones((3,1),np.uint8))
        else:
            # Runtime receives an accidental bbox, not the full staff width.
            ink=ink[:,max(0,37):min(ink.shape[1],43+width)]
    if condition=='dropout':
        yy=int(rng.integers(10,height+8));ink[yy:yy+int(rng.integers(1,3)),:]=0
        ink=cv2.morphologyEx(ink,cv2.MORPH_CLOSE,np.ones((3,1),np.uint8))
    if negative_mode=='fragment':
        extent=cv2.findNonZero(ink)
        if extent is None:return np.zeros((32,24),np.float32)
        _,first,_,span=cv2.boundingRect(extent)
        cutoff=first+int(rng.uniform(.3,.65)*span)
        if rng.random()<.5:ink[:cutoff,:]=0
        else:ink[cutoff:,:]=0
    points=cv2.findNonZero(ink)
    if points is None:return np.zeros((32,24),np.float32)
    x,y,w,h=cv2.boundingRect(points)
    return normalize_ink(ink[y:y+h,x:x+w])


def primitive(rng):
    a=np.zeros((64,48),np.float32);mode=int(rng.integers(5))
    if mode<3:
        cv2.ellipse(a,(23,40),(int(rng.integers(8,14)),int(rng.integers(5,10))),-25,0,360,1,-1 if mode!=1 else 2)
        if mode==2:cv2.line(a,(34,40),(34,2),1,2)
    elif mode==3:cv2.line(a,(23,3),(23,60),1,int(rng.integers(1,4)))
    else:
        for _ in range(3):cv2.line(a,tuple(rng.integers(3,45,2)),tuple(rng.integers(3,45,2)),1,int(rng.integers(1,4)))
    return a


def dataset(directory,split):
    rng=np.random.default_rng(SEEDS[split]);names=TEST if split=='test' else TRAIN
    per,neg=COUNTS[split];samples=[];labels=[];groups=[]
    conditions=['clean','staff-removed','staff-raw','dropout']
    for index,kind in enumerate(LABELS[1:],1):
        glyphs=bank(directory,names,[CODES[kind]])
        if not glyphs:raise ValueError('Missing positive glyphs '+kind)
        for i in range(per):
            font,code,value=glyphs[int(rng.integers(len(glyphs)))];condition=conditions[i%4]
            samples.append(augment(value,rng,condition,kind));labels.append(index);groups.append(font+':'+condition)
    music=bank(directory,names,list(range(0xe0a0,0xe0ba))+list(range(0xe4e2,0xe4ec))+list(range(0xe050,0xe06a))+list(range(0xe880,0xe88a))+list(range(0xe520,0xe52d)))
    text=bank(directory,['NotoSans'],list(map(ord,'0123456789ABCDEFGHabcdefgmpfrsxyz#')))
    positive=bank(directory,names,list(CODES.values()))
    for i in range(neg):
        source=i%7;kind=None;negative_mode=None
        if source==0:value=primitive(rng);group='primitive'
        elif source in (1,2):
            choices=text if source==1 else music
            _,_,value=choices[int(rng.integers(len(choices)))];group='text' if source==1 else 'music'
        elif source in (3,4,5):
            _,code,value=positive[int(rng.integers(len(positive)))];kind=next(k for k,c in CODES.items() if c==code)
            negative_mode={3:'merged',4:'multi-glyph',5:'fragment'}[source];group=negative_mode
        else:value=primitive(rng);group='primitive'
        condition=conditions[i%4]
        samples.append(augment(value,rng,condition,kind,negative_mode));labels.append(0);groups.append('negative:'+group)
    x=np.asarray(samples,np.float32)[:,None];y=np.asarray(labels,np.int64)
    digest=hashlib.sha256(x.tobytes()+y.tobytes()+'\n'.join(groups).encode()).hexdigest()
    return x,y,groups,digest


def net_class():
    import torch
    class Net(torch.nn.Module):
        def __init__(self):
            super().__init__();self.conv1=torch.nn.Conv2d(1,8,3,padding=1);self.conv2=torch.nn.Conv2d(8,16,3,padding=1);self.fc1=torch.nn.Linear(768,32);self.fc2=torch.nn.Linear(32,len(LABELS))
        def forward(self,x):
            x=torch.nn.functional.max_pool2d(torch.relu(self.conv1(x)),2);x=torch.nn.functional.max_pool2d(torch.relu(self.conv2(x)),2)
            return self.fc2(torch.relu(self.fc1(x.flatten(1))))
    return Net


def accepted(logits,gates):
    order=np.argsort(logits,axis=1)[:,::-1];pred=order[:,0].copy();score=logits[np.arange(len(logits)),pred];margin=score-logits[np.arange(len(logits)),order[:,1]]
    for i,kind in enumerate(LABELS[1:],1):
        gate=gates[kind];pred[(pred==i)&((score<gate['score'])|(margin<gate['margin']))]=0
    return pred


def gates_from_dev(logits,y):
    result={}
    for i,kind in enumerate(LABELS[1:],1):
        best=None
        for score in (0,2,4,6,8,10):
            for margin in (.5,1,2,3,4,5,6,8,10):
                gates={k:{'score':score,'margin':margin} for k in LABELS[1:]};pred=accepted(logits,gates);chosen=pred==i
                tp=int(sum(chosen&(y==i)));fp=int(sum(chosen&(y!=i)))
                if sum(chosen&(y==0))>sum(y==0)*.001 or fp>max(1,tp*.005):continue
                objective=(tp,-fp,-score-margin)
                if best is None or objective>best[0]:best=(objective,gates[kind])
        result[kind]=best[1] if best else {'score':1e6,'margin':1e6}
    return result


def metrics(logits,y,groups,gates,digest):
    pred=accepted(logits,gates);matrix=np.zeros((len(LABELS),len(LABELS)),int)
    for a,b in zip(y,pred):matrix[a,b]+=1
    result={'data_sha256':digest,'samples':len(y),'labels':LABELS,'confusion':matrix.tolist(),
            'positive_recall':float(np.mean(pred[y!=0]==y[y!=0])),'negative_rejection':float(np.mean(pred[y==0]==0)),
            'accepted_precision':float(np.mean(pred[pred!=0]==y[pred!=0])) if sum(pred!=0) else None,'per_class':{},'groups':{}}
    for i,kind in enumerate(LABELS[1:],1):result['per_class'][kind]={'n':int(sum(y==i)),'recall':float(np.mean(pred[y==i]==i)),'precision':float(np.mean(y[pred==i]==i)) if sum(pred==i) else None}
    for group in sorted(set(groups)):
        mask=np.asarray(groups)==group;result['groups'][group]={'n':int(sum(mask)),'correct':int(sum(pred[mask]==y[mask])),'accepted_wrong':int(sum((pred[mask]!=0)&(pred[mask]!=y[mask])))}
    return result


def load_export():
    import torch
    model=json.loads((ROOT/'web/src/py/accidental_classifier.json').read_text());net=net_class()()
    net.load_state_dict({k:torch.from_numpy(np.frombuffer(base64.b64decode(v['data']),'<f2').astype(np.float32).reshape(v['shape'])) for k,v in model['weights'].items()});net.eval()
    return model,net


def logits_for(net,x):
    import torch
    with torch.no_grad():return torch.cat([net(b) for b in torch.from_numpy(x).split(512)]).numpy()


def train(args):
    import torch
    torch.set_num_threads(4);torch.manual_seed(906400);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    x,y,groups,digest=dataset(args.fonts,'train');dx,dy,dg,dd=dataset(args.fonts,'dev');np.savez_compressed(out/'dev.npz',x=dx,y=dy,groups=dg)
    net=net_class()();optimizer=torch.optim.AdamW(net.parameters(),lr=.0015,weight_decay=.0003)
    lossfn=torch.nn.CrossEntropyLoss(weight=torch.tensor([.65,1,1,1,1,1.]));loader=torch.utils.data.DataLoader(torch.utils.data.TensorDataset(torch.from_numpy(x),torch.from_numpy(y)),batch_size=256,shuffle=True)
    start=time.time();history=[]
    for epoch in range(args.epochs):
        net.train();losses=[]
        for bx,by in loader:
            optimizer.zero_grad();loss=lossfn(net(bx),by);loss.backward();optimizer.step();losses.append(float(loss))
        net.eval();logits=logits_for(net,dx);item={'epoch':epoch+1,'loss':float(np.mean(losses)),'dev_argmax_accuracy':float(np.mean(logits.argmax(1)==dy))};history.append(item);print(json.dumps(item),flush=True)
    gates=gates_from_dev(logits,dy)
    model={'format':'accidental-cnn-f16-v1','labels':LABELS,'gates':gates,'train_fonts':TRAIN,'held_font':TEST,'seeds':SEEDS,'train_data_sha256':digest,'dev_data_sha256':dd,'license':'OFL-1.1','weights':{}}
    for k,v in net.state_dict().items():
        a=v.numpy().astype('<f2');model['weights'][k]={'shape':list(a.shape),'data':base64.b64encode(a.tobytes()).decode()}
    path=ROOT/'web/src/py/accidental_classifier.json';path.write_text(json.dumps(model,separators=(',',':'))+'\n')
    model,net=load_export();logits=logits_for(net,dx)
    result={'model_sha256':sha(path),'model_bytes':path.stat().st_size,'train_data_sha256':digest,'dev_data_sha256':dd,'train_seed':906400,'split_seeds':SEEDS,'epochs':args.epochs,'seconds':time.time()-start,'history':history,'gates':gates,'test_accessed':False,'dev':metrics(logits,dy,dg,gates,dd)}
    (out/'freeze.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


def test(args):
    import torch
    torch.set_num_threads(4);out=Path(args.out);receipt=json.loads((out/'freeze.json').read_text());path=ROOT/'web/src/py/accidental_classifier.json'
    if sha(path)!=receipt['model_sha256']:raise ValueError('Model changed after freeze')
    model,net=load_export();x,y,groups,digest=dataset(args.fonts,'test');logits=logits_for(net,x)
    result={'model_sha256':sha(path),'test_font_sha256':sha(font_path(args.fonts,'Eugene')),'test':metrics(logits,y,groups,model['gates'],digest)}
    (out/'unseen-font-test.json').write_text(json.dumps(result,indent=2)+'\n');np.savez_compressed(out/'unseen-test.npz',x=x,y=y,groups=groups,logits=logits);print(json.dumps(result,indent=2))


def prepare(args):
    directory=Path(args.fonts);directory.mkdir(parents=True,exist_ok=True)
    for item in manifest():
        path=directory/item['filename']
        if not path.exists():
            with urllib.request.urlopen(item['url'],timeout=60) as response:path.write_bytes(response.read())
        if sha(path)!=item['sha256']:raise ValueError('Font hash mismatch '+item['name'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('mode',choices=['prepare','train','test']);parser.add_argument('--fonts',required=True);parser.add_argument('--out',required=True);parser.add_argument('--epochs',type=int,default=24)
    args=parser.parse_args();{'prepare':prepare,'train':train,'test':test}[args.mode](args)
