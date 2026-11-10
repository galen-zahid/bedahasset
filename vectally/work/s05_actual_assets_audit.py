from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import cv2,numpy as np,json
r=Path('outputs/VECTALLY-story-repair/S05');src=np.asarray(Image.open(VSRC_+'/Story/VECTALLY_S05_Got_A_Bookkeeping_Question.png').convert('RGB'));a=np.asarray(Image.open(r/'CANVA_ASSETS_BODY.png').convert('RGB'));assert src.shape==a.shape==(1672,941,3)
boxes=[('Bingkai kanan',(390,310,905,600),'dark'),('Bingkai kiri',(25,1135,270,1400),'purple'),('Aksen logo',(90,125,305,165),'green'),('Aksen QUESTION',(380,1335,900,1435),'green'),('Body native',(590,1420,920,1500),'dark')];sheet=Image.new('RGB',(1500,1100),'#e7edf4');d=ImageDraw.Draw(sheet);font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',20);rows=[]
def mask(im,fam):
 if fam=='dark':return np.all(im<90,axis=2)
 if fam=='green':return(im[:,:,1]>110)&(im[:,:,0]<100)&(im[:,:,2]>70)&(im[:,:,2]<210)
 return(im[:,:,2].astype(int)-im[:,:,0]>25)&(im[:,:,0]>110)
for i,(name,(x,y,xx,yy),fam)in enumerate(boxes):
 sm=mask(src[y:yy,x:xx],fam);nm=mask(a[y:yy,x:xx],fam);score=float((sm&nm).sum()/(sm|nm).sum());rows.append(dict(asset=name,geometry_iou=score,kind='native_body_font_candidate'if i==4 else'whole_native_shape'))
 for col,im in enumerate([src,a]):
  p=Image.fromarray(im[y:yy,x:xx]);p.thumbnail((700,165));sheet.paste(p,(20+col*750,45+i*215));d.text((20+col*750,10+i*215),name+' | '+('SUMBER'if col==0 else'CANVA')+f' | IoU {score:.4f}',font=font,fill='#091522')
sheet.save(r/'CONTACT-SHEET-ASSETS-BODY-CANVA.png');(r/'ACTUAL-ASSET-AUDIT.json').write_text(json.dumps(dict(stage='INCOMPLETE_PAGE_ASSETS_ONLY_VERIFIED',dimensions=[941,1672],native_shapes=5,native_text=1,displayHeadlines='NOT_INSERTED',rows=rows,all84_complete=False),indent=2));print(json.dumps(rows))
