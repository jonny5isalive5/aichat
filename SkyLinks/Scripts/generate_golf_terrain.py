"""Generate deterministic golf terrain for the existing Aura grids (holes 1-6).
Run outside Unreal with Python, numpy and Pillow. Does not modify editor assets.
Heights are uint16 PNG: world Z = (value - 32768) / 128 * scale_z + actor_z.
Rows increase world Y; columns increase world X. Weightmaps sum to 255 exactly.
"""
import ast
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Art' / 'Terrain' / 'Holes01-06'
SCALE_Z = 0.4296875
ACTOR_Z = -0.4296875
# Preserve Aura's saved hole 2 water placement, 40 m right of the original layout.
WATER_OVERRIDES = {1: [(55, 115, 20, 60)]}
SLOPES = [(0.012, 0.009), (-0.014, 0.006), (0.009, -0.012), (-0.012, -0.009), (0.015, 0.004), (0.006, 0.014)]

def smooth(t):
    t = np.clip(t, 0, 1)
    return t*t*(3-2*t)

def layouts():
    tree = ast.parse((ROOT/'Scripts/build_blockout_course.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'HOLES' for t in n.targets))
    return eval(compile(ast.Expression(node.value), '<hole layouts>', 'eval'), {'__builtins__': {}, 'dict': dict, 'range': range})[:6]

def rect_distance(x, y, rect):
    a,b,c,d=rect
    return np.maximum(np.maximum(a-x,x-b),np.maximum(c-y,y-d))

def generate():
    OUT.mkdir(parents=True, exist_ok=True)
    meta=json.loads((ROOT/'Saved/terrain/heightmaps/raw/meta.json').read_text())
    manifest={'encoding':'uint16 PNG, row +Y column +X', 'actor_z_cm':ACTOR_Z, 'scale_z':SCALE_Z, 'holes':[]}
    for index,hole in enumerate(layouts()):
        label=f'Terrain_Hole{index+1:02d}'
        g=meta[label]
        x=(g['x0']+np.arange(g['W'])*g['sx'])[None,:]/100
        y=(g['y0']+np.arange(g['H'])*g['sy'])[:,None]/100-index*350
        x,y=np.broadcast_arrays(x,y)
        fair=np.zeros(x.shape)
        for rect in hole['fairway']:
            fair=np.maximum(fair,1-smooth(rect_distance(x,y,rect)/1.5))
        tee=1-smooth(rect_distance(x,y,(-4,4,-4,4))/2)
        fair=np.maximum(fair,tee)
        cx,cy=hole['cup']; radius=hole['green']
        r=np.hypot(x-cx,y-cy)
        green=1-smooth((r-radius)/1.0)
        bunker=np.zeros(x.shape)
        height=30+20*np.sin(x/45+index*.7)*np.cos(y/38)
        height+=15*np.sin(x/31+.8)*np.sin(y/27+.4)

        sx,sy=SLOPES[index]
        green_height=30+100*(sx*(x-cx)+sy*(y-cy))
        green_blend=1-smooth((r-radius-1)/12)
        height=height*(1-green_blend)+green_height*green_blend
        for bx,by,br in hole['bunkers']:
            distance=np.hypot(x-bx,y-by)
            bowl=1-smooth((distance/br-.35)/.65)
            height-=30*bowl
            bunker=np.maximum(bunker,1-smooth((distance-br)/.6))
        water=np.zeros(x.shape)
        for rect in WATER_OVERRIDES.get(index,hole.get('water',[])):
            d=rect_distance(x,y,rect)
            bank=1-smooth((d-0)/6)
            target=15-75*smooth(-d/10)
            height=height*(1-bank)+target*bank
            water=np.maximum(water,(d<0).astype(float))
        tee_blend=1-smooth(rect_distance(x,y,(-5,5,-5,5))/7)
        height*=1-tee_blend
        edge=np.minimum.reduce([x-x.min(),x.max()-x,y-y.min(),y.max()-y])
        height*=smooth(edge/8)
        encoded=np.rint((height-ACTOR_Z)*128/SCALE_Z+32768)
        assert encoded.min()>=0 and encoded.max()<=65535, 'Height clipping'
        encoded=encoded.astype(np.uint16)
        decoded=(encoded.astype(float)-32768)/128*SCALE_Z+ACTOR_Z
        dzdy,dzdx=np.gradient(decoded,g['sy'],g['sx'])
        putting=r<radius-1
        for bx,by,br in hole['bunkers']:
            putting &= np.hypot(x-bx,y-by)>br+1
        slope=np.hypot(dzdx[putting],dzdy[putting])
        assert slope.min()>.009 and slope.max()<.03, 'Green slope outside target'
        assert np.max(np.abs(decoded[rect_distance(x,y,(-4,4,-4,4))<0]))<.01
        assert np.max(np.abs(decoded-height))<.002
        # Priority: sand then green then fairway; everything else rough.
        bw=np.rint(bunker*255).astype(np.int32)
        gw=np.rint(green*(255-bw)).astype(np.int32)
        fw=np.rint(fair*(255-bw-gw)).astype(np.int32)
        rw=255-bw-gw-fw
        files={}
        for name,arr in [('height',encoded),('Bunker',bw),('Green',gw),('Fairway',fw),('Rough',rw)]:
            path=OUT/f'Hole{index+1:02d}_{name}.png'
            Image.fromarray(arr if name=='height' else arr.astype(np.uint8)).save(path)
            files[name]={'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        manifest['holes'].append({'label':label,'grid':g,'cup_cm':[cx*100,cy*100+index*35000,30],'green_slope':list(SLOPES[index]),'height_range_cm':[float(decoded.min()),float(decoded.max())],'green_slope_range':[float(slope.min()),float(slope.max())],'max_slope':float(np.hypot(dzdx,dzdy).max()),'files':files})
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps([{k:v for k,v in h.items() if k in ['label','height_range_cm','green_slope_range','max_slope']} for h in manifest['holes']],indent=2))

if __name__=='__main__':
    generate()
