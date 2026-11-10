from copy import deepcopy
import io
import cv2,numpy as np
from PIL import Image
import resvg_py
from native_contour_path import native_component,render_shape,_join_holes

def fill_holes(mask):
 p=np.pad((mask>0).astype('uint8'),1);cv2.floodFill(p,None,(0,0),2);return (p[1:-1,1:-1]!=2).astype('uint8')

def native_group(name,children):
 x=min(e['left']for e in children);y=min(e['top']for e in children);xx=max(e['left']+e['width']for e in children);yy=max(e['top']+e['height']for e in children)
 for e in children:e['left']-=x;e['top']-=y
 return dict(type='group',name=name,left=x,top=y,width=xx-x,height=yy-y,children=children)

def render_node(e,ox=0,oy=0):
 x=ox+e['left'];y=oy+e['top']
 if e['type']=='group':return ''.join(render_node(c,x,y)for c in e['children'])
 return f'<g transform="translate({x} {y})">'+''.join(f'<path d="{p["d"]}" fill="{p["fill"]["color"]}"/>'for p in e['paths'])+'</g>'

class ComponentBuilder:
 def __init__(self,source):self.im=np.asarray(source);self.audit=[]
 def color(self,mask):
  interior=cv2.erode((mask>0).astype('uint8'),np.ones((3,3),np.uint8))>0
  if not interior.any():interior=mask>0
  return '#%02x%02x%02x'%tuple(np.rint(np.median(self.im[interior],axis=0)).astype(int))
 def node(self,mask,name,color=None,fill_ink_holes=False):
  original=(mask>0).astype('uint8');mask=fill_holes(original)if fill_ink_holes else original;color=color or self.color(original);node,meta=native_component(mask,color,name);x,y,w,h=cv2.boundingRect(mask);pad=3;target=np.pad(mask[y:y+h,x:x+w]>0,pad)
  def score(e):
   svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w+6}" height="{h+6}" viewBox="{x-pad} {y-pad} {w+6} {h+6}">{render_shape(e)}</svg>';r=np.array(Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert('RGBA'))[:,:,3]>=128;return float((r&target).sum()/(r|target).sum())
  best=(-1,None);ox,oy=node['left'],node['top']
  for dx in np.arange(-.5,.501,.125):
   for dy in np.arange(-.5,.501,.125):
    node['left']=ox+float(dx);node['top']=oy+float(dy);s=score(node)
    if s>best[0]:best=(s,deepcopy(node))
  node=best[1]
  if best[0]<.985:
   local=mask[y:y+h,x:x+w]
   for scale in [2,4,8]:
    high=cv2.resize(local,(w*scale,h*scale),interpolation=cv2.INTER_NEAREST)
    cs,hierarchy=cv2.findContours(high,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:continue
    roots=[i for i,v in enumerate(hierarchy[0])if v[3]<0]
    if len(roots)!=1:continue
    root=roots[0];hole_ids=[];child=hierarchy[0][root][2]
    while child>=0:
     hole_ids.append(child);child=hierarchy[0][child][0]
    for eps in [0,.15,.3,.5,.7,1]:
     outer=cv2.approxPolyDP(cs[root],eps*scale,True).reshape(-1,2)
     holes=[cv2.approxPolyDP(cs[i],eps*scale,True).reshape(-1,2)for i in hole_ids]
     pts=_join_holes(outer,holes,high)/scale+.5/scale
     num=lambda z:f'{z:.3f}'.rstrip('0').rstrip('.')if z!=int(z)else str(int(z));d='M'+' '.join(map(num,pts[0]))+'l'+' '.join(' '.join(map(num,p))for p in np.diff(pts,axis=0))+'Z'
     if len(d.encode())>1850:continue
     for dx in [-.125,0,.125]:
      for dy in [-.125,0,.125]:
       candidate=dict(type='shape',name=name,left=x+dx,top=y+dy,width=w,height=h,viewBox=dict(left=0,top=0,width=w,height=h),paths=[dict(d=d,fill=dict(color=color))]);s=score(candidate)
       if s>best[0]:best=(s,candidate);node=candidate;meta.update(path_bytes=len(d.encode()),epsilon=eps,sampling=scale)
  meta.update(name=name,source_bbox=[x,y,w,h],color=color,mask_iou=best[0],local_geometry_gate='PASS'if best[0]>=.985 else 'FAIL_REQUIRES_ALIGNMENT',printed_ink_holes_filled_in_body=fill_ink_holes,body_tiling=False);self.audit.append(meta);return node
