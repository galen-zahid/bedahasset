"""Paket S03 dengan copy yang tercapai native. Headline besar sengaja belum dipasang."""
import json
from pathlib import Path
from PIL import ImageFont
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"outputs/VECTALLY-story-repair"; FONTS=ROOT/"outputs/VECTALLY-teks-native/fonts"
fit={r["text"]:r for r in json.loads((R/"S03-ITALIC-FIT.json").read_text(encoding="utf-8"))}
base=[r for r in json.loads((R/"DISPLAY-FIT.json").read_text(encoding="utf-8")) if r["code"]=="S03" and r["text"]=="VECTALLY"][0]
A=("Asap","YAFdJr0OaFw:0","bold","italic","asap-Asap-Italic[wdth,wght].ttf",[700,100])
B=("Archivo Black","YACgEZulLoA:0","normal","normal","archivoblack-ArchivoBlack-Regular.ttf",None)
C=("Asap Condensed","YAD1fmY3NpE:0","bold","normal","asap-Asap[wdth,wght].ttf",[700,75])
def make(text,face,box,size,ls,ang):
    f=ImageFont.truetype(str(FONTS/face[4]),200)
    if face[5]: f.set_variation_by_axes(face[5])
    w=round(f.getlength(text)*size/200+ls*size*len(text)+24)
    cx,cy=(box[0]+box[2])/2,(box[1]+box[3])/2
    e={"type":"text","name":f"S03 - {text} native","text":text,"fontFamily":face[0],"fontRef":face[1],"fontSize":size,"left":round(cx-(w-24)/2,2),"top":round(cy-size/2-0.11*size,2),"width":w,"color":"#091522","fontWeight":face[2],"fontStyle":face[3],"letterSpacingEm":ls,"lineHeightEm":1}
    if ang: e["rotation"]=-ang
    return e
g=lambda t,k:fit[t]["fits"][k]
ab="Asap bold italic"; h=lambda v:round(v*2)/2
items={"PROFIT &":make("PROFIT &",A,fit["PROFIT &"]["inkBox"],h(g("PROFIT &",ab)["fontSize"]),g("PROFIT &",ab)["ls"],g("PROFIT &",ab)["angleCcw"]),
"LOSS":make("LOSS",A,fit["LOSS"]["inkBox"],h(g("LOSS",ab)["fontSize"]),g("LOSS",ab)["ls"],g("LOSS",ab)["angleCcw"]),
"SHEET":make("SHEET",A,fit["SHEET"]["inkBox"],h(g("SHEET",ab)["fontSize"]),g("SHEET",ab)["ls"],g("SHEET",ab)["angleCcw"]),
"BALANCE":make("BALANCE",A,[586,664,819,722],h(g("SHEET",ab)["fontSize"]),0,g("SHEET",ab)["angleCcw"]),
"OR":make("OR",C,fit["OR"]["inkBox"],h(g("OR","Asap Condensed bold")["fontSize"]),0,g("OR","Asap Condensed bold")["angleCcw"]),
"VECTALLY":make("VECTALLY",B,base["inkBox"],h(base["fits"]["Archivo Black"]["fontSize"]),-0.04,0)}
json.dump(items,open(R/"S03/_partial_text.json","w",encoding="utf-8"),ensure_ascii=False,indent=0)
for k,v in items.items(): print(k,v["fontSize"],v["left"],v["top"],v["width"],v.get("rotation",0))
