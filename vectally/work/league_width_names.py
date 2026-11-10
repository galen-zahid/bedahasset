from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from pathlib import Path
p=Path('outputs/VECTALLY-hybrid/font-identification');f=TTFont(p/'LeagueGothic-variable.ttf')
for wdth in [75,87.5]:
 try:g=instantiateVariableFont(f,dict(wdth=wdth),inplace=False,updateFontNames=True)
 except Exception as e:print(type(e).__name__,str(e));continue
 name='LeagueGothic-wdth'+str(wdth)+'-named.ttf';g.save(p/name);print(name,{i:g['name'].getDebugName(i)for i in [1,2,4,6,16,17]})
