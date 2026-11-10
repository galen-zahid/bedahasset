from vpaths import VSRC_, REPORT_FONT_  # portable paths (was D:/ and C:/)
from pathlib import Path
import json,gzip,hashlib,io,math
import cv2,numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy.optimize import least_squares
import resvg_py
from native_component_builder import ComponentBuilder,fill_holes,native_group,render_node
from normalize_native_package import normalize_package
SOURCE=next(Path(VSRC_+'/Highlight').glob('VECTALLY_H03_*.png'));OUT=Path('outputs/VECTALLY-highlight-repair/H03');OUT.mkdir(parents=True,exist_ok=True);im=np.array(Image.open(SOURCE).convert('RGB'));a=im.astype(int);h,w=im.shape[:2];b=ComponentBuilder(im)
def components(mask):
 n,l,s,c=cv2.connectedComponentsWithStats(mask.astype('uint8'));return l,{tuple(map(int,s[i,:4])):i for i in range(1,n)if s[i,4]>500}
dark,ds=components(a.max(2)<80);white,ws=components(a.min(2)>200);purple,ps=components((a[:,:,0]>75)&(a[:,:,1]<210)&(a[:,:,2]>a[:,:,0]*1.1));get=lambda labels,look,bounds:(labels==look[tuple(bounds)]).astype('uint8');root=get(dark,ds,(104,467,746,792));white_main=get(white,ws,(130,494,603,714));white_fold=get(white,ws,(616,513,101,104));cs,_=cv2.findContours(root,cv2.RETR_LIST,cv2.CHAIN_APPROX_NONE);points=np.concatenate([c.reshape(-1,2)for c in cs]).astype(float)+.5
fits={};outer_points=[];inner_points=[]
# Use only unoccluded annulus edges; document rules and the handle are excluded.
for y in range(856,1008):
 if 910<=y<=931:continue
 xs=np.flatnonzero(root[y,330:820])+330
 if not len(xs):continue
 left,right=xs[0],xs[-1];outer_points.extend([[left+.5,y+.5],[right+.5,y+.5]])
 l=left
 while l<right and root[y,l]:l+=1
 r=right
 while r>left and root[y,r]:r-=1
 if l<433 and r>730:inner_points.extend([[l-.5,y+.5],[r+.5,y+.5]])
for x in range(450,681):
 ys=np.flatnonzero(root[690:805,x])+690
 if not len(ys):continue
 top=ys[0];outer_points.append([x+.5,top+.5]);z=top
 while z<838 and root[z,x]:z+=1
 if z<838:inner_points.append([x+.5,z-.5])
for x in range(450,631):
 ys=np.flatnonzero(root[1100:1180,x])+1100
 if not len(ys):continue
 bottom=ys[-1];outer_points.append([x+.5,bottom+.5]);z=bottom
 while z>1025 and root[z,x]:z-=1
 if z>1025:inner_points.append([x+.5,z+.5])
for tag,initial,rawpoints in [('outer',[563.5,932,227,229],outer_points),('inner',[563.5,932,194,196],inner_points)]:
 picked=np.asarray(rawpoints,float)
 def residual(v):return (np.sqrt(((picked[:,0]-v[0])/v[2])**2+((picked[:,1]-v[1])/v[3])**2)-1)*min(v[2:])
 fit=least_squares(residual,initial,bounds=(np.array(initial)-[6,6,8,8],np.array(initial)+[6,6,8,8]),loss='soft_l1',f_scale=.5,max_nfev=300);fits[tag]=fit.x.tolist()

def ellipse_node(params,color,name):
 cx,cy,rx,ry=params;k=.5522847498307936;d=f'M{2*rx} {ry}C{2*rx} {ry+k*ry} {rx+k*rx} {2*ry} {rx} {2*ry}C{rx-k*rx} {2*ry} 0 {ry+k*ry} 0 {ry}C0 {ry-k*ry} {rx-k*rx} 0 {rx} 0C{rx+k*rx} 0 {2*rx} {ry-k*ry} {2*rx} {ry}Z';return dict(type='shape',name=name,left=cx-rx,top=cy-ry,width=2*rx,height=2*ry,viewBox=dict(left=0,top=0,width=2*rx,height=2*ry),paths=[dict(d=d,fill=dict(color=color))])
def raster(e):
 svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">{render_node(e)}</svg>';return (np.array(Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert('RGBA'))[:,:,3]>=128).astype('uint8')
navy=b.color(root);paper_color=b.color(white_main);outer_circle=raster(ellipse_node(fits['outer'],navy,'lens mask'));inner_circle=raster(ellipse_node(fits['inner'],paper_color,'inner mask'));yy,xx=np.indices((h,w));pane_boxes=[(449,735,282,104),(400,795,33,44),(373,856,60,152),(400,1025,33,42),(449,1025,278,100)];panes=np.maximum.reduce([fill_holes(get(white,ws,p))for p in pane_boxes]+[fill_holes(get(purple,ps,(448,855,307,153)))]);grid_bridge=(((xx>=433)&(xx<449))|((yy>=838)&(yy<857))|((yy>=1007)&(yy<1026)))&(inner_circle>0);inner_circle=fill_holes((panes>0)|grid_bridge);handle=((root>0)&(xx>620)&(yy>1020)&(np.abs((yy-xx)-407)<=76)).astype('uint8');lens_body=((outer_circle>0)|(handle>0)).astype('uint8');doc_clip=((xx>=104)&(xx<759)&(yy>=467)&(yy<1235));source_union=((root>0)|(white_main>0)|(white_fold>0))&doc_clip
outer_geom=np.zeros((h,w),np.uint8);inner_geom=np.zeros((h,w),np.uint8);cv2.rectangle(outer_geom,(104,467),(758,1234),1,-1);cv2.rectangle(inner_geom,(130,494),(732,1207),1,-1)
# Only hidden areas are reconstructed; the visible contour remains source-derived.
doc_body=fill_holes(np.where(lens_body>0,outer_geom,source_union));doc_inner=fill_holes(np.where(lens_body>0,inner_geom,white_main));document=[b.node(doc_body,'Dokumen: siluet badan utuh',navy,True),b.node(doc_inner,'Dokumen: lembar putih utuh',paper_color,True),b.node(white_fold,'Dokumen: bidang lipatan sudut',paper_color)]
for role,boxes in [('Piktogram mata uang',[(190,544,100,178)]),('Baris ringkasan',[(324,581,215,32),(324,647,148,31)]),('Garis isi',[(168,842,155,32),(168,971,155,32),(168,1099,193,32)])]:
 for i,box in enumerate(boxes):document.append(b.node(get(dark,ds,box),'Dokumen: '+role+' '+str(i+1)))
for i,(top,bottom)in enumerate([(784,801),(912,929),(1041,1058)]):
 mask=((xx>=164)&(xx<733)&(yy>=top)&(yy<bottom)).astype('uint8');document.append(b.node(mask,'Dokumen: baris tabel utuh '+str(i+1),navy))
lens=[b.node(lens_body,'Kaca pembesar: lingkaran dan gagang tersambung',navy,True),b.node(inner_circle,'Kaca pembesar: bidang lensa putih utuh',paper_color,True),b.node(get(purple,ps,(448,855,307,153)),'Kaca pembesar: sorotan nilai ungu utuh',fill_ink_holes=True)]
grid=(root>0)&(((xx>=432)&(xx<450))|((yy>=838)&(yy<857))|((yy>=1007)&(yy<1026)))&(inner_circle>0);lens.append(b.node(grid.astype('uint8'),'Kaca pembesar: kisi pembesaran tersambung',navy))
for role,boxes in [('Piktogram mata uang',[(482,880,57,102)]),('Indikator nilai',[(555,924,52,23),(615,924,52,23),(675,924,52,23)])]:
 for i,box in enumerate(boxes):lens.append(b.node(get(dark,ds,box),'Kaca pembesar: '+role+' '+str(i+1)))
assets=[native_group('DOKUMEN - badan, lipatan, tabel dan simbol',document),native_group('KACA PEMBESAR - lensa, gagang, kisi dan sorotan',lens)];bg='#%02x%02x%02x'%tuple(np.rint(np.median(im[20:150,20:150],axis=(0,1))).astype(int));background=dict(type='shape',name='Latar kandidat: gradasi sumber belum dipulihkan',left=0,top=0,width=w,height=h,viewBox=dict(left=0,top=0,width=w,height=h),paths=[dict(d=f'M0 0H{w}V{h}H0Z',fill=dict(color=bg))]);package=normalize_package(dict(format='cusbe-canva-package',version=2,source='H03 - DOKUMEN DAN KACA PEMBESAR UTUH',width=w,height=h,elements=[background]+assets,summary={},warnings=['Local geometry candidate, not yet imported into Canva.','Currency symbols are currently traced icon graphics; native text interpretation remains an explicit open audit item.','Subtle source gradients and grain remain unresolved.']));raw=json.dumps(package,ensure_ascii=False).encode();(OUT/'CANVA_PACKAGE.json').write_bytes(raw);(OUT/'package.gz').write_bytes(gzip.compress(raw));svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'+''.join(render_node(e)for e in package['elements'])+'</svg>';(OUT/'preview.svg').write_text(svg);(OUT/'preview.png').write_bytes(resvg_py.svg_to_bytes(svg_string=svg));rendered=np.array(Image.open(OUT/'preview.png').convert('RGB'));roi=(slice(440,1280),slice(80,880));source_dark=(a.max(2)<80)[roi];candidate_dark=(rendered.max(2)<80)[roi];dark_iou=float((source_dark&candidate_dark).sum()/(source_dark|candidate_dark).sum());(OUT/'inventory.json').write_text(json.dumps(dict(source=str(SOURCE),sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),semantic_assets=['whole document with integrated fold and data','whole magnifier with integrated handle, lens grid and highlight'],native_components=b.audit,ellipse_fits=fits,currency_symbols='vector icon candidate; editable-text scope remains open',hidden_geometry='reconstructed only under the magnifier; visible document silhouette source-derived',ownership='explicit physical masks and observed component bounds',nearest_object_assignment=False,body_tiling=False),indent=2));(OUT/'QA.json').write_text(json.dumps(dict(stage='LOCAL_GEOMETRY_CANDIDATE_REQUIRES_VISUAL_TEXT_POLICY_AND_CANVA_QA',source_dark_family_iou=dark_iou,minimum_component_mask_iou=min(x['mask_iou']for x in b.audit),geometry_gates=[x['local_geometry_gate']for x in b.audit],native_text_policy='CURRENCY_ICON_SCOPE_UNRESOLVED',gradients='UNRESOLVED',buyer='NOT_TESTED',**package['summary']),indent=2));sheet=Image.new('RGB',(1000,980),'#e7edf4');dr=ImageDraw.Draw(sheet);font=ImageFont.truetype(REPORT_FONT_,24)
for j,(label,path)in enumerate([('SUMBER',SOURCE),('DOKUMEN + KACA PEMBESAR',OUT/'preview.png')]):
 dr.text((20+j*500,20),label,font=font,fill='#091522');pic=Image.open(path).convert('RGB');pic.thumbnail((460,880));sheet.paste(pic,(20+j*500,70))
sheet.save(OUT/'CONTACT-SHEET.png');print(json.dumps(dict(**package['summary'],dark_iou=dark_iou,min_iou=min(x['mask_iou']for x in b.audit),ellipse_fits=fits)))
