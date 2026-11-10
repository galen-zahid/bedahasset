from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
from pathlib import Path
import json,math
import cv2,numpy as np
from PIL import Image,ImageDraw,ImageFont
r=Path('outputs/VECTALLY-story-repair/S06');F=Path('outputs/VECTALLY-teks-native/fonts');a=np.asarray(Image.open(VSRC_+'/Story/VECTALLY_S06_Good_Records_Better_Decisions.png').convert('RGB'));spec=[('VECTALLY','Archivo Black',(106,50,400,108),46,56,'white'),('GOOD','Asap',(47,168,491,289),135,160,'white'),('RECORDS.','Asap',(48,289,741,410),135,160,'white'),('BETTER','Asap',(216,428,486,498),65,84,'white'),('DECISIONS.','Asap',(137,501,930,636),139,166,'green'),('Talk through what your','Asap',(50,1128,755,1195),53,65,'white'),('business needs.','Asap',(50,1196,670,1250),53,65,'white'),('LET’S TALK BOOKS.','Asap',(129,1305,823,1389),63,80,'navy')];out=[];records=[]
for text,family,box,lo,hi,color in spec:
 x0,y0,x1,y1=box;crop=a[y0:y1,x0:x1];target=((crop.min(2)>190)if color=='white'else((crop[:,:,0]<100)&(crop[:,:,1]>175)&(crop[:,:,1]>crop[:,:,2]))if color=='green'else(crop.max(2)<95)).astype('float32');best=None;file=F/('archivoblack-ArchivoBlack-Regular.ttf'if family=='Archivo Black'else'asap-Asap[wdth,wght].ttf')
 for size in np.arange(lo,hi+.01,.5):
  font=ImageFont.truetype(str(file),float(size)*2)
  if family=='Asap':font.set_variation_by_axes([900 if text in ['GOOD','RECORDS.','BETTER','DECISIONS.','LET’S TALK BOOKS.']else 400,100])
  for tr in np.arange(-.02,.0601 if family=='Asap'and text in ['Talk through what your','business needs.']else .0201,.005):
   wid=math.ceil(font.getlength(text)+max(0,(len(text)-1)*tr*size*2))+40;hei=math.ceil(size*4+40);raw=Image.new('L',(wid,hei));draw=ImageDraw.Draw(raw)
   for i,ch in enumerate(text):draw.text((12+font.getlength(text[:i+1])-font.getlength(ch)+i*tr*size*2,0),ch,font=font,fill=255)
   raw=raw.resize((wid//2,hei//2),Image.Resampling.LANCZOS);arr=np.asarray(raw);bb=cv2.boundingRect((arr>127).astype('uint8'));xx,yy,w,h=bb
   if not w or h>target.shape[0]or w>target.shape[1]:continue
   ink=(arr[yy:yy+h,xx:xx+w]>127).astype('float32');mt=cv2.matchTemplate(target,ink,cv2.TM_CCORR);_,inter,_,loc=cv2.minMaxLoc(mt);iou=inter/max(1,target.sum()+ink.sum()-inter)
   if best is None or iou>best[0]:best=(float(iou),float(size),float(tr),bb,loc)
 if best is None:raise RuntimeError(text)
 score,size,tr,bb,loc=best;px=x0+loc[0];py=y0+loc[1];el=dict(type='text',name='S06 - '+text,text=text,fontFamily=family,fontRef='YACgEZulLoA:0'if family=='Archivo Black'else'YAFdJr0OaFw:0',fontSize=size,left=round(px-bb[0]+6,3),top=round(py-bb[1]-.045*size,3),width=float(bb[2]+12),color='#f4f7fa'if color=='white'else'#00df9f'if color=='green'else'#091522',fontWeight='heavy'if text in ['GOOD','RECORDS.','BETTER','DECISIONS.','LET’S TALK BOOKS.']else'normal',fontStyle='normal',letterSpacingEm=tr,lineHeightEm=1)
 out.append(el);record=dict(text=text,localIoU=score,fontSize=size,tracking=tr,fitInkBox=[px,py,bb[2],bb[3]],targetInkBox=[x0+cv2.boundingRect(target.astype('uint8'))[0],y0+cv2.boundingRect(target.astype('uint8'))[1],*cv2.boundingRect(target.astype('uint8'))[2:]],stage='LOCAL_FONT_FIT_ACTUAL_CANVA_REQUIRED');records.append(record);print(json.dumps(record),flush=True)
p=dict(format='cusbe-canva-package',version=1,source='S06 - NATIVE COPY CANDIDATE',width=941,height=1672,elements=out,summary=dict(shape=0,group=0,text=len(out),image=0),warnings=['Requested Archivo Black and Asap; exact actual font shape fidelity pending.'])
(r/'NATIVE_COPY_PACKAGE.json').write_text(json.dumps(p));(r/'NATIVE-COPY-LOCAL-FIT.json').write_text(json.dumps(records,indent=2))
