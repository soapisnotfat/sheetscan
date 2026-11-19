"""Experimental source-only notehead/stem/beam geometry; no rhythm edits.

A beam count is evidence about written flags, not a complete timing decision.
This module does not read a score, expected pitches, meter or a filename.
"""
import cv2
import numpy as np


def _staffs(grids):
    result=[]
    for staff in grids:
        grid=staff['grid'];xs=np.asarray([p['x'] for p in grid],float)
        for k in range(0,len(grid[0]['y'])-4,5):
            ys=np.asarray([p['y'][k:k+5] for p in grid],float)
            result.append({'x':xs,'y':ys,'unit':float(np.median(np.diff(ys,axis=1)))})
    return result


def _core(staff,x):
    return [float(np.interp(x,staff['x'],staff['y'][:,k])) for k in range(5)]


def _connection(ink,a,b,staff):
    unit=staff['unit']
    if a['direction']!=b['direction'] or not .8*unit < b['x']-a['x'] < 9*unit:
        return None
    if abs(a['tip']-b['tip'])>1.8*unit:return None
    xs=np.arange(round(a['x']+.2*unit),round(b['x']-.2*unit)+1)
    if len(xs)<5:return None
    baseline=a['tip']+(b['tip']-a['tip'])*(xs-a['x'])/(b['x']-a['x'])
    direction=1 if a['direction']=='up' else -1
    offsets=np.arange(0,round(1.45*unit)+1)
    coverage=[]
    for offset in offsets:
        ys=np.rint(baseline+direction*offset).astype(int)
        valid=(xs>=0)&(xs<ink.shape[1])&(ys>0)&(ys<ink.shape[0]-1)
        if not valid.all():return None
        coverage.append(float(ink[ys,xs].mean()))
    bands=[];start=None
    for i,present in enumerate([v>=.78 for v in coverage]+[False]):
        if present and start is None:start=i
        if not present and start is not None:
            bands.append((start,i-1));start=None
    # A long staff line crossing the stem gap can otherwise act as an extra
    # beam. Record uncertainty instead of guessing the written flag count.
    beams=[]
    for low,high in bands:
        midpoint=(low+high)/2;ys=baseline+direction*midpoint
        hits=sum(min(abs(y-line) for line in _core(staff,x))<.13*unit for x,y in zip(xs,ys))/len(xs)
        if not (hits>.7 and high-low+1<.4*unit):beams.append((low,high))
    if not beams or beams[0][0]>.3*unit or len(beams)>3:return None
    return {'count':len(beams),'from':[a['x'],a['tip']],'to':[b['x'],b['tip']],
            'bands':[list(v) for v in beams],'coverage':[round(v,3) for v in coverage]}


def _split_tall_head(ink, head, unit):
    """Separate filled head lobes inside one tall segmentation candidate.

    Only source ink is used: long staff lines and stems are removed, horizontal
    ink profiles must contain two or three separated lobes. No decoded pitch or
    expected head count enters this operation.
    """
    x, y = head['center']
    width, height = head['size']
    if not (1.6*unit <= height <= 3.8*unit and .5*unit <= width <= 2*unit):
        return [head]
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                                 np.ones((1, max(12, round(8*unit))), np.uint8))
    vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                               np.ones((max(3, round(1.6*unit))|1, 1), np.uint8))
    clean = ink & (1-horizontal) & (1-vertical)
    left, right = max(0, round(x-width*.6)), min(ink.shape[1], round(x+width*.6)+1)
    top, bottom = max(0, round(y-height*.55)), min(ink.shape[0], round(y+height*.55)+1)
    crop = clean[top:bottom, left:right]
    if not crop.size:
        return [head]
    profile = np.convolve(crop.sum(axis=1).astype(float), [.2,.6,.2], mode='same')
    possible = [i for i in range(1,len(profile)-1)
                if profile[i] >= .4*unit and profile[i] >= profile[i-1]
                and profile[i] >= profile[i+1]]
    peaks = []
    for candidate in sorted(possible, key=lambda i: -profile[i]):
        if all(abs(candidate-old) >= .65*unit for old in peaks):
            peaks.append(candidate)
    peaks.sort()
    if not 2 <= len(peaks) <= 3:
        return [head]
    result = []
    for j, peak in enumerate(peaks):
        a = round((peaks[j-1]+peak)/2)+1 if j else 0
        b = round((peak+peaks[j+1])/2)+1 if j+1<len(peaks) else len(profile)
        local = crop[a:b]
        yy, xx = np.nonzero(local)
        if not len(xx):
            return [head]
        a0, b0, a1, b1 = int(xx.min()), int(yy.min()), int(xx.max())+1, int(yy.max())+1
        w, h = a1-a0, b1-b0
        density = len(xx)/(w*h)
        if not (.5*unit <= w <= 2.2*unit and .3*unit <= h <= 1.3*unit and density >= .35):
            return [head]
        result.append({'center': [float(left+xx.mean()), float(top+a+yy.mean())],
                       'size': [float(w),float(h)], 'angle': 0,
                       'splitFrom': head, 'sourceInkFraction': float(density),
                       'sourceProfilePeak': top+peak})
    return result


def read_beam_groups(image,staff_grids,raw_heads):
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY) if image.ndim==3 else image
    ink=(gray<160).astype(np.uint8);staffs=_staffs(staff_grids);assigned=[[] for _ in staffs]
    for head in raw_heads:
        x,y=map(float,head['center']);distances=[]
        for i,staff in enumerate(staffs):
            lines=_core(staff,x);distances.append((max(lines[0]-y,y-lines[-1],0),i))
        if not distances:continue
        distances.sort();distance,si=distances[0];s=staffs[si];u=s['unit']
        if (distance>7*u or len(distances)>1 and distances[1][0]-distance<=.5*u
                or not s['x'].min()-u<x<s['x'].max()+u):continue
        for head in _split_tall_head(ink, head, u):
            x,y=head['center'];w,h=head['size']
            if not (.3*u<h<1.7*u and .4*u<w<2.2*u):continue
            a=max(0,round(y-.4*h));b=min(len(ink),round(y+.4*h)+1)
            left=max(0,round(x-.4*w));right=min(ink.shape[1],round(x+.4*w)+1)
            support=ink[a:b,left:right]
            if not support.size or support.mean()<.35:continue
            lines=_core(s,x);refined=[]
            for line in lines:
                a=max(0,round(line-.3*u));b=min(len(ink),round(line+.3*u)+1)
                left=max(0,round(x-2*u));right=min(ink.shape[1],round(x+2*u)+1)
                profile=ink[a:b,left:right].mean(axis=1)
                if len(profile) and profile.max()>=.65:
                    refined.append(float(a+np.flatnonzero(profile>=.9*profile.max()).mean()))
                else:refined.append(line)
            refined_unit=float(np.median(np.diff(refined)))
            position=(refined[-1]-y)*2/refined_unit
            assigned[si].append({**head,'staffPosition':round(position),
                                 'positionResidual':abs(position-round(position))})
    result=[]
    for si,(s,heads) in enumerate(zip(staffs,assigned)):
        u=s['unit'];vertical=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((max(3,round(1.6*u))|1,1),np.uint8))
        _,_,stats,_=cv2.connectedComponentsWithStats(vertical)
        by_component={}
        for head in sorted(heads,key=lambda h:h['center'][0]):
            x,y=head['center'];found=[]
            for index,(a,b,w,h,area) in enumerate(stats[1:],1):
                cx=a+(w-1)/2
                if w>.45*u or not 1.7*u<=h<=9*u or abs(cx-x)>.9*u or not b-.6*u<=y<=b+h+.6*u:continue
                found.append((index,a,b,w,h,cx))
            # A merged chord can itself survive vertical opening. Keep all
            # candidates until their extension beyond the whole chord is
            # checked; an internal head bridge is not a second stem.
            for item in found:
                by_component.setdefault(item,[]).append(head)
        stems=[]
        for (index,a,b,w,h,cx),chord_heads in by_component.items():
            low=min(head['center'][1] for head in chord_heads)
            high=max(head['center'][1] for head in chord_heads)
            if b<low-1.5*u and b+h<high+u:direction,tip='up',b
            elif b+h>high+1.5*u and b>low-u:direction,tip='down',b+h-1
            else:continue
            stems.append({'component':index,'x':float(cx),'tip':float(tip),'direction':direction,
                          'heads':chord_heads,'stemBox':[int(a),int(b),int(a+w),int(b+h)]})
        memberships={}
        for stem in stems:
            for head in stem['heads']:
                memberships[id(head)]=memberships.get(id(head),0)+1
        stems=[stem for stem in stems if all(memberships[id(head)]==1 for head in stem['heads'])]
        stems.sort(key=lambda s:s['x'])
        pending=[];connections=[]
        for a,b in zip(stems,stems[1:]):
            edge=_connection(ink,a,b,s)
            if edge and (not connections or edge['count']==connections[-1]['count']):
                if not pending:pending=[a]
                pending.append(b);connections.append(edge)
            else:
                if connections:result.append({'staff':si,'heads':[head for stem in pending for head in stem['heads']],'eventCount':len(pending),'stems':pending,'beamCount':connections[0]['count'],'connections':connections})
                pending,connections=[],[]
                if edge:pending,connections=[a,b],[edge]
        if connections:result.append({'staff':si,'heads':[head for stem in pending for head in stem['heads']],'eventCount':len(pending),'stems':pending,'beamCount':connections[0]['count'],'connections':connections})
    return result
