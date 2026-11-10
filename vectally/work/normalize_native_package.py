"""Normalize authored semantic groups to Canva's native simple-child constraints.

Keeps every rendered leaf's geometry/color intact. Semantic ownership is kept in
root asset names and the source inventory; singleton assets remain whole shapes.
"""
from copy import deepcopy
import json

def _leaves(e,ox=0.,oy=0.):
 x=ox+e.get('left',0);y=oy+e.get('top',0)
 if e['type']=='group':
  if e.get('rotation',0):raise ValueError('Rotated nested groups require an explicit transform')
  out=[]
  for c in e.get('children',[]):out.extend(_leaves(c,x,y))
  return out
 leaf=deepcopy(e);leaf['left']=x;leaf['top']=y;return[leaf]

def _signature(elements):
 rows=[]
 for e in elements:
  for l in _leaves(e):
   l.pop('name',None);l['left']=round(l['left'],8);l['top']=round(l['top'],8);rows.append(l)
 return json.dumps(rows,sort_keys=True,separators=(',',':'))

def normalize_package(package):
 p=deepcopy(package);before=_signature(p['elements']);out=[]
 for e in p['elements']:
  if e['type']!='group':out.append(e);continue
  children=[]
  for child in e.get('children',[]):children.extend(_leaves(child))
  if not children:raise ValueError('Empty semantic asset')
  if len(children)==1:
   c=children[0];c['left']+=e.get('left',0);c['top']+=e.get('top',0);c['name']=e['name'];out.append(c)
  else:
   e['children']=children;out.append(e)
 p['elements']=out
 assert before==_signature(out),'Native normalization changed rendered leaves'
 def count(ty):return sum((e['type']==ty)+sum(c['type']==ty for c in e.get('children',[]))for e in out)
 p['summary']={t:count(t)for t in ['shape','group','text','image']}
 for e in out:
  if e['type']=='group':assert len(e['children'])>=2 and all(c['type']!='group'for c in e['children'])
  for leaf in _leaves(e):
   if leaf['type']=='shape':assert all(len(x['d'].encode('utf8'))<=1850 for x in leaf['paths'])
 p['native_adaptation']={'nested_groups_flattened_with_geometry_preserved':True,'single_primitive_assets_are_whole_shapes':True,'leaf_signature_verified':True}
 return p
