from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
from pathlib import Path
import json
import cv2,numpy as np
from PIL import Image
import resvg_py
from native_component_builder import ComponentBuilder,fill_holes,native_group,render_node
from normalize_native_package import normalize_package
R=Path('outputs/VECTALLY-story-repair/S02');R.mkdir(parents=True,exist_ok=True)
im=Image.open(VSRC_+'/Story/VECTALLY_S02_Whats_Harder_To_Track.png').convert('RGB');a=np.asarray(im);H,W=a.shape[:2];cb=ComponentBuilder(im)
P=(a[:,:,2].astype(int)-a[:,:,0]>25)&(a[:,:,0]>90)&(a[:,:,0]<215)&(a[:,:,2]>150)
N=(a.max(2)<95);G=(a[:,:,1]>95)&(a[:,:,0]<70)&(a[:,:,2]>45)
def roi(m,box):
 x,y,xx,yy=box;q=np.zeros((H,W),'uint8');q[y:yy,x:xx]=m[y:yy,x:xx];return q
def parts(m,minimum=16):
 n,lab,stats,_=cv2.connectedComponentsWithStats(m.astype('uint8'),8);return [(lab==i).astype('uint8')for i in range(1,n)if stats[i,4]>=minimum]
def path(name,box,d,color):
 x,y,w,h=box;return dict(type='shape',name=name,left=x,top=y,width=w,height=h,viewBox=dict(left=0,top=0,width=w,height=h),paths=[dict(d=d,fill=dict(color=color))])
def absolute_path(name,d,color):
 import re
 tokens=re.findall(r'[MLCHVZ]|-?\d+(?:\.\d+)?',d);ops=[];i=0;cx=cy=0;xs=[];ys=[]
 while i<len(tokens):
  op=tokens[i];i+=1;n={'M':2,'L':2,'C':6,'H':1,'V':1,'Z':0}[op];v=list(map(float,tokens[i:i+n]));i+=n
  if op in ['M','L','C']:
   xs.extend(v[::2]);ys.extend(v[1::2]);cx,cy=v[-2:]
  elif op=='H':xs.append(v[0]);ys.append(cy);cx=v[0]
  elif op=='V':ys.append(v[0]);xs.append(cx);cy=v[0]
  ops.append((op,v))
 x=min(xs);y=min(ys);xx=max(xs);yy=max(ys);result=''
 for op,v in ops:
  if op in ['M','L','C']:v=[n-(x if j%2==0 else y) for j,n in enumerate(v)]
  elif op=='H':v=[v[0]-x]
  elif op=='V':v=[v[0]-y]
  result+=op+' '.join(f'{n:.4f}'.rstrip('0').rstrip('.') for n in v)
 return path(name,(x,y,xx-x,yy-y),result,color)
def roundrect(name,x,y,w,h,r,color):
 return path(name,(x,y,w,h),f'M{r} 0H{w-r}C{w-r/3} 0 {w} {r/3} {w} {r}V{h-r}C{w} {h-r/3} {w-r/3} {h} {w-r} {h}H{r}C{r/3} {h} 0 {h-r/3} 0 {h-r}V{r}C0 {r/3} {r/3} 0 {r} 0Z',color)
def native_mask(node):
 svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">'+render_node(node)+'</svg>'
 import io
 return (np.asarray(Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert('RGBA'))[:,:,3]>127).astype('uint8')
receipts=[('FOOD','Struk makanan', 'M99 241L263 219C279 217 282 225 282 237L301 375L286 369L271 382L254 373L238 387L220 377L202 390L185 380L168 393L150 383L134 395L116 385L100 397L81 260C78 245 88 242 99 241Z',[(110,250,160,322),(172,250,270,300),(244,302,275,355)]),('FUEL','Struk bahan bakar','M64 379L232 400C247 403 254 411 251 432L236 535L218 530L200 543L184 533L166 546L149 536L131 548L114 538L96 550L80 540L62 552L46 541L31 528L46 398C48 385 52 380 64 379Z',[(64,402,125,471),(128,410,228,465),(186,472,218,524)]),('SHOP','Struk belanja','M109 556L266 528C276 526 284 533 288 546L308 674L292 667L277 682L260 675L244 688L227 680L209 694L192 687L175 701L156 693L140 708L124 700L104 714L77 579C74 568 82 559 109 556Z',[(94,580,161,639),(172,557,270,611),(247,608,280,659)])]
groups=[];inventory=[]
for code,name,d,rois in receipts:
 outer=absolute_path(name+' - kertas luar lengkap',d,'#b497fc');mask=native_mask(outer);inner=cv2.erode(mask,np.ones((7,7),'uint8'));children=[outer,cb.node(inner,name+' - bidang kertas utuh',color='#f6f3ff',fill_ink_holes=True)]
 for j,box in enumerate(rois):
  for k,m in enumerate(parts(roi(P,box),10)):children.append(cb.node(m,name+f' - ikon atau detail {j+1}.{k+1}',color='#a17afa'))
 group=native_group(name+' - badan ikon dan detail',children);groups.append(group);inventory.append(dict(id=code,name=group['name'],wholeBody=True,hiddenEdge='reconstructed continuous receipt silhouette',currencyPolicy='vector icon candidate; native copy policy unresolved',children=len(children)));print(code,len(children),flush=True)
# Curves remain a separate connected network, behind all paper assets.
connector=path('Konektor tiga struk - satu jalur utuh',(243,321,158,298),'M50 0C79 0 103 20 103 47V132C103 167 123 184 151 185L137 173L140 168L158 185L140 207L135 203L150 190C113 190 99 207 99 237V249C99 277 85 295 54 298L53 293C78 291 94 276 94 249V237C94 215 102 200 118 190C94 188 78 178 65 162C51 146 44 141 20 141H0V136H20C47 136 56 143 69 159C83 175 98 184 124 185C106 173 98 156 98 132V47C98 23 77 5 50 5Z','#ad8aff')
# Classification tag with transparent inner counter, owned by the same tag group.
tagmask=roi(G,(407,456,622,562));tagbody=cb.node(fill_holes(max(parts(tagmask,50),key=lambda m:m.sum())),'Panel label klasifikasi utuh',color='#00d79e',fill_ink_holes=True)
tagink=parts(roi(N,(434,478,600,541)),18);tag=native_group('Panel klasifikasi - label dan garis',[tagbody]+[cb.node(m,'Label klasifikasi - ikon atau garis '+str(i+1),color='#091522')for i,m in enumerate(tagink)])
invoice_outline='M611 962L828 962L897 1032L858 1320C856 1335 850 1342 832 1342L573 1342C558 1342 549 1331 552 1317L589 986C591 969 598 962 611 962Z'
invoiceouter=absolute_path('Invoice - tepi luar lengkap',invoice_outline,'#091522');invoice_mask=native_mask(invoiceouter);invoiceinner=cv2.erode(invoice_mask,np.ones((15,15),'uint8'));invoicechildren=[invoiceouter,cb.node(invoiceinner,'Invoice - kertas lengkap di bawah status',color='#f3f7fa',fill_ink_holes=True),absolute_path('Invoice - lipatan pojok','M827 967L894 1034H844C831.333 1034 825 1029 825 1019Z','#26354a')]
bar=(a[:,:,0]>50)&(a[:,:,0]<190)&(a[:,:,1]<205)&(a[:,:,2]<230)
for i,m in enumerate(parts(roi(bar,(600,1060,860,1180)),30)):
 x,y,w,h=cv2.boundingRect(m)
 if w>40:invoicechildren.append(cb.node(fill_holes(m),'Invoice - garis isi '+str(i+1),color='#6c8199'))
for i,m in enumerate(parts(roi(N,(790,1120,847,1210)),30)):invoicechildren.append(cb.node(m,'Invoice - simbol mata uang '+str(i+1),color='#091522'))
invoice=native_group('Invoice - kertas lipatan dan isi',invoicechildren)
status=[roundrect('Status - tepi kapsul utuh',591,1229,312,74,37,'#078346'),roundrect('Status - bidang kapsul utuh',597,1235,300,62,31,'#f4faf7'),roundrect('Status - lingkaran tanda perhatian',613,1242,49,49,24.5,'#00df9d'),roundrect('Status - tangkai perhatian',635,1251,6,20,3,'#ffffff'),roundrect('Status - titik perhatian',635,1276,6,6,3,'#ffffff'),roundrect('Status - aksen latar OPEN PAYMENT',673,1253,205,26,2,'#00dda0')]
status=native_group('Status pembayaran - kapsul ikon dan aksen',status)
elements=[roundrect('Latar - gradasi belum dipulihkan',0,0,W,H,0,'#f1f6fa'),connector]+groups+[tag,invoice,status,roundrect('Pilihan EXPENSES - kapsul utuh',45,1484,428,143,43,'#b99afd'),roundrect('Pilihan UNPAID INVOICES - kapsul utuh',494,1484,409,146,40,'#091522')]
def count(es,t):return sum((e['type']==t)+count(e.get('children',[]),t)for e in es)
pkg=normalize_package(dict(format='cusbe-canva-package',version=1,source='S02 - ASET PER OBJEK - TEKS DAN GRADASI PENDING',width=W,height=H,elements=elements,summary={t:count(elements,t)for t in ['shape','text','group','image']},warnings=['Asset candidate only; native text pending','Source gradients not yet restored','Currency icons policy pending']))
(R/'ASSETS_PACKAGE.json').write_text(json.dumps(pkg));(R/'INVENTORY.json').write_text(json.dumps(inventory,indent=2));(R/'GEOMETRY-AUDIT.json').write_text(json.dumps(cb.audit,indent=2))
svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">'+''.join(render_node(e)for e in elements)+'</svg>';(R/'assets.svg').write_text(svg);(R/'assets.png').write_bytes(resvg_py.svg_to_bytes(svg_string=svg));print(json.dumps(pkg['summary']),flush=True)
