from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
from pathlib import Path
import json
import numpy as np,cv2
from PIL import Image
import resvg_py
from native_component_builder import ComponentBuilder,fill_holes,native_group,render_node
from normalize_native_package import normalize_package
from native_clean_quad import clean_quad

def parts(mask,minimum=20):
 n,labels,stats,_=cv2.connectedComponentsWithStats(mask.astype('uint8'),8);return [(labels==i).astype('uint8')for i in range(1,n)if stats[i,4]>=minimum]
def roi(mask,box):
 x,y,xx,yy=box;q=np.zeros(mask.shape,'uint8');q[y:yy,x:xx]=mask[y:yy,x:xx];return q
def largest(mask):return max(parts(mask,5),key=lambda m:int(m.sum()))
def rectangle(name,x,y,w,h,color,r=0):
 return dict(type='shape',name=name,left=x,top=y,width=w,height=h,viewBox=dict(left=0,top=0,width=w,height=h),paths=[dict(d=f'M{r} 0H{w-r}C{w-r/3} 0 {w} {r/3} {w} {r}V{h-r}C{w} {h-r/3} {w-r/3} {h} {w-r} {h}H{r}C{r/3} {h} 0 {h-r/3} 0 {h-r}V{r}C0 {r/3} {r/3} 0 {r} 0Z',fill=dict(color=color))])
def count(es,t):return sum((e['type']==t)+count(e.get('children',[]),t)for e in es)
def save(sid,source,elements,cb,inventory):
 r=Path('outputs/VECTALLY-story-repair')/sid;r.mkdir(parents=True,exist_ok=True);p=normalize_package(dict(format='cusbe-canva-package',version=1,source=source,width=941,height=1672,elements=elements,summary={t:count(elements,t)for t in ['shape','text','group','image']},warnings=['Asset prototype only. No outlined copy: native or approved TypeCraft copy pending.','Source gradients and grain not yet restored.']))
 (r/'ASSETS_PACKAGE.json').write_text(json.dumps(p));(r/'GEOMETRY-AUDIT.json').write_text(json.dumps(cb.audit,indent=2));(r/'INVENTORY.json').write_text(json.dumps(inventory,indent=2));svg='<svg xmlns="http://www.w3.org/2000/svg" width="941" height="1672">'+''.join(render_node(e)for e in elements)+'</svg>';(r/'assets.svg').write_text(svg);(r/'assets.png').write_bytes(resvg_py.svg_to_bytes(svg_string=svg));print(json.dumps(dict(id=sid,summary=p['summary'],geometryFailures=[x['name']for x in cb.audit if x['local_geometry_gate']!='PASS'])),flush=True)

def s03():
 im=Image.open(VSRC_+'/Story/VECTALLY_S03_Which_Report_Shows_Profit.png').convert('RGB');a=np.asarray(im);cb=ComponentBuilder(im);WH=(a.min(2)>190)&((a.max(2).astype(int)-a.min(2))<45);G=(a[:,:,1]>100)&(a[:,:,0]<100)&(a[:,:,2]>45);P=(a[:,:,2].astype(int)-a[:,:,0]>15)&(a[:,:,2].astype(int)-a[:,:,1]>25)&(a[:,:,0]>70);N=a.max(2)<95
 cards=[];inventory=[]
 for code,name,box in [('PL','Lembar Profit and Loss',(60,610,412,1053)),('BS','Lembar Balance Sheet',(486,620,874,1058))]:
  body=fill_holes(largest(roi(WH,box)));visible=body.copy();ys=[];xs=[]
  for y in list(range(670,750))+list(range(920,990)):
   xx=np.where(body[y]>0)[0]
   if len(xx):ys.append(y);xs.append(int(xx.max()if code=='PL'else xx.min()))
  fit=np.polyfit(ys,xs,1)
  for y in range(758,901):
   edge=int(round(np.polyval(fit,y)))
   if code=='PL':body[y,350:edge+1]=1
   else:body[y,edge:edge+50]=1
  child=[cb.node(body,name+' - kertas utuh di bawah pilihan OR',color='#f3f5fa',fill_ink_holes=True)]
  contentroi=(100,780,366,1020)if code=='PL'else(530,785,820,995)
  for i,m in enumerate(parts(roi(P&visible.astype(bool),contentroi),80)):child.append(cb.node(fill_holes(m),name+' - baris laporan '+str(i+1),fill_ink_holes=True))
  if code=='PL':
   for i,m in enumerate(parts(roi(((a[:,:,1].astype(int)-a[:,:,0]>40)&(a[:,:,1].astype(int)-a[:,:,2]>10)&(a[:,:,1]>150))&visible.astype(bool),(100,952,370,1025)),50)):child.append(cb.node(fill_holes(m),name+' - total hijau '+str(i+1),fill_ink_holes=True))
   for box2,nm in [((330,775,375,865),'tanda aritmetika'),((104,925,367,977),'garis total')]:
    for i,m in enumerate(parts(roi(N,box2),10)):child.append(cb.node(m,name+' - '+nm+' '+str(i+1),color='#091522'))
  else:
   for i,m in enumerate(parts(roi(N,(648,787,701,1002)),20)):child.append(cb.node(m,name+' - pemisah kolom '+str(i+1),color='#091522'))
  assert len(child)==(8 if code=='PL'else 10),(code,len(child),'missing expected report detail')
  group=native_group(name+' - kertas dan seluruh detail',child);cards.append(group);inventory.append(dict(id=code,name=group['name'],wholeBody=True,hiddenReconstruction='edge restored behind green OR badge',nativeCopy='PENDING',children=len(child)));print(code,len(child),flush=True)
 accents=[]
 for nm,box in [('Garis penegas SHOWS',(420,510,890,620)),('Garis penegas PROFIT',(90,1290,795,1410)),('Pilihan OR - lingkaran utuh',(390,750,540,901))]:
  m=fill_holes(largest(roi(G,box)));accents.append(cb.node(m,nm,fill_ink_holes=True));inventory.append(dict(id=nm,wholeBody=True,nativeCopy='OR pending'if'OR -'in nm else'non-copy ornament'))
 save('S03','S03 - DUA LAPORAN UTUH - TYPOGRAPHY PENDING',[rectangle('Latar ungu - gradasi belum dipulihkan',0,0,941,1672,'#b296fa')]+cards+accents,cb,inventory)

def s04():
 im=Image.open(VSRC_+'/Story/VECTALLY_S04_Its_The_Profit_And_Loss.png').convert('RGB');a=np.asarray(im);cb=ComponentBuilder(im);N=a.max(2)<90;WH=(a.min(2)>190)&((a.max(2).astype(int)-a.min(2))<45);P=(a[:,:,2].astype(int)-a[:,:,0]>20)&(a[:,:,2].astype(int)-a[:,:,1]>25)&(a[:,:,0]>80)
 icons=[];inventory=[]
 for code,name,box,inside,arrow in [('REV','Tumpukan revenue',(42,590,267,886),WH,(110,620,198,706)),('EXP','Tumpukan expenses',(356,627,579,887),P,(424,657,505,745)),('RES','Kantong hasil',(660,567,913,887),WH,(737,690,835,831))]:
  outer=fill_holes(largest(roi(N,box)));child=[cb.node(outer,name+' - badan luar lengkap',color='#091522',fill_ink_holes=True)]
  for i,m in enumerate(parts(roi(inside,box),200)):child.append(cb.node(fill_holes(m),name+' - bidang isi '+str(i+1),color='#b99bfc'if code=='EXP'else'#f4f7fa',fill_ink_holes=True))
  for i,m in enumerate(parts(roi(N,arrow),100)):child.append(cb.node(m,name+' - simbol '+str(i+1),color='#091522'))
  group=native_group(name+' - satu aset lengkap',child);icons.append(group);inventory.append(dict(id=code,name=group['name'],wholeBody=True,children=len(child),nativeCopy='no outlined label; currency symbol icon policy pending'if code=='RES'else'labels separate, native text pending'));print(code,len(child),flush=True)
 accents=[]
 for nm,box in [('Pita IT’S THE',(42,286,369,331)),('Pita LOSS',(42,1327,895,1412))]:
  accents.append(cb.node(fill_holes(largest(roi(P,box))),nm,fill_ink_holes=True))
 badges=[rectangle('Label REVENUE - kapsul utuh',30,897,265,73,'#f4f7fa',36.5),rectangle('Label EXPENSES - kapsul utuh',337,897,282,73,'#b99bfc',36.5),rectangle('Label RESULT - kapsul utuh',661,897,249,73,'#f4f7fa',36.5)]
 arith=[rectangle('Operator minus',285,746,55,18,'#091522'),rectangle('Operator sama dengan atas',599,730,54,18,'#091522'),rectangle('Operator sama dengan bawah',599,761,54,18,'#091522')]
 save('S04','S04 - REVENUE EXPENSES RESULT PER ASET - TYPOGRAPHY PENDING',[rectangle('Latar hijau - gradasi belum dipulihkan',0,0,941,1672,'#00d59c')]+icons+arith+accents+badges,cb,inventory)
if __name__=='__main__':
 import sys
 {'S03':s03,'S04':s04}[sys.argv[1]]()
