"""Generate deterministic golf terrain for the course landscapes.

Run outside Unreal with Python, numpy and Pillow. Does not modify editor assets.

    python Scripts/generate_golf_terrain.py            # holes 1-6 (existing Aura grids) and 7-18
    python Scripts/generate_golf_terrain.py 1-6        # one batch only
    python Scripts/generate_golf_terrain.py 7-18

Heights are uint16 PNG: world Z = (value - 32768) / 128 * scale_z + actor_z.
Rows increase world Y; columns increase world X. Weightmaps sum to 255 exactly.

Holes 1-6 use the grids Aura already created (Saved/terrain/heightmaps/raw/meta.json); their
output is byte-identical to the original Codex pass. Holes 7-18 have no landscapes yet, so their
grids are planned here to the same conventions (hole bounds + 35 m margin, 63-quad sections,
spacing at most 40 cm) and written to the manifest as `create` parameters for Aura.
"""
import ast
import hashlib
import json
import math
import sys
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCALE_Z = 0.4296875
ACTOR_Z = -0.4296875
BATCHES = {(1, 6): 'Holes01-06', (7, 18): 'Holes07-18'}
# Preserve Aura's saved hole 2 water placement, 40 m right of the original layout (0-based index).
WATER_OVERRIDES = {1: [(55, 115, 20, 60)]}
# Planar green slope (x, y) per hole, all between about 1.2% and 1.6%.
SLOPES = [(0.012, 0.009), (-0.014, 0.006), (0.009, -0.012), (-0.012, -0.009), (0.015, 0.004), (0.006, 0.014),
          (-0.011, 0.010), (0.013, -0.007), (-0.006, -0.014), (0.010, 0.011), (-0.015, -0.003), (0.004, -0.015),
          (0.012, -0.010), (-0.009, 0.012), (0.014, 0.006), (-0.013, -0.008), (0.007, 0.013), (-0.010, 0.010)]
MARGIN_M = 35
SECTION_QUADS = 63
MAX_SPACING_CM = 40.0


def smooth(t):
    t = np.clip(t, 0, 1)
    return t*t*(3-2*t)


def all_layouts():
    tree = ast.parse((ROOT/'Scripts/build_blockout_course.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'HOLES' for t in n.targets))
    return eval(compile(ast.Expression(node.value), '<hole layouts>', 'eval'), {'__builtins__': {}, 'dict': dict, 'range': range})


def layouts():
    """First six holes (kept for the existing probe script)."""
    return all_layouts()[:6]


def origin_m(index):
    """Hole origin in metres, matching build_blockout_course.build_hole: two rows of nine."""
    row, column = divmod(index, 9)
    return row*800, column*350


def rect_distance(x, y, rect):
    a,b,c,d=rect
    return np.maximum(np.maximum(a-x,x-b),np.maximum(c-y,y-d))


def hole_bounds_m(index, hole):
    """Same bounds as build_blockout_course.bounds(): everything on the hole plus a 35 m margin."""
    xs, ys = [0, hole['cup'][0]], [0, hole['cup'][1]]
    for rect in hole.get('fairway', []) + WATER_OVERRIDES.get(index, hole.get('water', [])):
        xs += [rect[0], rect[1]]
        ys += [rect[2], rect[3]]
    for x, y, r in hole.get('bunkers', []):
        xs += [x-r, x+r]
        ys += [y-r, y+r]
    for x, y in hole.get('trees', []):
        xs.append(x)
        ys.append(y)
    return min(xs)-MARGIN_M, max(xs)+MARGIN_M, min(ys)-MARGIN_M, max(ys)+MARGIN_M


def plan_grid(index, hole):
    ox, oy = origin_m(index)
    x0, x1, y0, y1 = hole_bounds_m(index, hole)
    grid = {}
    for axis, low, high, offset in (('x', x0, x1, ox), ('y', y0, y1, oy)):
        length_cm = (high-low)*100
        sections = math.ceil(length_cm/MAX_SPACING_CM/SECTION_QUADS)
        count = sections*SECTION_QUADS+1
        grid['W' if axis == 'x' else 'H'] = count
        grid[axis+'0'] = round((offset+low)*100, 3)
        grid['s'+axis] = round(length_cm/(count-1), 6)
    return grid


def generate(first, last):
    folder_name = BATCHES[(first, last)]
    out = ROOT/'Art'/'Terrain'/folder_name
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((ROOT/'Saved/terrain/heightmaps/raw/meta.json').read_text())
    manifest = {'encoding':'uint16 PNG, row +Y column +X', 'actor_z_cm':ACTOR_Z, 'scale_z':SCALE_Z, 'holes':[]}
    course = all_layouts()
    for index in range(first-1, last):
        hole = course[index]
        label = f'Terrain_Hole{index+1:02d}'
        planned = label not in meta
        g = plan_grid(index, hole) if planned else meta[label]
        ox, oy = origin_m(index)
        x=(g['x0']+np.arange(g['W'])*g['sx'])[None,:]/100-ox
        y=(g['y0']+np.arange(g['H'])*g['sy'])[:,None]/100-oy
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
        # Greens stay above water (island and water-side greens); water basins carve around them.
        land=1-smooth((r-radius-1)/3)
        for bx,by,br in hole['bunkers']:
            land=np.maximum(land,1-smooth((np.hypot(x-bx,y-by)-br-1)/3))
        water=np.zeros(x.shape)
        for rect in WATER_OVERRIDES.get(index,hole.get('water',[])):
            d=rect_distance(x,y,rect)
            bank=(1-smooth((d-0)/6))*(1-land)
            target=15-75*smooth(-d/10)
            height=height*(1-bank)+target*bank
            water=np.maximum(water,(d<0).astype(float)*(1-land))
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
        assert slope.min()>.009 and slope.max()<.03, f'{label}: green slope outside target'
        assert np.max(np.abs(decoded[rect_distance(x,y,(-4,4,-4,4))<0]))<.01, f'{label}: tee not flat'
        assert np.max(np.abs(decoded-height))<.002
        # Priority: sand then green then fairway; everything else rough.
        bw=np.rint(bunker*255).astype(np.int32)
        gw=np.rint(green*(255-bw)).astype(np.int32)
        fw=np.rint(fair*(255-bw-gw)).astype(np.int32)
        rw=255-bw-gw-fw
        files={}
        for name,arr in [('height',encoded),('Bunker',bw),('Green',gw),('Fairway',fw),('Rough',rw)]:
            path=out/f'Hole{index+1:02d}_{name}.png'
            Image.fromarray(arr if name=='height' else arr.astype(np.uint8)).save(path)
            files[name]={'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        entry={'label':label,'grid':g,'cup_cm':[(cx+ox)*100,cy*100+oy*100,30],'green_slope':list(SLOPES[index]),
               'height_range_cm':[float(decoded.min()),float(decoded.max())],'green_slope_range':[float(slope.min()),float(slope.max())],
               'max_slope':float(np.hypot(dzdx,dzdy).max()),'files':files}
        if planned:
            # What Aura needs to create the landscape before update_landscape_heightmap can apply this.
            entry['create']={'landscape_label':label,'location_cm':[g['x0'],g['y0'],ACTOR_Z],'scale':[g['sx'],g['sy'],SCALE_Z],
                             'resolution':[g['W'],g['H']],'section_quads':SECTION_QUADS,'sections_per_component':1,
                             'material':'/Game/Course/Materials/M_Hole01_Landscape','layers':['Rough','Fairway','Green','Bunker'],
                             'folder':f'Course/Hole{index+1:02d}'}
        manifest['holes'].append(entry)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps([{k:v for k,v in h.items() if k in ['label','height_range_cm','green_slope_range','max_slope']} for h in manifest['holes']],indent=2))


if __name__=='__main__':
    requested = sys.argv[1:] or ['1-6', '7-18']
    for batch in requested:
        first, last = (int(n) for n in batch.split('-'))
        generate(first, last)
