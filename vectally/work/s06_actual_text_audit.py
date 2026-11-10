from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
from pathlib import Path
import json,cv2,numpy as np
from PIL import Image,ImageDraw,ImageFont
r=Path('outputs/VECTALLY-story-repair/S06');src=Image.open(VSRC_+'/Story/VECTALLY_S06_Good_Records_Better_Decisions.png').convert('RGB');can=Image.open(r/'CANVA_ALL_NATIVE.png').convert('RGB');s=np.asarray(src);c=np.asarray(can);spec=[('VECTALLY',(106,50,408,110),'white'),('GOOD',(47,168,491,289),'white'),('RECORDS.',(48,289,741,410),'white'),('BETTER',(216,428,486,501),'white'),('DECISIONS.',(137,501,930,638),'green'),('Talk through what your',(45,1128,755,1195),'white'),('business needs.',(45,1196,670,1250),'white'),('LET’S TALK BOOKS.',(129,1305,823,1390),'navy')];out=[]
def mask(a,col):return (a.min(2)>190)if col=='white'else((a[:,:,0]<100)&(a[:,:,1]>175)&(a[:,:,1]>a[:,:,2]))if col=='green'else(a.max(2)<95)
for text,box,col in spec:
 x,y,xx,yy=box;sm=mask(s[y:yy,x:xx],col);cm=mask(c[y:yy,x:xx],col);iou=float((sm&cm).sum()/max(1,(sm|cm).sum()));b=cv2.boundingRect(cm.astype('uint8'));best=(iou,0,0)
 for dx in range(-8,9):
  for dy in range(-8,9):
   mm=cv2.warpAffine(cm.astype('uint8'),np.array([[1,0,dx],[0,1,dy]],dtype='float32'),(xx-x,yy-y))>0;score=float((sm&mm).sum()/max(1,(sm|mm).sum()))
   if score>best[0]:best=(score,dx,dy)
 out.append(dict(text=text,actualToSourceIoU=iou,actualInkBox=[b[0]+x,b[1]+y,b[2],b[3]],bestTranslation=dict(iou=best[0],dx=best[1],dy=best[2]),gate='NOT_1_TO_1'))
(r/'ACTUAL-TEXT-AUDIT.json').write_text(json.dumps(out,indent=2));sheet=Image.new('RGB',(1902,1742),'#e7edf4');d=ImageDraw.Draw(sheet);f=ImageFont.truetype(REPORT_FONT_,23);d.text((12,15),'S06 SOURCE',font=f,fill='#091522');d.text((973,15),'S06 ACTUAL CANVA - ALL COPY NATIVE, FIDELITY PENDING',font=f,fill='#091522');sheet.paste(src,(0,70));sheet.paste(can,(961,70));sheet.save(r/'CONTACT-SOURCE-CANVA.png');print(json.dumps(out),flush=True)
