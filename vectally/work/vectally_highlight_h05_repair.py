from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
from normalize_native_package import normalize_package
"""H05: explicit semantic ownership and whole transparent compound contours."""
from pathlib import Path
import gzip,hashlib,io,json
import cv2,numpy as np
from PIL import Image,ImageDraw,ImageFont
import resvg_py
from native_contour_path import native_component,render_shape

SOURCE=next(Path(VSRC_+'/Highlight').glob('VECTALLY_H05_*.png'))
OUT=Path('outputs/VECTALLY-highlight-repair/H05');OUT.mkdir(parents=True,exist_ok=True)
im=np.array(Image.open(SOURCE).convert('RGB'));h,w=im.shape[:2];a=im.astype(float)
def components(mask):
    n,l,s,c=cv2.connectedComponentsWithStats(mask.astype('uint8'))
    return l,{tuple(map(int,s[i,:4])):(i,s[i]) for i in range(1,n) if s[i,4]>1000}
purple,p=components((a[:,:,2]>120)&(a[:,:,0]>75)&(a[:,:,1]<210)&(a[:,:,2]>a[:,:,0]*1.1))
white,q=components(a.min(2)>170)
green,g=components((a[:,:,0]<90)&(a[:,:,1]>100)&(a[:,:,2]>65))
doc_bounds=[(109,379,232,274),(151,462,95,21),(151,505,115,21),(253,512,77,98),(151,547,70,22),(221,589,140,64)]
arrow_bounds=(354,541,159,173)
assert set(p)==set(doc_bounds+[arrow_bounds])
assert set(q)=={(307,730,339,470)}
assert len(g)==6
definitions=[
 ('IMPORT','Dokumen impor, isi dan tanda unduh',purple,[p[b] for b in doc_bounds],['document','download_symbol']),
 ('ARROW1','Konektor proses atas utuh',purple,[p[arrow_bounds]],['connector']),
 ('EVALUATION','Neraca dan konektor tindak lanjut yang tersambung',white,list(q.values()),['scale','attached_connector']),
 ('CHECKLIST','Clipboard, daftar dan lencana verifikasi',green,list(g.values()),['clipboard','status_badge']),
]
bg='#%02x%02x%02x'%tuple(np.median(im[10:100,10:100],axis=(0,1)).astype(int))
elements=[dict(type='shape',name='Latar kandidat: gradasi sumber belum dipulihkan',left=0,top=0,width=w,height=h,
               viewBox=dict(left=0,top=0,width=w,height=h),paths=[dict(d=f'M0 0H{w}V{h}H0Z',fill=dict(color=bg))])]
svg=[render_shape(elements[0])];inventory=[];all_geometry=[]
for asset_id,name,labels,entries,roles in definitions:
    children=[];parts=[]
    for number,(idx,stats) in enumerate(entries):
        mask=(labels==idx).astype('uint8');interior=cv2.erode(mask,np.ones((3,3),np.uint8))>0
        color='#%02x%02x%02x'%tuple(np.rint(np.median(im[interior],axis=0)).astype(int))
        node,meta=native_component(mask,color,f'{asset_id} kontur utuh {number+1}')
        # Refine the three thin symbols that failed the unchanged geometry gate.
        # Each remains a single native path and keeps its explicit parent asset.
        if tuple(map(int,stats[:4])) in {(253,512,77,98),(605,1111,59,47),(605,1170,59,46)}:
            refinements=json.loads((OUT/'SMALL-COMPONENT-REPAIR.json').read_text())
            fit=next(r for r in refinements if r['bbox']==list(map(int,stats[:4])))
            assert fit['iou']>=.985 and fit['path_bytes']<=1850
            bx0,by0,bw0,bh0=fit['bbox'];dx0,dy0=fit['offset']
            node.update(left=bx0+dx0,top=by0+dy0,width=bw0,height=bh0,
                viewBox=dict(left=0,top=0,width=bw0,height=bh0),
                paths=[dict(d=fit['path'],fill=dict(color=color))])
            meta.update(path_bytes=fit['path_bytes'],epsilon=fit['epsilon'],holes=0,
                contour_sampling=fit['scale'],points=fit['path'].count(' '),
                refinement='subpixel contour boundary fit, whole component')
        # Verify rendered SVG topology. Calibrate subpixel placement against the
        # source rather than lowering the acceptance gate for thin outlines.
        bx,by,bw,bh=map(int,stats[:4]);pad=3
        target=mask[by-pad:by+bh+pad,bx-pad:bx+bw+pad]>0
        original_left=node['left'];original_top=node['top'];best=(-1,0,0)
        for dx in np.arange(-.5,.501,.125):
            for dy in np.arange(-.5,.501,.125):
                node['left']=original_left+float(dx);node['top']=original_top+float(dy)
                markup=f'<svg xmlns="http://www.w3.org/2000/svg" width="{bw+pad*2}" height="{bh+pad*2}" viewBox="{bx-pad} {by-pad} {bw+pad*2} {bh+pad*2}">{render_shape(node)}</svg>'
                png=resvg_py.svg_to_bytes(svg_string=markup)
                rendered=np.array(Image.open(io.BytesIO(png)).convert('RGBA'))[:,:,3]>=128
                score=float((rendered&target).sum()/(rendered|target).sum())
                if score>best[0]:best=(score,float(dx),float(dy))
        score,dx,dy=best;node['left']=original_left+dx;node['top']=original_top+dy
        meta['mask_iou']=score;meta['subpixel_translation']=[dx,dy]
        meta['local_geometry_gate']='PASS' if score>=.985 else 'FAIL_REQUIRES_MORE_ALIGNMENT'
        meta['source_bbox']=list(map(int,stats[:4]));meta['color']=color
        children.append(node);parts.append(meta);svg.append(render_shape(node));all_geometry.append(meta)
    x=min(n['left'] for n in children);y=min(n['top'] for n in children)
    xx=max(n['left']+n['width'] for n in children);yy=max(n['top']+n['height'] for n in children)
    for n in children:n['left']-=x;n['top']-=y
    elements.append(dict(type='group',name=f'{asset_id} - {name}',left=x,top=y,width=xx-x,height=yy-y,children=children))
    inventory.append(dict(id=asset_id,name=name,kind='semantic_assembly',roles=roles,parts=parts,
                          ownership='explicit_observed_source_component_bounds',joined_strokes_not_split=True))
package=dict(format='cusbe-canva-package',version=2,source='H05 - KONTUR UTUH PER UNIT PROSES',width=w,height=h,
             elements=elements,summary=dict(shape=1+len(all_geometry),group=4,text=0,image=0),
             warnings=['Local candidate only; actual Canva import/export and buyer editing are not tested.',
                       'Background and subtle source color gradients remain unresolved.',
                       'Scale and its attached connector form one editable assembly so their continuous stroke is not cut.'])
package=normalize_package(package)
raw=json.dumps(package,ensure_ascii=False).encode('utf8')
(OUT/'CANVA_PACKAGE.json').write_bytes(raw);(OUT/'package.gz').write_bytes(gzip.compress(raw))
doc=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'+''.join(svg)+'</svg>'
(OUT/'preview.svg').write_text(doc,encoding='utf8');(OUT/'preview.png').write_bytes(resvg_py.svg_to_bytes(svg_string=doc))
(OUT/'inventory.json').write_text(json.dumps(dict(source=str(SOURCE),sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    objects=inventory,group_count_is_not_claimed_as_physical_object_count=True,nearest_object_assignment=False),ensure_ascii=False,indent=2),encoding='utf8')
(OUT/'QA.json').write_text(json.dumps(dict(stage='LOCAL_REPAIR_REQUIRES_CANVA_IMPORT_AND_EXPORT',
    structure='LOCAL_SVG_TOPOLOGY_VERIFIED',visual='NOT_1_TO_1_GRADIENTS_UNRESOLVED',buyer='NOT_TESTED',
    geometry_gates=[i['local_geometry_gate'] for i in all_geometry],
    minimum_component_mask_iou=min(i['mask_iou'] for i in all_geometry),transparent_holes=sum(i['holes'] for i in all_geometry),
    single_move_paths=True,body_tiling=False,**package['summary']),indent=2),encoding='utf8')
font=ImageFont.truetype(REPORT_FONT_,24);sheet=Image.new('RGB',(1000,980),'#e7edf4');draw=ImageDraw.Draw(sheet)
for j,(label,path) in enumerate([('SUMBER',SOURCE),('KONTUR UTUH + LUBANG TRANSPARAN',OUT/'preview.png')]):
    draw.text((20+j*500,20),label,font=font,fill='#091522');pic=Image.open(path).convert('RGB');pic.thumbnail((460,880));sheet.paste(pic,(20+j*500,70))
sheet.save(OUT/'CONTACT-SHEET.png')
print(json.dumps(dict(shapes=package['summary']['shape'],assemblies=4,min_iou=min(i['mask_iou'] for i in all_geometry),holes=sum(i['holes'] for i in all_geometry)),indent=2))
