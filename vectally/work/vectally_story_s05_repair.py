from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import cv2,numpy as np,json,math,io
import resvg_py
from native_component_builder import ComponentBuilder,render_node
from native_clean_quad import clean_quad
R=Path('outputs/VECTALLY-story-repair/S05');src=Path(VSRC_+'/Story/VECTALLY_S05_Got_A_Bookkeeping_Question.png');im=Image.open(src).convert('RGB');a=np.asarray(im);h,w=a.shape[:2];cb=ComponentBuilder(im);elements=[]
def roi_mask(condition,box):
 x,y,xx,yy=box;m=np.zeros((h,w),'uint8');m[y:yy,x:xx]=condition[y:yy,x:xx];return m
bg='#f1f5f9';elements.append(dict(type='shape',name='Latar - gradasi sumber belum dipulihkan',left=0,top=0,width=w,height=h,viewBox=dict(left=0,top=0,width=w,height=h),paths=[dict(d=f'M0 0H{w}V{h}H0Z',fill=dict(color=bg))]))
dark=np.all(a<90,axis=2);green=(a[:,:,1]>110)&(a[:,:,0]<100)&(a[:,:,2]>70)&(a[:,:,2]<210);purple=(a[:,:,2].astype(int)-a[:,:,0]>25)&(a[:,:,0]>110)
for name,cond,box in [('Bingkai sudut kanan atas utuh',dark,(390,310,905,600)),('Bingkai sudut kiri bawah utuh',purple,(25,1135,270,1400)),('Aksen garis logo utuh',green,(90,125,305,165)),('Aksen garis QUESTION utuh',green,(380,1335,900,1435))]:
 m=roi_mask(cond,box);node=cb.node(m,name)
 if name.startswith('Aksen'):
  node,clean=clean_quad(node,m);cb.audit[-1]['regularization']=clean
 elements.append(node)
fits=json.loads((R/'FONT-FIT.json').read_text());textgeom=[]
for f in fits:
 name=f['font'];fontfile=Path('outputs/VECTALLY-teks-native/fonts')/('archivoblack-ArchivoBlack-Regular.ttf'if name=='Archivo Black'else'asap-Asap[wdth,wght].ttf');ft=ImageFont.truetype(str(fontfile),150)
 if name=='Asap':ft.set_variation_by_axes([400,100])
 tr=f['letterSpacingEm'];size=f['fontSize'];t=f['text'];adv=sum(ft.getlength(c)for c in t)+(len(t)-1)*tr*150;canvas=Image.new('L',(math.ceil(adv)+80,400));dr=ImageDraw.Draw(canvas);xp=40.
 for c in t:dr.text((xp,200),c,font=ft,fill=255,anchor='ls');xp+=ft.getlength(c)+tr*150
 ink=np.asarray(canvas);ix,iy,iw,ih=cv2.boundingRect((ink>127).astype('uint8'));scale=size/150;width=adv*scale+12;height=size*1.2;cx,cy=f['inkCenter'];rot=f['rotation'];ang=math.radians(rot);co=math.cos(ang);sn=math.sin(ang);offset=.05 if name=='Archivo Black'else .04;icx=(ix-40+iw/2)*scale;icy=(iy-200+ft.getmetrics()[0]+ih/2)*scale+offset*size;vx=icx-width/2;vy=icy-height/2;left=cx-width/2-(co*vx-sn*vy);top=cy-height/2-(sn*vx+co*vy);e=dict(type='text',name=t,text=t,fontName=name,fontFamily=name,fontSize=size,fontWeight='normal',fontStyle='normal',letterSpacingEm=tr,lineHeightEm=1.2,left=left,top=top,width=width,height=height,rotation=rot,color='#091522');elements.append(e);textgeom.append(dict(text=t,element=e,fontFitIoU=f['iou'],actualCanva='PENDING'));
svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'+''.join(render_node(e)for e in elements if e['type']=='shape')+'</svg>';base=Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert('RGBA')
for f in fits:
 name=f['font'];fontfile=Path('outputs/VECTALLY-teks-native/fonts')/('archivoblack-ArchivoBlack-Regular.ttf'if name=='Archivo Black'else'asap-Asap[wdth,wght].ttf');ft=ImageFont.truetype(str(fontfile),150)
 if name=='Asap':ft.set_variation_by_axes([400,100])
 tr=f['letterSpacingEm'];adv=sum(ft.getlength(c)for c in f['text'])+(len(f['text'])-1)*tr*150;ci=Image.new('L',(math.ceil(adv)+80,400));dr=ImageDraw.Draw(ci);xp=40.
 for c in f['text']:dr.text((xp,200),c,font=ft,fill=255,anchor='ls');xp+=ft.getlength(c)+tr*150
 ar=np.asarray(ci);ix,iy,iw,ih=cv2.boundingRect((ar>127).astype('uint8'));ar=ar[iy:iy+ih,ix:ix+iw];ss=f['fontSize']/150;ang=math.radians(f['rotation']);co=math.cos(ang)*ss;sn=math.sin(ang)*ss;cx,cy=f['inkCenter'];M=np.array([[co,-sn,cx-co*iw/2+sn*ih/2],[sn,co,cy-sn*iw/2-co*ih/2]],'float32');mask=cv2.warpAffine(ar,M,(w,h),flags=cv2.INTER_LINEAR);layer=Image.new('RGBA',(w,h),'#091522');layer.putalpha(Image.fromarray(mask));base.alpha_composite(layer)
base.convert('RGB').save(R/'preview.png');(R/'assets.svg').write_text(svg);pkg=dict(format='cusbe-canva-package',version=2,source='S05 - BINGKAI UTUH DAN TEKS NATIVE DENGAN SPASI',width=w,height=h,elements=elements,summary=dict(shape=5,text=5,group=0,image=0),warnings=['Candidate, typography not1:1; source gradients pending.','All5strings are native editable richtext; no outlined lettering.']);(R/'CANVA_PACKAGE.json').write_text(json.dumps(pkg));(R/'QA.json').write_text(json.dumps(dict(stage='LOCAL_CANDIDATE_PENDING_CANVA',shapeAudit=cb.audit,textGeometry=textgeom,gradients='PENDING',all84complete=False),indent=2));print(json.dumps(dict(shapes=len(cb.audit)+1,nativeTexts=len(fits),minimumGeometryIoU=min(x['mask_iou']for x in cb.audit))))
