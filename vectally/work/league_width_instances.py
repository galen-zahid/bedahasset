from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from pathlib import Path
p=Path('outputs/VECTALLY-hybrid/font-identification');f=TTFont(p/'LeagueGothic-variable.ttf');print([(a.axisTag,a.minValue,a.defaultValue,a.maxValue)for a in f['fvar'].axes])
for wdth in [75,87.5]:
 g=instantiateVariableFont(f,dict(wdth=wdth),inplace=False);g.save(p/('LeagueGothic-wdth'+str(wdth)+'.ttf'))
