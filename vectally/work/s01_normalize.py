from pathlib import Path
import json
from normalize_native_package import normalize_package
r=Path('outputs/VECTALLY-story-repair/S01');p=normalize_package(json.loads((r/'ASSETS_PACKAGE.json').read_text()));(r/'ASSETS_PACKAGE.json').write_text(json.dumps(p));inv=json.loads((r/'INVENTORY.json').read_text());byname={e['name']:e for e in p['elements']}
for row in inv:
 e=byname.get(row.get('name'));
 if e is not None:row['children']=len(e.get('children',[]))or 1;row['shadowOwnership']='same physical sheet group'if row['id'].startswith('DOC')else'within book group'if row['id']=='BOOK'else'own process connector'
(r/'INVENTORY.json').write_text(json.dumps(inv,indent=2));print(json.dumps(p['summary']))
