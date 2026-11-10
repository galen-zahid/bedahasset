from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
from pathlib import Path
import io,json
import numpy as np,cv2
from PIL import Image
import resvg_py
from native_component_builder import ComponentBuilder,fill_holes,native_group,render_node
from vectally_story_s03_s04_repair import parts,roi,largest,rectangle,save
im=Image.open(VSRC_+'/Story/VECTALLY_S06_Good_Records_Better_Decisions.png').convert('RGB');a=np.asarray(im);H,W=a.shape[:2];cb=ComponentBuilder(im)
P=(a[:,:,2].astype(int)-a[:,:,0]>15)&(a[:,:,2].astype(int)-a[:,:,1]>15)&(a[:,:,0]>100)
PS=(a[:,:,2].astype(int)-a[:,:,0]>65)&(a[:,:,0]<195)
WH=(a.min(2)>190)&((a.max(2).astype(int)-a.min(2))<45)
G=(a[:,:,0]<120)&(a[:,:,1]>45)&(a[:,:,1].astype(int)-a[:,:,2]>5)&(a[:,:,1].astype(int)-a[:,:,0]>25)
N=a.max(2)<85

def path(name,box,d,color):
 x,y,w,h=box;return dict(type='shape',name=name,left=x,top=y,width=w,height=h,viewBox=dict(left=0,top=0,width=w,height=h),paths=[dict(d=d,fill=dict(color=color))])
def svgmask(d):
 svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"><path d="{d}" fill="#ffffff"/></svg>';return (np.asarray(Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert('RGBA'))[:,:,3]>127).astype('uint8')
back2=path('Kertas belakang ungu tua - satu lembar utuh',(21,699,323,389),'M13 39L260 0C272 0 282 8 284 22L323 343C323 357 315 365 302 368L73 388C59 389 56 383 55 374L0 59C0 47 5 41 13 39Z','#a17ce9')
back1=path('Kertas tengah ungu muda - satu lembar utuh',(50,682,321,395),'M16 27L259 0C271 0 281 7 282 21L321 354C321 365 315 373 304 375L42 395C29 395 24 389 23 378L0 52C0 38 6 29 16 27Z','#cdb7fc')
front=path('Laporan depan - badan kertas utuh',(96,679,289,379),'M18 0H220L289 69V361C289 371 281 379 271 379H18C8 379 0 371 0 361V18C0 8 8 0 18 0Z','#f4f7fa')
fold=path('Laporan depan - lipatan pojok',(316,679,69,69),'M0 0L69 69H10C4 69 0 65 0 59Z','#c8adfa')
children=[front,fold];detail_counts={}
for name,box in [('batang grafik',(120,714,309,811)),('garis bawah grafik',(120,816,361,834))]:
 mm=parts(roi(P,box),20);detail_counts[name]=len(mm)
 for i,m in enumerate(mm):children.append(cb.node(fill_holes(m),'Laporan - '+name+' '+str(i+1),color='#9d7bee',fill_ink_holes=True))
assert detail_counts['batang grafik']==4 and detail_counts['garis bawah grafik']==1,detail_counts
for idx,(y,yy)in enumerate([(843,881),(893,931),(943,981),(993,1032)]):
 m=fill_holes(largest(roi(P,(122,y,289,yy))));children.append(cb.node(m,'Laporan - bidang baris '+str(idx+1),color='#d3c0fc',fill_ink_holes=True))
 for j,ink in enumerate(parts(roi(PS,(130,y+3,279,yy-3)),25)):children.append(cb.node(ink,'Laporan - isi baris '+str(idx+1)+'.'+str(j+1),color='#a17aeb'))
checks=parts(roi(G,(302,842,351,1031)),50);assert len(checks)==4,len(checks)
for i,m in enumerate(checks):children.append(cb.node(m,'Laporan - centang '+str(i+1),color='#00b88d'))
for i,m in enumerate(parts(roi(P,(294,842,362,1032)),20)):children.append(cb.node(m,'Laporan - kisi tabel '+str(i+1),color='#d1cee9'))
report=native_group('Laporan depan - kertas lipatan grafik tabel centang',children);print('REPORT',len(children),flush=True)
# Reconstruct one smooth ribbon through the display occlusion; source-visible contour fit remains a separate pending gate.
ribbon_path='M112 321C-10 350 5 455 96 517C208 594 422 663 517 738C573 781 593 826 566 841L592 826C618 773 545 678 456 630C355 562 140 484 104 422C81 386 89 354 112 345Z'
band=svgmask(ribbon_path);ribbon=roi(G,(20,310,640,860));ribbon[510:625,140:640]=band[510:625,140:640]
ribbon=np.maximum(ribbon,(band&roi(WH,(45,297,740,500)).astype('uint8')))
branch=fill_holes(largest(roi(G&((a[:,:,1]>180)|(np.arange(H)[:,None]>=830)),(381,680,914,1031))));body=np.maximum(band,branch)
# A connected source-attached bridge below the hidden display line makes this one physical ribbon/tree.
body=np.maximum(body,band);body=fill_holes(largest(body));
import re
x,y,w,h=cv2.boundingRect(band);coord=[0]
def shift_coord(match):
 idx=coord[0];coord[0]+=1;value=float(match.group())-(x if idx%2==0 else y);return f'{value:.3f}'.rstrip('0').rstrip('.')
shifted=re.sub(r'-?\d+(?:\.\d+)?',shift_coord,ribbon_path)
backribbon=path('Alur keputusan - pita belakang utuh dengan kurva asli',(x,y,w,h),shifted,'#0c8067')
tree=[backribbon,cb.node(branch,'Alur keputusan - tiga cabang dan panel depan utuh',color='#00d8a0',fill_ink_holes=True)]

for name,box in [('sasaran',(757,689,838,769)),('timbangan',(748,812,846,892)),('kalender',(751,937,840,1016))]:
 shapes=parts(roi(N,box),12);assert shapes,(name,'missing icon')
 for i,m in enumerate(shapes):tree.append(cb.node(m,'Panel '+name+' - ikon '+str(i+1),color='#091522'))
flow=native_group('Pita alur dan tiga panel keputusan - satu aset terhubung',tree);print('FLOW',len(tree),flush=True)
cta=path('Panel CTA - jajaran genjang utuh',(58,1293,824,111),'M55 0H824L769 111H0Z','#00dfa0')
footer=rectangle('Bidang respons kosong - kapsul utuh',49,1464,843,159,'#f4f7fa',49)
brand=path('Aksen merek - garis miring utuh',(58,59,40,37),'M20 0H40L20 37H0Z','#00dfa0')
inventory=[dict(id='PAPER_BACK_2',wholeBody=True,hiddenBody='reconstructed whole rear sheet, visible contour still requires final source alignment'),dict(id='PAPER_BACK_1',wholeBody=True,hiddenBody='reconstructed whole middle sheet, visible contour still requires final source alignment'),dict(id='PAPER_FRONT',wholeBody=True,children=len(children),contents=detail_counts,checks=4),dict(id='DECISION_FLOW',wholeBody=True,children=len(tree),heads=3,iconTypes=['target','scales','calendar'],reconstruction='analytic hidden ribbon behind title; final visible contour comparison pending'),dict(id='CTA',wholeBody=True,nativeCopy='PENDING'),dict(id='RESPONSE',wholeBody=True),dict(id='BRAND_ACCENT',wholeBody=True)]
save('S06','S06 - TIGA KERTAS DAN ALUR KEPUTUSAN UTUH - TEXT PENDING',[rectangle('Latar - gradasi sumber belum dipulihkan',0,0,W,H,'#091522'),flow,back2,back1,report,cta,footer,brand],cb,inventory)
