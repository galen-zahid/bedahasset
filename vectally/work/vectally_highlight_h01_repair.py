from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
from normalize_native_package import normalize_package
from pathlib import Path
import json,gzip,hashlib,io
import cv2,numpy as np
from PIL import Image,ImageDraw,ImageFont
import resvg_py
from native_contour_path import native_component,render_shape
SOURCE=next(Path(VSRC_+'/Highlight').glob('VECTALLY_H01_*.png'));OUT=Path('outputs/VECTALLY-highlight-repair/H01');OUT.mkdir(parents=True,exist_ok=True);im=np.array(Image.open(SOURCE).convert('RGB'));a=im.astype(float);h,w=im.shape[:2]
def cc(mask):
 n,l,s,c=cv2.connectedComponentsWithStats(mask.astype('uint8'));return l,{tuple(map(int,s[i,:4])):i for i in range(1,n)if s[i,4]>1000}
dark,ds=cc(a.max(2)<80);white,ws=cc(a.min(2)>200);purple,ps=cc((a[:,:,0]>75)&(a[:,:,1]<210)&(a[:,:,2]>a[:,:,0]*1.1));green,gs=cc((a[:,:,0]<90)&(a[:,:,1]>100)&(a[:,:,2]>65))
def component(labels,index):return (labels==index).astype('uint8')
def fill_holes(mask):
 p=np.pad(mask,1);f=p.copy();cv2.floodFill(f,None,(0,0),2);return (f[1:-1,1:-1]!=2).astype('uint8')
def color_for(mask):
 interior=cv2.erode(mask,np.ones((3,3),np.uint8))>0
 return '#%02x%02x%02x'%tuple(np.rint(np.median(im[interior],axis=0)).astype(int))
allmeta=[]
def node(mask,name,color=None,holes_are_ink=False):
 original=mask.copy();mask=fill_holes(mask) if holes_are_ink else mask
 e,meta=native_component(mask,color or color_for(original),name);e['name']=name
 bx,by,bw,bh=cv2.boundingRect(mask);pad=3;t=mask[by-pad:by+bh+pad,bx-pad:bx+bw+pad]>0;origx=e['left'];origy=e['top'];best=(-1,0,0)
 for dx in np.arange(-.5,.501,.125):
  for dy in np.arange(-.5,.501,.125):
   e['left']=origx+float(dx);e['top']=origy+float(dy);svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{bw+6}" height="{bh+6}" viewBox="{bx-pad} {by-pad} {bw+6} {bh+6}">{render_shape(e)}</svg>';r=np.array(Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert('RGBA'))[:,:,3]>=128;s=float((r&t).sum()/(r|t).sum())
   if s>best[0]:best=(s,float(dx),float(dy))
 e['left']=origx+best[1];e['top']=origy+best[2];meta.update(name=name,source_bbox=[bx,by,bw,bh],mask_iou=best[0],local_geometry_gate='PASS' if best[0]>=.985 else 'FAIL_REQUIRES_ALIGNMENT',ink_holes_filled_in_parent_body=holes_are_ink,body_tiling=False);allmeta.append(meta);return e

def group(name,children):
 x=min(e['left']for e in children);y=min(e['top']for e in children);xx=max(e['left']+e['width']for e in children);yy=max(e['top']+e['height']for e in children)
 for e in children:e['left']-=x;e['top']-=y
 return dict(type='group',name=name,left=x,top=y,width=xx-x,height=yy-y,children=children)
def render(e):
 if e['type']=='shape':return render_shape(e)
 return '<g transform="translate('+str(e['left'])+' '+str(e['top'])+')">'+''.join(render(c)for c in e['children'])+'</g>'
right_white=(381,533,406,598);fold=(665,533,121,119);binding=(380,644,143,426);pie_green=(655,715,76,77);pie_dark=(564,728,153,155);left_body=(154,664,294,484);right_rows=[(565,921,174,25),(565,971,174,25)];left_rows=[(202,807,35,41),(260,819,138,54),(202,881,35,41),(260,893,138,53),(202,953,34,42),(260,965,138,55)]
assert set(gs)=={fold,binding,pie_green};assert set(ws)=={right_white};assert left_body in ps
spine=node(component(green,gs[binding]),'Punggung hijau laporan')
white_mask=component(white,ws[right_white]);page_mask=fill_holes(white_mask|component(green,gs[fold]));paper=node(page_mask,'Lembar kanan: badan utuh di bawah diagram',color_for(white_mask),True)
right=[paper,node(component(green,gs[fold]),'Lipatan sudut lembar kanan'),node(component(dark,ds[pie_dark]),'Diagram lingkaran: bidang gelap'),node(component(green,gs[pie_green]),'Diagram lingkaran: sektor hijau')]+[node(component(dark,ds[b]),'Baris laporan kanan '+str(i+1))for i,b in enumerate(right_rows)]
left=[node(component(purple,ps[left_body]),'Panel kiri ungu: badan utuh',holes_are_ink=True)]+[node(component(dark,ds[b]),'Isi panel kiri '+str(i+1))for i,b in enumerate(left_rows)]
asset=group('LAPORAN TERBUKA - panel kiri, punggung, lembar kanan',[spine,group('LEMBAR KANAN - kertas, lipatan, diagram, baris',right),group('PANEL KIRI - bidang ungu dan isi daftar',left)])
bgcolor='#%02x%02x%02x'%tuple(np.rint(np.median(im[20:150,20:150],axis=(0,1))).astype(int));bg=dict(type='shape',name='Latar kandidat: gradasi belum dipulihkan',left=0,top=0,width=w,height=h,viewBox=dict(left=0,top=0,width=w,height=h),paths=[dict(d=f'M0 0H{w}V{h}H0Z',fill=dict(color=bgcolor))]);elements=[bg,asset];package=dict(format='cusbe-canva-package',version=2,source='H01 - LAPORAN TERBUKA UTUH',width=w,height=h,elements=elements,summary=dict(shape=15,group=3,text=0,image=0),warnings=['Local candidate only. Actual Canva import/export and buyer editing not tested.','Subtle source gradients and grain remain unresolved.'])
package=normalize_package(package)
raw=json.dumps(package,ensure_ascii=False).encode();(OUT/'CANVA_PACKAGE.json').write_bytes(raw);(OUT/'package.gz').write_bytes(gzip.compress(raw));svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'+''.join(render(e)for e in elements)+'</svg>';(OUT/'preview.svg').write_text(svg);(OUT/'preview.png').write_bytes(resvg_py.svg_to_bytes(svg_string=svg));(OUT/'inventory.json').write_text(json.dumps(dict(source=str(SOURCE),sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),semantic_asset='folded/open report with integrated left panel, spine and right page',root_asset_count=1,subgroups=['right page with its fold/chart/rows','left panel with its list'],native_components=allmeta,ownership='explicit observed source component bounds',nearest_object_assignment=False,body_tiling=False),indent=2));(OUT/'QA.json').write_text(json.dumps(dict(stage='LOCAL_REPAIR_REQUIRES_CANVA_IMPORT_AND_EXPORT',minimum_component_mask_iou=min(m['mask_iou']for m in allmeta),geometry_gates=[m['local_geometry_gate']for m in allmeta],gradients='UNRESOLVED',buyer='NOT_TESTED',**package['summary']),indent=2));sheet=Image.new('RGB',(1000,980),'#e7edf4');d=ImageDraw.Draw(sheet);font=ImageFont.truetype(REPORT_FONT_,24)
for j,(title,p)in enumerate([('SUMBER',SOURCE),('LAPORAN DALAM SATU ASET',OUT/'preview.png')]):
 d.text((20+j*500,20),title,font=font,fill='#091522');pic=Image.open(p).convert('RGB');pic.thumbnail((460,880));sheet.paste(pic,(20+j*500,70))
sheet.save(OUT/'CONTACT-SHEET.png');print(json.dumps(dict(shapes=15,semantic_assets=1,groups=3,min_iou=min(m['mask_iou']for m in allmeta))))
