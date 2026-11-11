"""Uji League Gothic italic (dimiringkan lokal sebagai perkiraan) dan Asap bold italic untuk copy S03."""
import glob, json, sys
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent))
import s01_s05_display_fit as F
DARK = F.DARK
ITEMS = [("WHICH",(25,75,165,122)),("REPORT",(22,110,208,165)),("SHOWS",(135,140,368,240)),("PROFIT?",(12,435,368,552)),("OR",(165,320,205,348)),("PROFIT &",(55,262,148,292)),("LOSS",(55,287,112,314)),("BALANCE",(236,266,335,296)),("SHEET",(234,287,302,313))]
lg = F.var(F.FONTS/"leaguegothic-LeagueGothic[wdth].ttf",[100])
SHEAR = {}
C = {"Asap bold italic":F.CANDS["Asap bold italic"],"Asap Condensed bold":F.CANDS["Asap Condensed bold"]}
for s in (0.14,0.2,0.26):
    f = (lambda size: lg(size)); SHEAR[f]=s; C[f"League Gothic italic {s}"]=f
orig = F.render
def render(make,text,ls):
    img = orig(make,text,ls); s = SHEAR.get(make)
    return img.transform(img.size,Image.AFFINE,(1,s,-s*img.size[1]/2,0,1,0),Image.BILINEAR) if s else img
F.render = render; F.CANDS = C
rgb = np.array(Image.open(glob.glob(str(F.ROOT/"sources/VECTALLY/Story/*S03_*"))[0]).convert("RGB"))
out=[]
for t,roi in ITEMS:
    m=F.source_mask(rgb,roi,DARK)
    if not m.any(): print(t,"NO INK"); continue
    tg,b=F.crop(m); h=np.array(Image.fromarray(tg).resize((max(1,tg.shape[1]//2),max(1,tg.shape[0]//2)),Image.BILINEAR))>0
    r=F.fit(h,t,0); out.append({"text":t,"inkBox":[int(x) for x in b],"fits":r})
    print(t.ljust(9),[int(x) for x in b]," | ".join(f"{k.replace('League Gothic italic','LGi')} {v['iou']:.3f} a{v['angleCcw']} ls{v['ls']} s{v['fontSize']}" for k,v in sorted(r.items(),key=lambda kv:-kv[1]['iou'])))
(F.ROOT/"outputs/VECTALLY-story-repair/S03-ITALIC-FIT.json").write_text(json.dumps(out,indent=1),encoding="utf-8")
