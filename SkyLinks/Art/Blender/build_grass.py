"""Grass blade clumps for the 3D grass that grows on the rough and along bunker lips (ASkyLinksGrass).

    python Art/Blender/build_grass.py        (bpy module; -- SM_GrassPatch to build just that one)

Writes Art/Exports/Grass/SM_GrassClump.fbx (short rough), SM_GrassTuft.fbx (taller, wispy lip tufts) and
SM_WindLeaf / SM_WindStraw.fbx (the leaves and dry grass the wind blows about, ASkyLinksWindDebris).
Each blade is a thin bent strip (3 triangles). Vertex colour R = height up the blade (0 root .. 1 tip),
G = a random shade per blade; the normals all point up so the blades light like the ground they grow from.
Scripts/apply_floating_islands.py (import_grass) brings them in with the M_GrassBlades material.
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sl_common as sl  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / 'Exports' / 'Grass'


def clump(name, blades, spread, height, width, lean, seed):
    rng = np.random.default_rng(seed)
    verts, faces, cols = [], [], []
    for _ in range(blades):
        r = spread * math.sqrt(rng.random())
        a = rng.random() * 2 * math.pi
        base = np.array([r * math.cos(a), r * math.sin(a), 0.0])
        h = rng.uniform(*height)
        w = rng.uniform(*width)
        facing = rng.random() * 2 * math.pi
        side = np.array([math.cos(facing), math.sin(facing), 0.0])
        # Lean mostly outward from the clump centre, bending more toward the tip.
        out = np.array([math.cos(a), math.sin(a), 0.0]) if r > 1e-4 else side
        tilt = rng.uniform(*lean)
        shade = rng.random()
        pts = []
        for t, half in ((0.0, w * 0.5), (0.5, w * 0.38), (1.0, 0.0)):
            centre = base + np.array([0, 0, h * t]) + out * tilt * h * t ** 1.8
            pts.append((centre - side * half, centre + side * half, t))
        i = len(verts)
        for left, right, t in pts[:2]:
            verts += [left, right]
            cols += [(t, shade, 0.0, 1.0)] * 2
        verts.append(pts[2][0])
        cols.append((1.0, shade, 0.0, 1.0))
        faces += [(i, i + 1, i + 3), (i, i + 3, i + 2), (i + 2, i + 3, i + 4)]

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(map(float, v)) for v in verts], [], faces)
    attribute = mesh.color_attributes.new('Col', 'BYTE_COLOR', 'POINT')
    attribute.data.foreach_set('color_srgb', np.asarray(cols, np.float32).ravel())
    mesh.color_attributes.active_color = attribute
    uv = mesh.uv_layers.new(name='UVMap')
    loops_v = np.zeros(len(mesh.loops), np.int32)
    mesh.loops.foreach_get('vertex_index', loops_v)
    c = np.asarray(cols, np.float32)
    uv.data.foreach_set('uv', np.column_stack([c[loops_v, 1], c[loops_v, 0]]).ravel())
    mesh.materials.append(bpy.data.materials.new('GrassBlades'))
    mesh.validate()
    mesh.normals_split_custom_set_from_vertices([(0.0, 0.0, 1.0)] * len(verts))
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def flake(name, kind):
    """A single leaf (a folded diamond, 6 cm) or a bit of dry grass (a thin 8 cm sliver) for the wind debris.
    Vertex colour R = 0 at the stem end, 1 at the tip."""
    if kind == 'leaf':
        verts = [(-0.03, 0.0, 0.0), (0.0, -0.016, 0.004), (0.03, 0.0, 0.0), (0.0, 0.016, 0.004), (0.0, 0.0, -0.002)]
        faces = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]
        cols = [(0.0, 0.5, 0, 1), (0.5, 0.5, 0, 1), (1.0, 0.5, 0, 1), (0.5, 0.5, 0, 1), (0.5, 0.5, 0, 1)]
    else:
        verts = [(-0.04, -0.002, 0.0), (0.04, -0.001, 0.003), (0.04, 0.001, 0.003), (-0.04, 0.002, 0.0)]
        faces = [(0, 1, 2), (0, 2, 3)]
        cols = [(0.0, 0.5, 0, 1), (1.0, 0.5, 0, 1), (1.0, 0.5, 0, 1), (0.0, 0.5, 0, 1)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    attribute = mesh.color_attributes.new('Col', 'BYTE_COLOR', 'POINT')
    attribute.data.foreach_set('color_srgb', np.asarray(cols, np.float32).ravel())
    mesh.color_attributes.active_color = attribute
    mesh.uv_layers.new(name='UVMap')
    mesh.materials.append(bpy.data.materials.new('Debris'))
    mesh.validate()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    specs = {
        'SM_GrassClump': dict(blades=34, spread=0.16, height=(0.07, 0.19), width=(0.009, 0.016), lean=(0.2, 0.7), seed=1),
        'SM_GrassTuft': dict(blades=24, spread=0.06, height=(0.16, 0.38), width=(0.006, 0.011), lean=(0.3, 0.9), seed=2),
        # Thick rough near the camera: a wide patch, overlapping its neighbours into a full carpet.
        'SM_GrassPatch': dict(blades=70, spread=0.34, height=(0.08, 0.23), width=(0.009, 0.016), lean=(0.2, 0.75), seed=3),
    }
    only = [a for a in sys.argv[sys.argv.index('--') + 1:]] if '--' in sys.argv else []
    if only:
        specs = {k: v for k, v in specs.items() if k in only}
    for name, spec in specs.items():
        sl.reset_scene()
        obj = clump(name, **spec)
        sl.export_fbx(str(OUT / f'{name}.fbx'), [obj])
        print(f'GRASS {name}: {len(obj.data.polygons)} triangles')
    for name, kind in (() if only else (('SM_WindLeaf', 'leaf'), ('SM_WindStraw', 'straw'))):
        sl.reset_scene()
        obj = flake(name, kind)
        sl.export_fbx(str(OUT / f'{name}.fbx'), [obj])
        print(f'DEBRIS {name}')


if __name__ == '__main__':
    main()
