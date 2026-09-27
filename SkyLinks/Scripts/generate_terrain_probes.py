"""Build world-space acceptance probes from the course layouts and generated heights."""
import json, math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from generate_golf_terrain import layouts,WATER_OVERRIDES
from PIL import Image
import numpy as np
folder=Path(__file__).resolve().parents[1]/'Art/Terrain/Holes01-06'
m=json.loads((folder/'manifest.json').read_text()); samples=[]
for i,h in enumerate(layouts()):
 g=m['holes'][i]['grid']; im=np.array(Image.open(folder/m['holes'][i]['files']['height']['file']),dtype=float)
 def sample(kind,x,y,pm):
  wx=x*100; wy=y*100+i*35000; u=(wx-g['x0'])/g['sx'];v=(wy-g['y0'])/g['sy'];u0=int(u);v0=int(v);du=u-u0;dv=v-v0
  raw=im[v0,u0]*(1-du)*(1-dv)+im[v0,u0+1]*du*(1-dv)+im[v0+1,u0]*(1-du)*dv+im[v0+1,u0+1]*du*dv
  z=(raw-32768)/128*m['scale_z']+m['actor_z_cm']
  samples.append({'hole':i+1,'kind':kind,'x':wx,'y':wy,'expected_z':.4 if pm=='Water' else z,'landscape_z':z,'pm':'PM_'+pm})
 for dx,dy in [(0,0),(5,0),(-5,0),(0,5),(0,-5)]:sample('green',h['cup'][0]+dx,h['cup'][1]+dy,'Green')
 for x,y in [(0,0),(-3,-3),(3,3)]:sample('tee',x,y,'Fairway')
 a,b,c,d=h['fairway'][0];sample('fairway',(a+b)/2,(c+d)/2,'Fairway')
 sample('rough',10,-45,'Rough')
 for x,y,r in h['bunkers']:sample('bunker',x,y,'Bunker')
 for a,b,c,d in WATER_OVERRIDES.get(i,h.get('water',[])):sample('water',(a+b)/2,(c+d)/2,'Water')
(folder/'validation_samples.json').write_text(json.dumps(samples,indent=2)+'\n')
print(len(samples),'independent world-space probes')
