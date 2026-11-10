from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import numpy as np,json
r=Path('outputs/VECTALLY-story-repair');sources={'S01':'The_Books_Tell_A_Story','S02':'Whats_Harder_To_Track','S03':'Which_Report_Shows_Profit','S04':'Its_The_Profit_And_Loss'};actual={'S01':'CANVA_FLOW_REPAIRED_NORMAL_COPY.png','S02':'CANVA_WHITE_NATIVE.png','S03':'CANVA_ASSETS.png','S04':'CANVA_NORMAL_COPY.png'};font=ImageFont.truetype(REPORT_FONT_,17)
for ids in [('S01','S02'),('S03','S04')]:
 sheet=Image.new('RGB',(980,1800),'#e7edf4');d=ImageDraw.Draw(sheet)
 for row,sid in enumerate(ids):
  src=Image.open(VSRC_+'/Story/VECTALLY_'+sid+'_'+sources[sid]+'.png').convert('RGB');can=Image.open(r/sid/actual[sid]).convert('RGB');assert src.size==can.size==(941,1672)
  yy=row*900;d.text((10,yy+8),sid+' SOURCE',font=font,fill='#091522');d.text((500,yy+8),sid+' CANVA PROTOTYPE - HEADLINES PENDING',font=font,fill='#091522');sheet.paste(src.resize((470,836),Image.Resampling.LANCZOS),(10,yy+44));sheet.paste(can.resize((470,836),Image.Resampling.LANCZOS),(500,yy+44))
 sheet.save(r/('CONTACT-SOURCE-CANVA-'+ids[0]+'-'+ids[1]+'.png'))
for sid in ['S03','S04']:
 local=np.asarray(Image.open(r/sid/'assets.png').convert('RGB')).astype(float);can=np.asarray(Image.open(r/sid/actual[sid]).convert('RGB')).astype(float);mask=np.ones(local.shape[:2],bool)
 if sid=='S04':mask[895:973,25:914]=False;mask[1420:1620,40:920]=False
 mae=float(np.abs(local-can)[mask].mean());j=json.loads((r/sid/('CANVA_NORMAL_COPY_STRUCTURE.json'if sid=='S04'else'CANVA_STRUCTURE.json')).read_text());rec=dict(stage='ASSET_PROTOTYPE_NOT_FINISHED_PAGE',actualNative=j['breakdown'],localToNativeCanvaShapeAreaMAE=mae,maskScope='all non-copy pixels; S04 captions/body excluded',sourceVisualFidelity='NOT_PASSED: headlines, gradients, exact requested typeform and final buyer QA pending',wholeBody='visually inspected on contrasting pink per-group isolation sheet; no connector-shaped paper bites or transparent internal gaps',all84Complete=False);(r/sid/'ACTUAL-EXPORT-AUDIT.json').write_text(json.dumps(rec,indent=2));print(sid,mae,flush=True)
