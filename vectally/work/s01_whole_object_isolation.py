from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
from pathlib import Path
from copy import deepcopy
from PIL import Image,ImageDraw,ImageFont
import json,io,resvg_py
from native_component_builder import render_node
r=Path('outputs/VECTALLY-story-repair/S01');p=json.loads((r/'ASSETS_PACKAGE.json').read_text());sheet=Image.new('RGB',(1500,1030),'#e7edf4');d=ImageDraw.Draw(sheet);font=ImageFont.truetype(REPORT_FONT_,22)
for i,e in enumerate([x for x in p['elements']if x['type']=='group']):
 e=deepcopy(e);x=e['left'];y=e['top'];w=e['width'];h=e['height'];svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w+16}" height="{h+16}" viewBox="{x-8} {y-8} {w+16} {h+16}"><rect x="{x-8}" y="{y-8}" width="{w+16}" height="{h+16}" fill="#ff78ba"/>'+render_node(e)+'</svg>';im=Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert('RGB');im.thumbnail((460,420));cx=(i%3)*500+20;cy=(i//3)*510+60;sheet.paste(im,(cx,cy));d.text((cx,cy-40),['DOC1','DOC2','DOC3','DOC4','BOOK'][i]+' | SATU GRUP',font=font,fill='#091522')
sheet.save(r/'WHOLE-OBJECT-ISOLATION.png');print('saved')
