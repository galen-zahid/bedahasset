from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
from normalize_native_package import normalize_package
"""Targeted H06 contour repair, reusing the current native shape package format.

Ownership is audited explicitly: one frame, two person icons, one speech bubble.
The frame is the intentionally interrupted contour visible in the source, not
separate color fragments or a background-colored patch over a broken rectangle.
"""
from pathlib import Path
import gzip, hashlib, json
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import resvg_py
from vectally_collection import shape, svg_shape

SOURCE=next(Path(VSRC_+'/Highlight').glob('VECTALLY_H06_*.png'))
OUT=Path('outputs/VECTALLY-highlight-repair/H06')
OUT.mkdir(parents=True,exist_ok=True)
im=np.array(Image.open(SOURCE).convert('RGB'))
h,w=im.shape[:2]

def components(mask):
    n,labels,stats,centroids=cv2.connectedComponentsWithStats(mask.astype('uint8'))
    return labels,[(i,stats[i],centroids[i]) for i in range(1,n) if stats[i,4]>100]

dark,ds=components(im.max(2)<90)
purple,ps=components((im[:,:,2]>180)&(im[:,:,0]>110)&(im[:,:,1]<200)&(im[:,:,2]>im[:,:,0].astype(float)*1.15))
green,gs=components((im[:,:,0]<90)&(im[:,:,1]>130)&(im[:,:,2]>70))
assert len(ds)==3 and len(ps)==1 and len(gs)==2

def part(labels,entry,name):
    idx,stats,centroid=entry
    mask=(labels==idx).astype('uint8')
    contours,hierarchy=cv2.findContours(mask,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    assert len(contours)==1, (name,'Unexpected holes/components')
    contour=contours[0]
    # Keep a full closed contour, never split into path-length tiles.
    eps=.45
    while True:
        pts=cv2.approxPolyDP(contour,eps,True).reshape(-1,2)
        d='M'+' L'.join(f'{x} {y}' for x,y in pts)+' Z'
        if len(d.encode())<1850:break
        eps+=.1
    interior=cv2.erode(mask,np.ones((5,5),np.uint8))>0
    rgb=np.rint(np.median(im[interior],axis=0)).astype(int)
    color='#%02x%02x%02x'%tuple(rgb)
    node=shape(d,color,name)
    reconstructed=np.zeros(mask.shape,np.uint8)
    cv2.fillPoly(reconstructed,[pts],1)
    iou=float(((reconstructed>0)&(mask>0)).sum()/((reconstructed>0)|(mask>0)).sum())
    return node,dict(name=name,bbox=list(map(int,stats[:4])),source_component=idx,
                     points=len(pts),path_bytes=len(d.encode()),contour_epsilon=eps,
                     color=color,mask_iou=iou,body_tiling=False,closed=True)

# Explicit component identity is checked against observed source bounds.
ds.sort(key=lambda a:-int(a[1][4]))
frame_entry=ds[0]
assert tuple(frame_entry[1][:4])==(125,581,690,668)
left_entries=sorted(ds[1:],key=lambda a:int(a[1][1]))
right_entries=sorted(gs,key=lambda a:int(a[1][1]))
definitions=[
 ('FRAME','Bingkai percakapan utuh',[(dark,frame_entry,'Kontur bingkai')]),
 ('PERSON1','Orang kiri: kepala dan badan',[(dark,left_entries[0],'Kepala kiri'),(dark,left_entries[1],'Badan kiri')]),
 ('PERSON2','Orang kanan: kepala dan badan',[(green,right_entries[0],'Kepala kanan'),(green,right_entries[1],'Badan kanan')]),
 ('BUBBLE','Balon percakapan dan ekornya',[(purple,ps[0],'Balon utuh')]),
]
bg='#%02x%02x%02x'%tuple(np.median(im[10:100,10:100],axis=(0,1)).astype(int))
background=shape(f'M0 0 L{w} 0 L{w} {h} L0 {h} Z',bg,'Latar kandidat: gradasi sumber belum dipulihkan')
elements=[background];svg=[svg_shape(background)];inventory=[]
for asset_id,name,entries in definitions:
    children=[];reports=[]
    for labels,entry,label in entries:
        node,report=part(labels,entry,label);children.append(node);reports.append(report);svg.append(svg_shape(node))
    x=min(n['left'] for n in children);y=min(n['top'] for n in children)
    x1=max(n['left']+n['width'] for n in children);y1=max(n['top']+n['height'] for n in children)
    for child in children:child['left']-=x;child['top']-=y
    elements.append(dict(type='group',name=f'{asset_id} - {name}',left=x,top=y,width=x1-x,height=y1-y,children=children))
    inventory.append(dict(id=asset_id,name=name,kind='physical_asset',parts=reports,
                          grouping='explicit_source_object',native_shapes=len(children),text_copy=False))

package=dict(format='cusbe-canva-package',version=2,source='H06 - KOREKSI KONTUR PER ASET',width=w,height=h,
             elements=elements,summary=dict(shape=7,text=0,group=4,image=0),
             warnings=['Background source has subtle variation; flat candidate is not a 1:1 final.',
                       'Local contour audit is not an actual Canva export or buyer-test pass.'])
package=normalize_package(package)
raw=json.dumps(package,ensure_ascii=False).encode('utf8')
(OUT/'CANVA_PACKAGE.json').write_bytes(raw);(OUT/'package.gz').write_bytes(gzip.compress(raw))
document=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'+''.join(svg)+'</svg>'
(OUT/'preview.svg').write_text(document,encoding='utf8')
(OUT/'preview.png').write_bytes(resvg_py.svg_to_bytes(svg_string=document))
(OUT/'inventory.json').write_text(json.dumps(dict(source=str(SOURCE),sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
     observed_objects=4,objects=inventory,all_source_copy='No text copy in this illustration',
     nearest_object_assignment=False),ensure_ascii=False,indent=2),encoding='utf8')
(OUT/'QA.json').write_text(json.dumps(dict(stage='LOCAL_REPAIR_REQUIRES_CANVA_IMPORT_AND_EXPORT',
     structure='LOCAL_NATIVE_PACKAGE_VALIDATED',visual='NOT_1_TO_1_BACKGROUND_VARIATION_UNRESOLVED',buyer='NOT_TESTED',
     per_asset_min_contour_iou={a['id']:min(p['mask_iou'] for p in a['parts']) for a in inventory},
     native_shapes=7,native_groups=4,raster_images=0,body_tiling=False),indent=2),encoding='utf8')
font=ImageFont.truetype(REPORT_FONT_,24)
sheet=Image.new('RGB',(1000,980),'#e7edf4');draw=ImageDraw.Draw(sheet)
for j,(label,path) in enumerate([('SUMBER',SOURCE),('KANDIDAT KONTUR UTUH',OUT/'preview.png')]):
    draw.text((20+j*500,20),label,font=font,fill='#091522')
    pic=Image.open(path).convert('RGB');pic.thumbnail((460,880));sheet.paste(pic,(20+j*500,70))
sheet.save(OUT/'CONTACT-SHEET.png')
print(json.dumps(dict(objects=4,shapes=7,groups=4,min_iou=min(p['mask_iou'] for a in inventory for p in a['parts'])),indent=2))
