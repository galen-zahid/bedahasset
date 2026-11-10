"""Compact, single-move native paths for whole source components with holes.

Uses the current pipeline's contour approximation. Zero-width bridges preserve
opposite winding, so holes stay transparent without background-colored patches.
Every bridge is checked against the original component before it is emitted.
"""
import cv2
import numpy as np

def _compact_path(points):
    points=np.asarray(points,dtype=int)
    first=points[0]
    delta=np.diff(points,axis=0)
    return f'M{first[0]} {first[1]}l'+ ' '.join(f'{x} {y}' for x,y in delta)+'Z'

def _visible_bridge(a,b,mask):
    count=max(abs(int(a[0])-int(b[0])),abs(int(a[1])-int(b[1])))+1
    samples=np.rint(np.linspace(a,b,max(2,count))).astype(int)
    return bool(np.all(mask[samples[:,1],samples[:,0]]>0))

def _join_holes(outer,holes,mask):
    walk=[tuple(map(int,p)) for p in outer]
    for hole in holes:
        distances=((outer[:,None,:].astype(float)-hole[None,:,:])**2).sum(2)
        choice=None
        for flat in np.argsort(distances,axis=None):
            oi,hi=np.unravel_index(flat,distances.shape)
            if _visible_bridge(outer[oi],hole[hi],mask):
                choice=(oi,hi);break
        if choice is None:raise ValueError('No visible bridge for a contour hole')
        oi,hi=choice;anchor=tuple(map(int,outer[oi]));position=walk.index(anchor)
        loop=[tuple(map(int,p)) for p in np.concatenate([hole[hi:],hole[:hi]],axis=0)]
        walk=walk[:position+1]+loop+[loop[0],anchor]+walk[position+1:]
    return np.array(walk,dtype=int)

def native_component(mask,color,name,max_bytes=1850):
    mask=(mask>0).astype('uint8')
    # OpenCV contours run through boundary pixel centers. Extending their right
    # and bottom edges by one pixel converts those centers to SVG pixel-cell
    # boundaries; it prevents a half-pixel loss on both sides of thin strokes.
    mask=cv2.dilate(mask,np.ones((2,2),np.uint8))
    contours,hierarchy=cv2.findContours(mask,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:raise ValueError('Empty component')
    roots=[i for i,h in enumerate(hierarchy[0]) if h[3]<0]
    if len(roots)!=1:raise ValueError('Expected one whole connected component')
    root=roots[0];hole_ids=[];child=hierarchy[0][root][2]
    while child>=0:
        hole_ids.append(child);child=hierarchy[0][child][0]
    for eps in [.05,.15,.25,.35,.45,.55,.7,.85,1.,1.2,1.5]:
        outer=cv2.approxPolyDP(contours[root],eps,True).reshape(-1,2)
        holes=[cv2.approxPolyDP(contours[i],eps,True).reshape(-1,2) for i in hole_ids]
        walk=_join_holes(outer,holes,mask)
        x,y,ww,hh=cv2.boundingRect(contours[root]);width=ww-1;height=hh-1
        if width<=0 or height<=0:raise ValueError('Degenerate component')
        path=_compact_path(walk-[x,y])
        if len(path.encode())<=max_bytes:break
    else:raise ValueError(f'Whole component still exceeds {max_bytes} bytes at 1.5px: {name}')
    node=dict(type='shape',name=name,left=x,top=y,width=width,height=height,
              viewBox=dict(left=0,top=0,width=width,height=height),
              paths=[dict(d=path,fill=dict(color=color))])
    meta=dict(path_bytes=len(path.encode()),points=len(walk),holes=len(holes),
              epsilon=eps,single_move=True,body_tiling=False,background_counterfill=False)
    return node,meta

def render_shape(node):
    return f'<g transform="translate({node["left"]} {node["top"]})">'+''.join(
        f'<path d="{p["d"]}" fill="{p["fill"]["color"]}"/>' for p in node['paths'])+'</g>'
