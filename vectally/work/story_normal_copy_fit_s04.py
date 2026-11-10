from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
from pathlib import Path
import json,math
import cv2,numpy as np
from PIL import Image,ImageDraw,ImageFont
F=Path('outputs/VECTALLY-teks-native/fonts')
specs=[('S01','VECTALLY','Archivo Black',(40,90,340,150),45,55,False,False),('S01','TELL A','Asap',(390,738,628,808),60,80,True,False),('S01','Make sense of','Asap',(77,1365,352,1410),39,48,False,False),('S01','the numbers','Asap',(77,1410,355,1460),39,48,False,False),('S01','behind your','Asap',(77,1458,355,1505),39,48,False,False),('S01','business.','Asap',(77,1504,355,1553),39,48,False,False),('S02','VECTALLY','Archivo Black',(45,45,365,108),45,60,False,False),('S02','INVOICE','Asap',(617,1002,808,1053),40,52,True,True),('S02','OPEN PAYMENT','Asap',(669,1246,883,1288),26,37,True,False),('S02','EXPENSES','Asap',(125,1522,400,1584),45,60,True,False),('S02','UNPAID','Asap',(602,1494,800,1548),43,58,True,False),('S02','INVOICES','Asap',(580,1548,827,1603),43,58,True,False)]
specs.extend([('S04','REVENUE','Asap',(65,911,278,955),32,45,True,False),('S04','EXPENSES','Asap',(365,911,590,955),32,45,True,False),('S04','RESULT','Asap',(684,911,893,955),32,45,True,False),('S04','A P&L summarizes revenue,','Asap',(53,1438,730,1501),49,61,False,False),('S04','expenses, and profit or loss','Asap',(53,1494,734,1554),49,61,False,False),('S04','over a period.','Asap',(53,1550,426,1615),49,61,False,False)])
imgs={'S01':np.asarray(Image.open(VSRC_+'/Story/VECTALLY_S01_The_Books_Tell_A_Story.png').convert('RGB')),'S02':np.asarray(Image.open(VSRC_+'/Story/VECTALLY_S02_Whats_Harder_To_Track.png').convert('RGB'))};imgs['S04']=np.asarray(Image.open(VSRC_+'/Story/VECTALLY_S04_Its_The_Profit_And_Loss.png').convert('RGB'));out={s:[]for s in imgs};records={s:[]for s in imgs}
for sid,text,family,box,lo,hi,bold,italic in specs:
 a=imgs[sid];x0,y0,x1,y1=box;crop=a[y0:y1,x0:x1];target=((crop.min(2)>190)if ((sid=='S01'and text!='TELL A')or(sid=='S02'and text in ['UNPAID','INVOICES']))else(crop.max(2)<95)).astype('float32');best=None
 file=F/('archivoblack-ArchivoBlack-Regular.ttf'if family=='Archivo Black'else('asap-Asap-Italic[wdth,wght].ttf'if italic else'asap-Asap[wdth,wght].ttf'))
 for size in np.arange(lo,hi+.01,.5):
  font=ImageFont.truetype(str(file),float(size)*2)
  if family=='Asap':font.set_variation_by_axes([700 if bold else 400,100])
  for tr in np.arange(-.02,.0201,.005):
   raw=Image.new('L',(1300,260));draw=ImageDraw.Draw(raw)
   for i,ch in enumerate(text):draw.text((12+font.getlength(text[:i])+i*tr*size*2,0),ch,font=font,fill=255)
   raw=raw.resize((650,130),Image.Resampling.LANCZOS);arr=np.asarray(raw);bb=cv2.boundingRect((arr>127).astype('uint8'));xx,yy,w,h=bb
   if not w or h>target.shape[0]or w>target.shape[1]:continue
   ink=(arr[yy:yy+h,xx:xx+w]>127).astype('float32');mt=cv2.matchTemplate(target,ink,cv2.TM_CCORR);_,inter,_,loc=cv2.minMaxLoc(mt);iou=inter/max(1,target.sum()+ink.sum()-inter)
   if best is None or iou>best[0]:best=(float(iou),float(size),float(tr),bb,loc,ink)
 if best is None:raise RuntimeError(text)
 score,size,tr,bb,loc,ink=best;px=x0+loc[0];py=y0+loc[1];offset=.045*size;left=px-bb[0]+6;top=py-bb[1]-offset
 el=dict(type='text',name=sid+' - '+text,text=text,fontFamily=family,fontRef='YACgEZulLoA:0'if family=='Archivo Black'else'YAFdJr0OaFw:0',fontSize=size,left=round(left,3),top=round(top,3),width=float(bb[2]+12),color='#f4f7fa'if ((sid=='S01'and text!='TELL A')or(sid=='S02'and text in ['UNPAID','INVOICES']))else'#091522',fontWeight='bold'if bold else'normal',fontStyle='italic'if italic else'normal',letterSpacingEm=tr,lineHeightEm=1)
 out[sid].append(el);record=dict(text=text,localIoU=score,fontSize=size,tracking=tr,sourceInk=[px,py,bb[2],bb[3]],stage='LOCAL_FIT_ACTUAL_CANVA_REQUIRED');records[sid].append(record);print(json.dumps(record),flush=True)
for sid,elements in out.items():
 r=Path('outputs/VECTALLY-story-repair')/sid;pkg=dict(format='cusbe-canva-package',version=1,source=sid+' - NATIVE NORMAL COPY CANDIDATE',width=941,height=1672,elements=elements,summary=dict(text=len(elements),shape=0,group=0,image=0),warnings=['Normal copy only; display headlines pending','Local font fit; actual native alignment and font mapping must be verified'])
 (r/'NATIVE_NORMAL_COPY.json').write_text(json.dumps(pkg));(r/'NORMAL-COPY-LOCAL-FIT.json').write_text(json.dumps(records[sid],indent=2))
