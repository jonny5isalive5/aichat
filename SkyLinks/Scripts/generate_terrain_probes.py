"""Build world-space acceptance probes from the course layouts and generated heights.

    python Scripts/generate_terrain_probes.py          # both batches
    python Scripts/generate_terrain_probes.py 7-18     # one batch
"""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from generate_golf_terrain import all_layouts,origin_m,WATER_OVERRIDES,BATCHES
from PIL import Image
import numpy as np


def build(first,last):
    folder=Path(__file__).resolve().parents[1]/'Art/Terrain'/BATCHES[(first,last)]
    m=json.loads((folder/'manifest.json').read_text()); samples=[]
    course=all_layouts()
    for entry in m['holes']:
        i=int(entry['label'][-2:])-1; h=course[i]; g=entry['grid']; ox,oy=origin_m(i)
        im=np.array(Image.open(folder/entry['files']['height']['file']),dtype=float)
        def sample(kind,x,y,pm):
            wx=x*100+ox*100; wy=y*100+oy*100; u=(wx-g['x0'])/g['sx'];v=(wy-g['y0'])/g['sy'];u0=int(u);v0=int(v);du=u-u0;dv=v-v0
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
    print(folder.name,len(samples),'independent world-space probes')


if __name__=='__main__':
    for batch in sys.argv[1:] or ['1-6','7-18']:
        first,last=(int(n) for n in batch.split('-'))
        build(first,last)
