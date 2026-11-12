"""Mesin Scene Codex, DISALIN dari VECTALLY_CODEX_TOOLKIT_20261112/engine/vector_batch.py.

Perubahan: folder hasil/sumber relatif ke vectally/, mode ink 'purple'. Logika lain tidak diubah.
"""
from pathlib import Path
import math,re,json,io,gzip
import numpy as np,cv2
from PIL import Image,ImageDraw
import resvg_py

ROOT=Path(__file__).resolve().parents[1]/'outputs'/'VECTALLY-resep'
SRC=Path(__file__).resolve().parents[1]/'sources'/'VECTALLY'/'Feed'
W,H=1122,1402
N='#091522';G='#00dfa0';P='#b18afa';WH='#f8f9fc';L='#e5d9fc'
def path(d,c):return dict(d=d.strip(),color=c)
def poly(ps,c):return path('M'+' L'.join(f'{x:g} {y:g}' for x,y in ps)+' Z',c)
def rect(x,y,w,h,c):return poly([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],c)
def ellipse(x,y,rx,ry,c,angle=0):
 t=math.radians(angle);co,si=math.cos(t),math.sin(t)
 return poly([(x+rx*math.cos(a)*co-ry*math.sin(a)*si,y+rx*math.cos(a)*si+ry*math.sin(a)*co) for a in np.linspace(0,math.tau,64,endpoint=False)],c)
def roundrect(x,y,w,h,r,c):
 k=r*.55228475
 return path(f'M{x+r} {y} L{x+w-r} {y} C{x+w-r+k} {y} {x+w} {y+r-k} {x+w} {y+r} L{x+w} {y+h-r} C{x+w} {y+h-r+k} {x+w-r+k} {y+h} {x+w-r} {y+h} L{x+r} {y+h} C{x+r-k} {y+h} {x} {y+h-r+k} {x} {y+h-r} L{x} {y+r} C{x} {y+r-k} {x+r-k} {y} {x+r} {y} Z',c)
def ribbon_line(d,c,width):
 # Closed stroke outlines are authored in the call sites; this helper is unused
 # by the Canva package, which contains fills only.
 return path(d,c)

class Scene:
 def __init__(self,code,filename,bg):
  self.code=code;self.filename=filename;self.bg=bg;self.rgb=np.array(Image.open(SRC/filename).convert('RGB'));self.assets=[]
  self.add('BG','Latar','background',[rect(0,0,W,H,bg)],'Satu warna flat; tekstur/gradasi sumber tidak disalin.')
 def add(self,id,name,kind,parts,note='',body=0):
  if not parts:raise ValueError(f'Empty asset {id}')
  self.assets.append(dict(id=id,name=name,kind=kind,parts=parts,note=note,body_part=body))
 def ink(self,box,c,mode='dark',hole=None,polygons=None,minarea=1.2):
  x0,y0,x1,y1=box;im=self.rgb[y0:y1,x0:x1]
  if mode=='dark':m=im.max(2)<125
  elif mode=='white':m=im.min(2)>175
  elif mode=='purple':m=(im[:,:,2]>150)&(im[:,:,2].astype(int)>im[:,:,1].astype(int)+40)&(im[:,:,0]>60)&(im[:,:,0]<215)
  elif mode=='green':m=(im[:,:,1]>45)&(im[:,:,0]<100)&(im[:,:,1]>im[:,:,0]*1.4)&(im[:,:,1]>im[:,:,2]*.9)
  else:raise ValueError(mode)
  if polygons:
   keep=np.zeros(m.shape,np.uint8)
   for q in polygons:cv2.fillPoly(keep,[np.array(q,dtype=np.int32)-[x0,y0]],1)
   m&=keep.astype(bool)
  contours,hier=cv2.findContours(m.astype('uint8'),cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
  if hier is None:return []
  out=[]
  def contour(cnt,col):
   if len(cnt)<3 or cv2.contourArea(cnt)<minarea:return
   eps=.4
   while True:
    q=cv2.approxPolyDP(cnt,eps,True).reshape(-1,2)+[x0,y0];p=poly(q,col)
    if len(p['d'])<1850:out.append(p);break
    eps+=.15
    if eps>4:raise ValueError('Cannot simplify whole contour')
  for i,cnt in enumerate(contours):
   if hier[0][i][3]>=0:continue
   contour(cnt,c);child=hier[0][i][2]
   while child>=0:
    contour(contours[child],hole or self.bg);child=hier[0][child][0]
  return out
 def text(self,id,label,box,c=N,mode='dark',hole=None):
  self.add(id,label,'lettering',self.ink(box,c,mode,hole),'Outline huruf dari sumber; warna/bentuk editable, bukan teks ketik.')
 def export(self):
  root=ROOT/self.code;(root/'assets').mkdir(parents=True,exist_ok=True)
  elements=[];records=[];svgparts=[];thumbs=[]
  def shape(p,name):
   ns=list(map(float,re.findall(r'-?\d+(?:\.\d+)?',p['d'])));xs,ys=ns[::2],ns[1::2];x0,y0=min(xs),min(ys);ww,hh=max(xs)-x0,max(ys)-y0
   assert ww>0 and hh>0 and len(p['d'])<1900,(name,len(p['d']))
   return dict(type='shape',name=name,left=x0,top=y0,width=ww,height=hh,viewBox=dict(left=x0,top=y0,width=ww,height=hh),paths=[dict(d=p['d'],fill=dict(color=p['color']))])
  for a in self.assets:
   es=[shape(p,f'{a["id"]}_{j}') for j,p in enumerate(a['parts'])];x0=min(e['left'] for e in es);y0=min(e['top'] for e in es);x1=max(e['left']+e['width'] for e in es);y1=max(e['top']+e['height'] for e in es)
   for e in es:e['left']-=x0;e['top']-=y0
   if len(es)==1:e=es[0];e['left']+=x0;e['top']+=y0;e['name']=a['name']
   else:e=dict(type='group',name=a['name'],left=x0,top=y0,width=x1-x0,height=y1-y0,children=es)
   elements.append(e)
   body=''.join(f'<path d="{p["d"]}" fill="{p["color"]}"/>' for p in a['parts']);svgparts.append(f'<g id="{a["id"]}" data-name="{a["name"]}">{body}</g>')
   svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{x1-x0+4}" height="{y1-y0+4}" viewBox="{x0-2} {y0-2} {x1-x0+4} {y1-y0+4}">{body}</svg>'
   (root/'assets'/f'{a["id"]}.svg').write_text(svg,encoding='utf8');png=bytes(resvg_py.svg_to_bytes(svg_string=svg));(root/'assets'/f'{a["id"]}.png').write_bytes(png);thumbs.append((a['id']+' '+a['name'],png))
   records.append({k:a[k] for k in ['id','name','kind','note','body_part']}|dict(index=len(records),parts=len(es),bbox=[x0,y0,x1-x0,y1-y0]))
  full=f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'+''.join(svgparts)+'</svg>'
  (root/'preview.svg').write_text(full,encoding='utf8');(root/'preview.png').write_bytes(bytes(resvg_py.svg_to_bytes(svg_string=full)))
  pkg=dict(format='cusbe-canva-package',version=1,source=f'{self.code} - ASET UTUH',width=W,height=H,elements=elements,summary=dict(shape=sum(len(a['parts']) for a in self.assets),group=sum(e['type']=='group' for e in elements),image=0,text=0),warnings=['Measured manual flat-vector reconstruction. Not pixel-identical; gradients and textures simplified.','Lettering is editable vector outlines, not typed text.','Group ownership explicitly audited per asset; no automatic global colour grouping.'])
  raw=json.dumps(pkg,ensure_ascii=False).encode();(root/'CANVA_PACKAGE.json').write_bytes(raw);(root/'package.gz').write_bytes(gzip.compress(raw));(root/'inventory.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
  board=Image.new('RGB',(1250,math.ceil(len(thumbs)/5)*260),'#e4e8ed');draw=ImageDraw.Draw(board)
  for i,(name,png) in enumerate(thumbs):
   im=Image.open(io.BytesIO(png)).convert('RGBA');im.thumbnail((230,220));xx=i%5*250;yy=i//5*260;board.paste(im,(xx+8,yy+5),im);draw.text((xx+8,yy+232),name[:32],fill=N)
  board.save(root/'aset-terpisah.png')
  qa=dict(status='LOCAL_RECONSTRUCTION_PENDING_CANVA',assets=len(elements),**pkg['summary'],max_path_chars=max(len(p['d']) for a in self.assets for p in a['parts']),body_tiling=False,global_color_grouping=False)
  (root/'QA.json').write_text(json.dumps(qa,indent=2),encoding='utf8');print(self.code,qa)
  return pkg

