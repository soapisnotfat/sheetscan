"""Printed meters, forward repeats and source-only multirest geometry.

The static glyph raster data is generated from the OFL-1.1 Bravura font:
https://github.com/steinbergmedia/bravura (license in web/public/Bravura-LICENSE.txt).
No PIL, font installation, filenames, measure indices or reference score needed at runtime.
Similarity scores are not calibrated probabilities. Unsupported/ambiguous marks are left alone.
"""
import base64
import json
import zlib
import cv2
import numpy as np

_GLYPH_DATA = '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'
_TEMPLATES = None


def _templates():
    global _TEMPLATES
    if _TEMPLATES is not None:
        return _TEMPLATES
    encoded = json.loads(zlib.decompress(base64.b64decode(_GLYPH_DATA)))
    glyphs = {int(k): np.frombuffer(base64.b64decode(v['bytes']), np.uint8)
              .reshape(v['shape']).astype(np.float32) / 255 for k,v in encoded.items()}
    variants=[]
    for num in range(2,10):
        for den in (2,4,8):
            for scale in (.8,.9,1.,1.1):
                pair=[]
                for digit in (num,den):
                    g=glyphs[digit]
                    pair.append(cv2.resize(g,(round(g.shape[1]/g.shape[0]*31*scale),31),interpolation=cv2.INTER_AREA))
                w=max(g.shape[1] for g in pair)+6
                template=np.zeros((64,w),np.float32)
                for top,g in zip((0,33),pair):
                    left=(w-g.shape[1])//2
                    template[top:top+31,left:left+g.shape[1]]=g
                mask=np.ones_like(template)
                for row in (0,16,32,48,63):
                    mask[max(0,row-2):min(64,row+3)]=0
                variants.append((num,den,template,mask))
    _TEMPLATES=variants
    return variants


def read_meters(image,boxes):
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY) if image.ndim==3 else image
    found=[]
    for staff_index,(left,top,right,bottom,*_) in enumerate(boxes):
        h=bottom-top+1
        if right-left<h*2 or top<0 or bottom>=gray.shape[0]:
            continue
        strip=(255-gray[top:bottom+1,max(0,left):right]).astype(np.float32)/255
        scale=64/h
        strip=cv2.resize(strip,(round(strip.shape[1]*scale),64))
        classes={}
        for num,den,template,mask in _templates():
            if template.shape[1]>strip.shape[1]:
                continue
            response=cv2.matchTemplate(strip,template,cv2.TM_CCORR_NORMED,mask=mask)[0]
            response=np.nan_to_num(response,nan=0,posinf=0,neginf=0)
            padded=np.zeros(strip.shape[1],np.float32)
            middle=template.shape[1]//2
            padded[middle:middle+len(response)]=response
            key=(num,den)
            classes[key]=np.maximum(classes.get(key,np.zeros_like(padded)),padded)
        if not classes:
            continue
        keys=list(classes);values=np.stack([classes[k] for k in keys])
        winner=values.argmax(axis=0);best=values.max(axis=0)
        while best.max()>=.82:
            x=int(best.argmax());which=int(winner[x]);num,den=keys[which]
            ranked=np.sort(values[:,x]);margin=float(ranked[-1]-ranked[-2])
            if margin>=.04:
                found.append({'staff':staff_index,'x':round(left+x/scale,2),
                    'numerator':num,'denominator':den,'templateScore':round(float(best[x]),4),
                    'margin':round(margin,4)})
            best[max(0,x-35):x+36]=0
    return found


def rest_number_box(image,box,point):
    """Locate a thick multirest bar near the model's attention, then its number above.

    Returns a source-image crop rectangle. The recognizer may read that crop using
    an optional local digit-OCR callback; the browser can use its existing Tesseract worker.
    """
    # A model may emit an ordinary whole-rest token for an old-style longa.
    # Source regions are therefore detected independently of decoder class.
    regions=read_multirest_regions(image,[box])
    choices=[]
    unit=(box[3]-box[1])/4
    for region in regions:
        left,top,right,bottom=region['shapeBox']
        distance=max(left-point[0],point[0]-right,0)+abs((top+bottom)/2-point[1])
        choices.append((distance,region['numberBox']))
    if choices and min(choices,key=lambda item:item[0])[0] <= 5*unit:
        return min(choices,key=lambda item:item[0])[1]
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY) if image.ndim==3 else image
    left,top,right,bottom,*_=box;unit=(bottom-top)/4
    if unit<=0:
        return None
    y0=max(0,round(top-unit));y1=min(gray.shape[0],round(bottom+unit))
    x0=max(0,left);x1=min(gray.shape[1],right)
    region=(gray[y0:y1,x0:x1]<150).astype(np.uint8)*255
    thick=cv2.erode(region,np.ones((max(2,round(unit*.25)),1),np.uint8))
    bars=cv2.morphologyEx(thick,cv2.MORPH_OPEN,np.ones((1,max(5,round(unit*3))),np.uint8))
    contours,_=cv2.findContours(bars,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    choices=[]
    for contour in contours:
        bx,by,w,h=cv2.boundingRect(contour);bx+=x0;by+=y0
        if w<unit*3 or not top-unit/2<=by+h/2<=bottom+unit/2:
            continue
        distance=max(bx-point[0],point[0]-(bx+w),0)+abs(by+h/2-point[1])
        choices.append((distance,bx,by,w,h))
    if not choices:
        return None
    distance,bx,by,w,h=min(choices)
    if distance>unit*5:
        return None
    center=bx+w/2
    return [max(0,round(center-3*unit)),max(0,round(top-3.4*unit)),
            min(gray.shape[1],round(center+3*unit)),max(0,round(top-.12*unit))]


def _rest_number_groups(gray,left,top,right,unit):
    """Untyped, tight above-staff ink groups; downstream OCR validates digits."""
    y0=max(0,round(top-4*unit));y1=max(0,min(len(gray),round(top-.15*unit)))
    x0=max(0,round(left));x1=min(gray.shape[1],round(right))
    if y1<=y0 or x1<=x0:
        return []
    ink=(gray[y0:y1,x0:x1]<160).astype(np.uint8)
    _,_,stats,_=cv2.connectedComponentsWithStats(ink)
    glyphs=sorted([(x0+int(x),y0+int(y),int(w),int(h)) for x,y,w,h,a in stats[1:]
                   if .65*unit<=h<=2.9*unit and .12*unit<=w<=2.5*unit
                   and y+h<=ink.shape[0]-2
                   and .12<=a/(w*h)<=.95],key=lambda item:item[0])
    groups=[]
    for x,y,w,h in glyphs:
        if groups:
            a,b,c,d=groups[-1]
            if -.15*unit<=x-c<=1.1*unit and abs((y+h/2)-(b+d)/2)<=.45*unit:
                groups[-1]=[min(a,x),min(b,y),max(c,x+w),max(d,y+h)]
                continue
        groups.append([x,y,x+w,y+h])
    return [box for box in groups if box[2]-box[0]<=6.3*unit]


def read_multirest_regions(image,staff_boxes):
    """Locate H and old-style symbol multirests from source ink alone.

    Returns original-pixel staff/style/shapeBox/numberBox evidence. A source
    number is required; no count, pitch, model token, filename, measure index or
    expected bar total is used. Counts are deliberately left to existing OCR.
    A lone ordinary whole rest is not a symbolic-multirest shape. The caller
    must bind a unique region to score rest(s), check count and musical context,
    and split expansion at key/time/clef boundaries. This function changes no XML.
    """
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY) if image.ndim==3 else image
    result=[]
    for staff,(left,top,right,bottom,*_) in enumerate(staff_boxes):
        unit=(bottom-top)/4
        if unit<3 or right-left<3*unit:
            continue
        x0,x1=max(0,round(left)),min(gray.shape[1],round(right))
        y0,y1=max(0,round(top-.3*unit)),min(len(gray),round(bottom+.3*unit))
        ink=(gray[y0:y1,x0:x1]<160).astype(np.uint8)
        if not ink.size:
            continue
        shapes=[]
        # H bars survive vertical erosion; the five thin staff lines do not.
        thick=cv2.erode(ink,np.ones((max(3,round(unit*.25)),1),np.uint8))
        bars=cv2.morphologyEx(thick,cv2.MORPH_OPEN,np.ones((1,max(5,round(unit*3))),np.uint8))
        _,_,stats,_=cv2.connectedComponentsWithStats(bars)
        vertical=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((max(3,round(1.5*unit)),1),np.uint8))
        for x,y,w,h,a in stats[1:]:
            cy=y0+y+h/2
            if not (w>=3*unit and .25*unit<=h<=1.35*unit and abs(cy-(top+2*unit))<=.55*unit):
                continue
            # Parallel secondary beams plus their note stems can otherwise look
            # like H caps. A genuine multirest has one thick horizontal body.
            parallel=any(ow>=3*unit and .3*unit<=abs((y+h/2)-(oy+oh/2))<=1.5*unit
                         and min(x+w,ox+ow)-max(x,ox)>=.75*min(w,ow)
                         for ox,oy,ow,oh,oa in stats[1:])
            if parallel:
                continue
            caps=[]
            for endpoint in (x,x+w-1):
                a0=max(0,round(endpoint-.3*unit));a1=min(ink.shape[1],round(endpoint+.3*unit)+1)
                strip=vertical[:,a0:a1]
                ys=np.flatnonzero(strip.any(axis=1)) if strip.size else np.array([])
                caps.append(bool(len(ys) and y0+ys[0]<=cy-.65*unit and y0+ys[-1]>=cy+.65*unit))
            if all(caps):
                inner=vertical[:,max(0,round(x+unit)):min(ink.shape[1],round(x+w-unit))]
                # A beamed note group has interior stems; an H rest does not.
                if inner.size and np.count_nonzero(inner.any(axis=0))>max(2,.4*unit):
                    continue
                shapes.append({'style':'H','box':[x0+int(x),round(cy-unit),x0+int(x+w),round(cy+unit)]})
        # Remove complete staff lines before finding narrow symbolic slabs.
        horizontal=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,max(12,round(unit*7))),np.uint8))
        clean=cv2.morphologyEx(ink-horizontal,cv2.MORPH_CLOSE,np.ones((3,1),np.uint8))
        # Anti-aliased staff edges can leave one-pixel horizontal bridges
        # between neighboring symbolic slabs; remove those before components.
        clean=cv2.morphologyEx(clean,cv2.MORPH_OPEN,np.ones((max(3,round(.16*unit))|1,1),np.uint8))
        _,_,stats,_=cv2.connectedComponentsWithStats(clean)
        symbols=[];whole_parts=[]
        for x,y,w,h,a in stats[1:]:
            box=[x0+int(x),y0+int(y),x0+int(x+w),y0+int(y+h)]
            cx,cy=(box[0]+box[2])/2,(box[1]+box[3])/2
            if any(s['style']=='H' and s['box'][0]-.3*unit<=cx<=s['box'][2]+.3*unit for s in shapes):
                continue
            fill=a/(w*h);style=None
            if .24*unit<=w<=.95*unit and fill>=.72:
                if 1.6*unit<=h<=2.4*unit and abs(cy-(top+2*unit))<=.4*unit:style='longa'
                elif .75*unit<=h<=1.35*unit and abs(cy-(top+1.5*unit))<=.3*unit:style='breve'
            if style is None and abs(cy-(top+2*unit))<=.5*unit and 1.05*unit<=w<=2.1*unit and 1.6*unit<=h<=2.4*unit and fill>=.45:
                # Maxima is two connected longa columns, not a full barline.
                slab=clean[y:y+h,x:x+w]
                dense=(slab.mean(axis=0)>=.75).astype(np.uint8)
                runs=np.diff(np.pad(dense,(1,1)).astype(int))
                if sum(runs==1)==2:style='maxima'
            if style is not None:symbols.append({'style':style,'box':box})
            elif .75*unit<=w<=1.8*unit and .25*unit<=h<=.75*unit and fill>=.72 and top+.8*unit<=cy<=top+1.7*unit:
                whole_parts.append({'style':'whole-part','box':box})
        # Number-first grouping can cover multiple old-style rest glyphs. Keep
        # individual contours until one above-number has selected its range.
        groups=_rest_number_groups(gray,left,top,right,unit)
        for number in groups:
            nx=(number[0]+number[2])/2
            matches=[]
            for shape in shapes+symbols:
                a,b,c,d=shape['box'];sx=(a+c)/2
                allowance=max((.65 if shape['style']=='H' else 1.8)*unit,(c-a)/2)
                if abs(nx-sx)<=allowance and top-number[3]>=.12*unit:
                    matches.append((abs(nx-sx),shape))
            if not matches:
                continue
            _,best=min(matches,key=lambda item:item[0])
            # Adjacent symbolic glyphs may encode 3/5/etc. Include only compact,
            # aligned slabs, never cross a clef/key/time signature or barline.
            selected=[best]
            if best['style']!='H':
                for other in symbols+whole_parts:
                    if other is best:continue
                    ax,bx=best['box'][0],best['box'][2];a,b,c,d=other['box']
                    gap=max(a-bx,ax-c,0)
                    if gap<=1.5*unit and abs((a+c)/2-nx)<=2.4*unit:
                        selected.append(other)
            a=min(s['box'][0] for s in selected);b=min(s['box'][1] for s in selected)
            c=max(s['box'][2] for s in selected);d=max(s['box'][3] for s in selected)
            # A count must be centered over its selected shape/group.
            if abs(nx-(a+c)/2)>max(.8*unit,.28*(c-a)):
                continue
            pad=max(2,round(.18*unit))
            number_box=[max(0,number[0]-pad),max(0,number[1]-pad),min(gray.shape[1],number[2]+pad),min(len(gray),number[3]+pad)]
            result.append({'staff':staff,'style':best['style'] if len(selected)==1 else 'symbols',
                           'shapeBox':[a,b,c,d],'numberBox':number_box,
                           'center':[round((a+c)/2,2),round((b+d)/2,2)],'evidence':'shape-and-above-number'})
    return sorted(result,key=lambda item:(item['staff'],item['shapeBox'][0]))


def read_forward_repeats(image, boxes):
    """Require two full-height bars (thick then thin) and two aligned round dots.

    This reads geometry, not repertoire or expected repeat counts. A single
    barline, double bar, notehead or pair of staccatos alone is insufficient.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    found = []
    for staff, (left, top, right, bottom, *_) in enumerate(boxes):
        unit = (bottom-top)/4
        if unit < 3:
            continue
        ink = (gray[top:bottom+1, left:right+1] < 150).astype(np.uint8)
        vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((round(3.7*unit), 1), np.uint8))
        _, _, stats, _ = cv2.connectedComponentsWithStats(vertical)
        bars = sorted([(int(x), int(w)) for x, y, w, h, area in stats[1:]
                       if h >= 3.6*unit and w <= unit], key=lambda item: item[0])
        horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, max(12, round(unit*8))), np.uint8))
        _, _, shapes, centers = cv2.connectedComponentsWithStats(ink-horizontal)
        dots = [(float(point[0]), float(point[1])) for (x, y, w, h, area), point in zip(shapes[1:], centers[1:])
                if .25*unit <= w <= .65*unit and .25*unit <= h <= .65*unit
                and .65 <= w/h <= 1.5 and .5 <= area/(w*h) <= .95]
        for (thick, tw), (thin, nw) in zip(bars, bars[1:]):
            if not (.3*unit <= tw <= .85*unit and nw <= .25*unit and tw >= 2*nw
                    and .15*unit <= thin-(thick+tw) <= .8*unit):
                continue
            upper = [p for p in dots if thin+nw+.1*unit <= p[0] <= thin+nw+1.2*unit and abs(p[1]-1.5*unit) <= .2*unit]
            lower = [p for p in dots if thin+nw+.1*unit <= p[0] <= thin+nw+1.2*unit and abs(p[1]-2.5*unit) <= .2*unit]
            pairs = [(a, b) for a in upper for b in lower if abs(a[0]-b[0]) <= .2*unit]
            if len(pairs) == 1:
                a, b = pairs[0]
                found.append({'staff': staff, 'x': round(left+(a[0]+b[0])/2, 2),
                              'kind': 'forward-repeat', 'bars': [left+thick, left+thin+nw],
                              'dots': [[round(left+p[0], 2), round(top+p[1], 2)] for p in (a, b)]})
    return found
