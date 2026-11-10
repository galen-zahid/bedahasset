from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
import json,io
from pathlib import Path
from copy import deepcopy
from PIL import Image,ImageDraw,ImageFont
import resvg_py
from native_component_builder import render_node
r=Path('outputs/VECTALLY-story-repair');sheet=Image.new('RGB',(1500,1120),'#e7edf4');d=ImageDraw.Draw(sheet);font=ImageFont.truetype(REPORT_FONT_,20)
for row,sid in enumerate(['S03','S04']):
 p=json.loads((r/sid/'ASSETS_PACKAGE.json').read_text());groups=[e for e in p['elements']if e['type']=='group']
 for col,g in enumerate(groups):
  g=deepcopy(g);g['left']=20;g['top']=55;svg='<svg xmlns="http://www.w3.org/2000/svg" width="490" height="545"><rect width="490" height="545" fill="#ff6dc2"/>'+render_node(g)+'</svg>';img=Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert('RGB');sheet.paste(img,(col*500,row*560));d.text((col*500+10,row*560+12),sid+' | '+g['name'][:32],font=font,fill='#091522')
sheet.save(r/'WHOLE-OBJECT-S03-S04.png');print('saved')