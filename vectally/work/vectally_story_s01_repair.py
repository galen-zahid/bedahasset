from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
from pathlib import Path
from copy import deepcopy
import io,json,hashlib,math
import cv2,numpy as np
from PIL import Image,ImageDraw,ImageFont
import resvg_py
from native_component_builder import ComponentBuilder,fill_holes,native_group,render_node
R=Path('outputs/VECTALLY-story-repair/S01');R.mkdir(parents=True,exist_ok=True);src=Path(VSRC_+'/Story/VECTALLY_S01_The_Books_Tell_A_Story.png');im=Image.open(src).convert('RGB');a=np.asarray(im);H,W=a.shape[:2];cb=ComponentBuilder(im);P=(a[:,:,2].astype(int)-a[:,:,0]>22)&(a[:,:,2]>100)&(a[:,:,0]>100);WH=(a.min(2)>190)&((a.max(2).astype(int)-a.min(2))<38);G=(a[:,:,1]>100)&(a[:,:,0]<100)&(a[:,:,2]>55)&(a[:,:,2]<220);N=(a[:,:,0]<95)&(a[:,:,1]<110)&(a[:,:,2]<135);N0=(a[:,:,0]<232)&(a[:,:,1]<240)&(a[:,:,2]<247)&((a[:,:,2].astype(int)-a[:,:,0])<43)&((a[:,:,1].astype(int)-a[:,:,0])<30)
def roi(m,box):
 x,y,xx,yy=box;q=np.zeros((H,W),'uint8');q[y:yy,x:xx]=m[y:yy,x:xx];return q
def components(m,minimum=10):
 count,lab,stats,_=cv2.connectedComponentsWithStats((m>0).astype('uint8'),8);return [(lab==i).astype('uint8')for i in range(1,count)if stats[i,cv2.CC_STAT_AREA]>=minimum]
def largest(m):
 co=components(m,5);return max(co,key=lambda x:x.sum())
def polygon(name,points,color):
 x=min(p[0]for p in points);y=min(p[1]for p in points);xx=max(p[0]for p in points);yy=max(p[1]for p in points);d='M'+' L'.join(f'{px-x:.3f} {py-y:.3f}'for px,py in points)+'Z';return dict(type='shape',name=name,left=x,top=y,width=xx-x,height=yy-y,viewBox=dict(left=0,top=0,width=xx-x,height=yy-y),paths=[dict(d=d,fill=dict(color=color))])
def add_parts(mask,name,children,minimum=12,color=None,fill=False):
 for i,m in enumerate(components(mask,minimum)):children.append(cb.node(m,name+' '+str(i+1),color=color,fill_ink_holes=fill))
parents={};assets=[];inventory=[]
for code,name,box,primary,fold in [('DOC1','Dokumen pendapatan utuh',(67,463,273,680),'white',[(227,464),(271,506),(227,514)]),('DOC2','Laporan grafik ungu utuh',(361,474,533,660),'purple',[(497,475),(532,508),(497,514)]),('DOC3','Struk ungu utuh',(48,726,202,923),'purple',None),('DOC4','Lembar diagram lingkaran utuh',(224,843,409,1030),'white',[(377,844),(408,871),(377,878)])]:
 base=fill_holes(largest(roi(P|WH,box)));visible_base=base.copy();
 if code in ['DOC1','DOC2']:
  span=(80,260)if code=='DOC1'else(382,529);hidden=(164,199)if code=='DOC1'else(435,474);xx=[];yy=[]
  for x in range(*span):
   if hidden[0]<=x<hidden[1]:continue
   ys=np.where(base[:,x]>0)[0]
   if len(ys):xx.append(x);yy.append(int(ys.max()))
  edge=np.polyfit(xx,yy,1)
  for x in range(*hidden):
   lower=int(round(np.polyval(edge,x)))+1;base[max(box[1],lower-42):lower,x]=1
 if code=='DOC2':cv2.fillPoly(base,[np.array([(362,641),(379,637),(379,658)],dtype='int32')],1)

 if code=='DOC3':
  patch=np.zeros_like(base);cv2.rectangle(patch,(185,791),(200,836),1,-1);base=np.maximum(base,patch)
 parents[code]=base;children=[cb.node(base,name+' - badan lengkap',color=cb.color(roi(WH if primary=='white'else P,box)),fill_ink_holes=True)]
 header=np.zeros_like(base)
 if code=='DOC1':
  cv2.rectangle(header,(90,499),(189,533),1,-1);children.append(polygon('DOC1 - garis judul utuh',[(94,516),(186,502),(186,514),(94,531)],'#ac8ded'))
 if code=='DOC4':
  cv2.rectangle(header,(245,867),(360,903),1,-1);children.append(polygon('DOC4 - garis judul utuh',[(248,889),(357,871),(357,883),(248,901)],'#82789f'))
 if primary=='white':add_parts((P&base.astype(bool)&~header.astype(bool)).astype('uint8'),code+' detail ungu',children,minimum=18)
 elif fold:
  fmask=np.zeros_like(base);cv2.fillPoly(fmask,[np.array(fold,dtype='int32')],1);fm=(P&fmask.astype(bool)).astype('uint8');children.append(cb.node(largest(fm),code+' lipatan sudut',color=cb.color(largest(fm))))
 if code=='DOC2':children.append(polygon('DOC2 - lipatan bawah kiri utuh',[(362,641),(379,637),(379,658)],'#7861aa'))
 add_parts((N0&cv2.erode(visible_base,np.ones((3,3),'uint8')).astype(bool)&~header.astype(bool)).astype('uint8'),code+' ikon atau garis isi',children,minimum=18)
 group=native_group(name,children);assets.append((code,group));inventory.append(dict(id=code,name=name,wholeBody=True,children=len(children),hiddenReconstruction='whole paper edge restored under green connector'if code in ['DOC1','DOC2','DOC3']else'none',iconTextPolicy='currency symbol is vector icon candidate; native-text scope remains open'if code=='DOC1'else'no bodycopy'))
 print(code,len(children),flush=True)
# Open book: one physical group owns both covers, page leaves, charts and rays.
bb=(348,891,912,1226);cover_parts=[m for m in components(roi(P|WH,bb),200) if (lambda r:r[0]+r[2]>450)(cv2.boundingRect(m))];original_cover=fill_holes(np.maximum.reduce(cover_parts));bp=original_cover.copy()
for cx in range(bb[0],bb[2]):
 ys=np.where(bp[:,cx]>0)[0]
 if len(ys):bp[ys.min():ys.max()+1,cx]=1
bookchildren=[cb.node(bp,'Buku - sampul lengkap tanpa celah tembus',color='#b898f9',fill_ink_holes=True)]
shadow=(bp>original_cover).astype('uint8');add_parts(shadow,'Buku - bayangan di bawah lembar',bookchildren,minimum=15,color='#091522')
pages=components(roi(WH,bb),200)
# Only the two main leaves are physical pages; internal white counters belong to those leaves.
pages=sorted(pages,key=lambda m:-int(m.sum()))[:2];leaf_union=np.zeros_like(bp)
for i,leaf in enumerate(pages):
 leaf=fill_holes(leaf);ys,xs=np.where(leaf>0);left=xs.mean()<650
 # Recover the top contour under the connector endpoint without extending past the page.
 lo,hi=(465,637)if left else(687,870);xx=[];yy=[]
 for x in range(lo,hi):
  sy=np.where(leaf[890:1000,x]>0)[0]
  if len(sy):xx.append(x);yy.append(int(sy.min()+890))
 if len(xx)>20:
  poly=np.polyfit(xx,yy,2)
  for x in range(638,660)if left else range(660,686):
   top=int(round(np.polyval(poly,x)));bottom=975
   leaf[max(890,top):bottom,x]=1
 bookchildren.append(cb.node(leaf,'Buku - lembar '+('kiri'if left else'kanan')+' utuh',color=cb.color(leaf),fill_ink_holes=True));bp=np.maximum(bp,leaf);leaf_union=np.maximum(leaf_union,leaf)
spine=np.zeros_like(bp)
for sy in range(960,1209):
 cx=int(round(658-(sy-960)*.244));spine[sy,cx-8:cx+9]=np.all(a[sy,cx-8:cx+9]<100,axis=1)
# The filled cover owns an opaque native shadow below the page crease.
# Purple chart and cover shadow remain parts of the same book group.
pp=(P&bp.astype(bool)).astype('uint8');
for m in components(pp,20):
 x,y,w,h=cv2.boundingRect(m)
 if y<1100 and x>680:bookchildren.append(cb.node(m,'Buku - segmen grafik ungu'))
bookchildren.append(polygon('Buku - lembar sampul belakang utuh',[(891,958),(909,965),(872,1223),(853,1216)],'#8a6ac3'))
gb=(G&leaf_union.astype(bool)).astype('uint8');gb[890:968,620:687]=0
for i,m in enumerate(components(gb,15)):
 x,y,w,h=cv2.boundingRect(m);bookchildren.append(cb.node(m,'Buku - aksen hijau '+str(i+1),fill_ink_holes=(x>640 and y>1030)))
add_parts((N0&cv2.erode(leaf_union,np.ones((3,3),'uint8')).astype(bool)).astype('uint8'),'Buku - garis dan tinta',bookchildren,minimum=18)
check=roi((a[:,:,0]<100)&(a[:,:,1]<160)&(a[:,:,2]<155),(646,1058,703,1140));add_parts(check,'Buku - tinta centang',bookchildren,minimum=15)
rays=roi(G,(738,770,842,870));add_parts(rays,'Buku - sorot penekanan',bookchildren,minimum=15);book=native_group('Buku terbuka - sampul lembar grafik dan sorot',bookchildren);inventory.append(dict(id='BOOK',name=book['name'],wholeBody=True,children=len(bookchildren),hiddenReconstruction='top leaf contour restored under connector endpoint',nestedGroups=False));print('BOOK',len(bookchildren),flush=True)
# One connected process network, with the pill text reserved for native editing.
flowmask=largest(roi(G,(160,570,690,963)));flowmask[579:587,269:319]=1;flow=cb.node(fill_holes(flowmask),'Jaringan konektor dan panel TELL A utuh',fill_ink_holes=True);assets.append(('FLOW',flow));inventory.append(dict(id='FLOW',wholeBody=True,children=1,text='TELL A not inserted; requires native or approved TypeCraft',noBodyTiling=True));print('FLOW',flush=True)
# Source rays belong to the book; ribbons are whole ornaments behind the sheets.
# Each document owns its shadow.
shadows={
 'DOC1':polygon('DOC1 - bayangan kiri utuh',[(0,603),(227,560),(227,596),(0,639)],'#51456f'),
 'DOC2':polygon('DOC2 - bayangan kanan utuh',[(379,588),(635,542),(608,656),(379,700)],'#302b4a'),
 'DOC3':polygon('DOC3 - bayangan kiri utuh',[(0,825),(201,783),(201,864),(0,917)],'#51456f'),
 'DOC4':polygon('DOC4 - bayangan kiri utuh',[(113,980),(407,916),(407,962),(113,1035)],'#65518f')}
for code,group in assets:
 if code in shadows:
  absolute=[]
  for e in group['children']:
   child=deepcopy(e);child['left']+=group['left'];child['top']+=group['top'];absolute.append(child)
  combined=native_group(group['name'],[shadows[code]]+absolute);group.clear();group.update(combined)

loop=dict(type='shape',name='Pita loop belakang buku utuh',left=254,top=1098,width=160,height=205,viewBox=dict(left=0,top=0,width=160,height=205),paths=[dict(d='M160 0C-51 0 -51 205 118 205L118 184C-24 184 -24 21 160 21Z',fill=dict(color='#00d49c'))])
bg=polygon('Latar - gradasi sumber belum dipulihkan',[(0,0),(W,0),(W,H),(0,H)],'#091522');elements=[bg,loop]+[g for c,g in assets if c!='FLOW']+[book]+[g for c,g in assets if c=='FLOW']
# Header/footer decorative bars, without outlining any text.
elements.append(polygon('Aksen garis merek',[(46,157),(269,157),(269,167),(46,167)],'#00dfa0'));elements.append(polygon('Aksen teks deskripsi',[(44,1370),(53,1370),(53,1548),(44,1548)],'#00dfa0'))
def count(es,t):return sum((e['type']==t)+count(e.get('children',[]),t)for e in es)
pkg=dict(format='cusbe-canva-package',version=1,source='S01 - KANDIDAT ASET UTUH - TYPOGRAPHY PENDING',width=W,height=H,elements=elements,summary={t:count(elements,t)for t in ['shape','text','group','image']},warnings=['Incomplete asset candidate. Headlines and bodycopy not inserted.','Semantic grouping by physical sheet/book/process network, not global color.','Source gradients and currency-icon text policy unresolved.']);(R/'ASSETS_PACKAGE.json').write_text(json.dumps(pkg));(R/'INVENTORY.json').write_text(json.dumps(inventory,indent=2));(R/'GEOMETRY-AUDIT.json').write_text(json.dumps(cb.audit,indent=2));svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">'+''.join(render_node(e)for e in elements)+'</svg>';(R/'assets.svg').write_text(svg);(R/'assets.png').write_bytes(bytes(resvg_py.svg_to_bytes(svg_string=svg)));print(json.dumps(pkg['summary']),flush=True)
