import cv2,numpy as np
from copy import deepcopy
from PIL import Image
import io,resvg_py
from native_contour_path import render_shape
def clean_quad(node,mask,min_iou=.985):
 x,y,w,h=cv2.boundingRect(mask);xx=np.arange(x,x+w);yt=[];yb=[]
 for q in xx:
  ys=np.where(mask[:,q]>0)[0];yt.append(ys.min());yb.append(ys.max()+1)
 pad=3;target=np.pad(mask[y:y+h,x:x+w]>0,pad);best=(-1,None)
 def curve(p,x0,x1):
  yy=np.polyval(p,[x0,x1]);der=np.polyval(np.polyder(p),[x0,x1]);le=x1-x0;return f'C{x0+le/3:.3f} {yy[0]+der[0]*le/3:.3f} {x1-le/3:.3f} {yy[1]-der[1]*le/3:.3f} {x1:.3f} {yy[1]:.3f}'
 for degree in [1,2,3]:
  top=np.polyfit(xx+.5-x,np.array(yt)-y,degree);bot=np.polyfit(xx+.5-x,np.array(yb)-y,degree)
  for dx in [-.5,-.25,0,.25,.5]:
   for dy in [-.5,-.25,0,.25,.5]:
    d=f'M0 {np.polyval(top,0):.3f}'+curve(top,0,w)+f'L{w} {np.polyval(bot,w):.3f}'+curve(bot,w,0)+'Z';e=deepcopy(node);e.update(left=x+dx,top=y+dy,width=w,height=h,viewBox=dict(left=0,top=0,width=w,height=h),paths=[dict(d=d,fill=node['paths'][0]['fill'])]);svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w+6}" height="{h+6}" viewBox="{x-pad} {y-pad} {w+6} {h+6}">{render_shape(e)}</svg>';r=np.array(Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert('RGBA'))[:,:,3]>=128;s=float((r&target).sum()/(r|target).sum())
    if s>best[0]:best=(s,e)
 if best[0]>=min_iou:return best[1],dict(mask_iou=best[0],method='whole_smooth_cubic_edges',path_bytes=len(best[1]['paths'][0]['d']))
 return node,dict(method='smooth_fit_rejected_geometry_gate',best_iou=best[0])
