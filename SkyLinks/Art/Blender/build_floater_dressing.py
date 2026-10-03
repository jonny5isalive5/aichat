"""Pandora-style dressing for the floating islands: leafy ivy hugging the rock, glowing flowers on the cliffs,
glowing ferns and mushrooms and big-leaved plants round the top.

    python Art/Blender/build_floater_dressing.py            (every floater)
    python Art/Blender/build_floater_dressing.py -- 3 7     (just holes 3 and 7)
    python Art/Blender/build_floater_dressing.py -- SM_H01_Floater08 novines   (one floater, old vines taken off)

For each Art/Exports/Islands/SM_Hnn_FloaterNN.fbx this writes SM_Hnn_FloaterNN_Dress.fbx in the same space (same
pivot), plus the shared leaf / petal texture Art/Textures/T_FloaterAtlas.png. In Unreal,
apply_floating_islands.dress_floaters() puts each dressing on its floater, attached to it, so the floaters stay
exactly where they were placed by hand (and the dressing follows when one is moved).

Two materials: FloaterLeaf (lit, cut out of the atlas, tinted by vertex colour) and FloaterGlow (unlit and
emissive, so it glows without lights, on phones too). Atlas quarters: heart leaf, fern frond, petal, plain.
"""
import math
import random
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sl_common as sl  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ISLANDS = ROOT / 'Art' / 'Exports' / 'Islands'
ATLAS = ROOT / 'Art' / 'Textures' / 'T_FloaterAtlas.png'

LEAF, FERN, PETAL, PLAIN = (0.0, 0.0), (0.5, 0.0), (0.0, 0.5), (0.5, 0.5)  # atlas quarters (u, v of a corner)
GLOW_COLOURS = [(0.05, 1.0, 0.85), (0.1, 0.75, 1.0), (0.25, 0.4, 1.0), (0.65, 0.25, 1.0), (0.1, 1.0, 0.6)]


# ---------------------------------------------------------------- the atlas

def make_atlas(size=1024):
    from PIL import Image, ImageDraw, ImageFilter
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    h = size // 2

    def quarter(corner):  # pixel box of an atlas quarter (u, v from the bottom left)
        x0 = int(corner[0] * size)
        y0 = size - int(corner[1] * size) - h
        return x0, y0

    # Heart-shaped ivy leaf, stalk at the bottom, with darker veins.
    leaf = Image.new('RGBA', (h, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(leaf)
    pts = []
    for i in range(200):
        t = 2 * math.pi * i / 200
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((h / 2 + x * h / 36, h * 0.47 - y * h / 36))
    pts = [(x, h - y) for x, y in pts]  # point down: the tip away from the stalk
    d.polygon(pts, fill=(235, 245, 225, 255))
    for k in range(-3, 4):
        d.line([(h / 2, h * 0.86), (h / 2 + k * h * 0.11, h * 0.25 + abs(k) * h * 0.09)], fill=(150, 175, 140, 255), width=3)
    d.line([(h / 2, h * 0.98), (h / 2, h * 0.12)], fill=(140, 165, 130, 255), width=5)
    img.paste(leaf, quarter(LEAF), leaf)

    # Fern frond: a stem with leaflets shrinking to the tip (stem along the quarter's height).
    fern = Image.new('RGBA', (h, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(fern)
    for j in range(22):
        y = h * (0.95 - j * 0.041)
        reach = h * 0.42 * (1 - j / 24) ** 0.8
        for s in (-1, 1):
            d.ellipse([h / 2 + min(0, s * reach), y - h * 0.018, h / 2 + max(0, s * reach), y + h * 0.018],
                      fill=(240, 250, 240, 255))
    d.line([(h / 2, h), (h / 2, h * 0.04)], fill=(200, 220, 200, 255), width=6)
    img.paste(fern, quarter(FERN), fern)

    # Petal: a soft long oval, brightest along the middle.
    petal = Image.new('RGBA', (h, h), (0, 0, 0, 0))
    yy, xx = np.mgrid[0:h, 0:h] / h
    r = np.sqrt(((xx - 0.5) / 0.3) ** 2 + ((yy - 0.5) / 0.48) ** 2)
    alpha = np.clip((1 - r) * 4, 0, 1)
    light = np.clip(1.25 - r * 0.9 - np.abs(xx - 0.5) * 0.8, 0.35, 1)
    arr = np.dstack([light * 255] * 3 + [alpha * 255]).astype(np.uint8)
    petal = Image.fromarray(arr, 'RGBA').filter(ImageFilter.GaussianBlur(1))
    img.paste(petal, quarter(PETAL), petal)

    # Plain (stems, caps, bulbs).
    img.paste(Image.new('RGBA', (h, h), (255, 255, 255, 255)), quarter(PLAIN))
    ATLAS.parent.mkdir(parents=True, exist_ok=True)
    img.save(ATLAS)


# ---------------------------------------------------------------- geometry kit

class Kit:
    """Triangles in two material slots (0 leaf, 1 glow) with UVs and vertex colours."""

    def __init__(self):
        self.v, self.uv, self.col, self.f, self.mat = [], [], [], [], []

    def quad(self, corners, uvs, colour, mat):
        base = len(self.v)
        self.v += [tuple(c) for c in corners]
        self.uv += uvs
        self.col += [colour] * 4
        self.f += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
        self.mat += [mat, mat]

    def card(self, root, up, side, length, width, region, colour, mat):
        """A flat card from root along up (its stalk at root), width across side."""
        u0, v0 = region
        a, b = root - side * width / 2, root + side * width / 2
        c, d = b + up * length, a + up * length
        self.quad([a, b, c, d], [(u0, v0), (u0 + 0.5, v0), (u0 + 0.5, v0 + 0.5), (u0, v0 + 0.5)], colour, mat)

    def bent_card(self, root, up, side, out, length, width, bend, region, colour, mat, rows=3):
        """A card that arches out and over (fern fronds, big leaves): rows of quads along a curve."""
        u0, v0 = region
        pts = []
        for i in range(rows + 1):
            t = i / rows
            pts.append(root + up * (length * t) + out * (bend * length * t * t))
        for i in range(rows):
            a0, a1 = pts[i] - side * width / 2, pts[i] + side * width / 2
            b0, b1 = pts[i + 1] - side * width / 2, pts[i + 1] + side * width / 2
            t0, t1 = i / rows, (i + 1) / rows
            self.quad([a0, a1, b1, b0], [(u0, v0 + 0.5 * t0), (u0 + 0.5, v0 + 0.5 * t0),
                                          (u0 + 0.5, v0 + 0.5 * t1), (u0, v0 + 0.5 * t1)], colour, mat)

    def blob(self, centre, radius, colour, mat, squash=1.0, sides=6):
        """A low bulb (two rings and two poles)."""
        u, v = PLAIN[0] + 0.25, PLAIN[1] + 0.25
        ring = []
        for k in (-0.5, 0.5):
            for i in range(sides):
                a = 2 * math.pi * (i + (0.5 if k > 0 else 0)) / sides
                ring.append(centre + Vector((math.cos(a) * radius * 0.87, math.sin(a) * radius * 0.87, k * radius * squash)))
        top, bottom = centre + Vector((0, 0, radius * squash)), centre - Vector((0, 0, radius * squash))
        base = len(self.v)
        self.v += [tuple(p) for p in ring] + [tuple(top), tuple(bottom)]
        self.uv += [(u, v)] * (len(ring) + 2)
        self.col += [colour] * (len(ring) + 2)
        t, bt = base + len(ring), base + len(ring) + 1
        for i in range(sides):
            j = (i + 1) % sides
            lo0, lo1, hi0, hi1 = base + i, base + j, base + sides + i, base + sides + j
            self.f += [(lo0, lo1, hi0), (lo1, hi1, hi0), (hi0, hi1, t), (lo1, lo0, bt)]
            self.mat += [mat] * 4

    def cone(self, apex, base_centre, radius, colour, mat, sides=7):
        u, v = PLAIN[0] + 0.25, PLAIN[1] + 0.25
        start = len(self.v)
        for i in range(sides):
            a = 2 * math.pi * i / sides
            self.v.append(tuple(base_centre + Vector((math.cos(a) * radius, math.sin(a) * radius, 0))))
        self.v += [tuple(apex), tuple(base_centre)]
        self.uv += [(u, v)] * (sides + 2)
        self.col += [colour] * (sides + 2)
        for i in range(sides):
            j = (i + 1) % sides
            self.f += [(start + i, start + j, start + sides), (start + j, start + i, start + sides + 1)]
            self.mat += [mat, mat]

    def mesh(self, name, domain='POINT'):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f)
        for slot in ('FloaterLeaf', 'FloaterGlow'):
            me.materials.append(bpy.data.materials.get(slot) or bpy.data.materials.new(slot))
        me.polygons.foreach_set('material_index', np.asarray(self.mat, np.int32))
        uv = me.uv_layers.new(name='UVMap')
        loops = np.zeros(len(me.loops), np.int32)
        me.loops.foreach_get('vertex_index', loops)
        uv.data.foreach_set('uv', np.asarray(self.uv, np.float32)[loops].ravel())
        # domain CORNER matches meshes whose colours are per corner (the trees), so the two can be joined.
        col = me.color_attributes.new('Col', 'BYTE_COLOR', domain)
        rgba = np.concatenate([np.asarray(self.col, np.float32), np.ones((len(self.v), 1), np.float32)], 1)
        if domain == 'CORNER':
            rgba = rgba[loops]
        col.data.foreach_set('color_srgb', np.clip(rgba, 0, 1).ravel())
        me.validate()
        obj = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(obj)
        return obj


# ---------------------------------------------------------------- one floater

def leaf_green(rng):
    return (rng.uniform(0.3, 0.5), rng.uniform(0.68, 0.88), rng.uniform(0.14, 0.3))


def dress(path, rng, strip_vines=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(path))
    rock = next(o for o in bpy.data.objects if o.type == 'MESH' and not o.name.endswith('_Ivy'))
    others = [o for o in bpy.data.objects if o is not rock]
    had_vines = any(o.name.endswith('_Ivy') for o in others)
    for o in others:
        bpy.data.objects.remove(o)
    if strip_vines and had_vines:
        # The old thin hanging vines hide the new ivy and flowers: the floater again, rock only (same name, so
        # Unreal re-imports it in place; the original with vines is kept beside it as .with_vines.fbx).
        keep = path.with_name(path.stem + '.with_vines.fbx')
        if not keep.exists():
            path.replace(keep)
        sl.export_fbx(str(path), [rock])
        print(f'VINES removed from {path.name}')
    world = rock.matrix_world.copy()
    me = rock.data
    tops = {i for i, m in enumerate(me.materials) if m and m.name.split('.')[0] == 'Rough'}
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(world)
    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm)
    top_faces = [f for f in bm.faces if f.material_index in tops]
    rock_faces = [f for f in bm.faces if f.material_index not in tops and f.calc_area() > 1e-4]
    lo = Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
    hi = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
    centre = (lo + hi) / 2
    size = max(hi.x - lo.x, hi.y - lo.y)

    # The top's rim: the farthest top point in each direction from the middle.
    bins = 72
    rim = [None] * bins
    for f in top_faces:
        for v in f.verts:
            d = Vector((v.co.x - centre.x, v.co.y - centre.y))
            k = int((math.atan2(d.y, d.x) + math.pi) / (2 * math.pi) * bins) % bins
            if rim[k] is None or d.length > rim[k][1]:
                rim[k] = (v.co.copy(), d.length)
    rim = [r[0] for r in rim if r]
    kit = Kit()
    # Smaller floaters get proportionally fewer plants (and every one at least a little).
    scale = max(0.6, min(1.6, size / 22.0))
    U = max(0.9, size / 13.0)  # plant size: the reference's leaves and flowers read from far off, so big

    def outward(p):
        d = Vector((p.x - centre.x, p.y - centre.y, 0))
        return d.normalized() if d.length > 1e-6 else Vector((1, 0, 0))

    def hug(p, gap):
        """p pushed in or out horizontally to sit gap metres off the rock (None if no rock at that height)."""
        out = outward(p)
        start = Vector((centre.x, centre.y, p.z)) + out * (size * 1.5)
        hit, normal, _, _ = tree.ray_cast(start, -out, size * 1.5)
        if hit is None:
            return None, out
        return hit + out * gap, out

    # Leafy ivy: strands from the rim down the cliffs, hugging the rock, then trailing free below it.
    for base in rim:
        if rng.random() > 0.6:
            continue
        for _ in range(rng.choice((1, 1, 2))):
            p = base.copy() + Vector((rng.uniform(-0.6, 0.6) * U, rng.uniform(-0.6, 0.6) * U, 0.05))
            length = rng.uniform(0.35, 1.0) * (hi.z - lo.z) + (rng.uniform(2, 9) * U if rng.random() < 0.4 else 0)
            green = leaf_green(rng)
            stem_prev = None
            step, travelled, side_flip = 0.36 * U, 0.0, 1
            sway = rng.uniform(0, 6.28)
            while travelled < length:
                p = p - Vector((0, 0, step))
                hugged, out = hug(p, 0.22 * U)
                if hugged is not None and hugged.z > lo.z + 0.3:
                    p = hugged
                else:
                    p = p + Vector((math.sin(sway + travelled * 0.7 / U) * 0.06 * U, math.cos(sway + travelled * 0.5 / U) * 0.06 * U, 0))
                travelled += step
                side = Vector((-out.y, out.x, 0))
                if stem_prev is not None:
                    kit.quad([stem_prev - side * 0.03 * U, stem_prev + side * 0.03 * U, p + side * 0.03 * U, p - side * 0.03 * U],
                             [(0.6, 0.6), (0.7, 0.6), (0.7, 0.7), (0.6, 0.7)], (0.1, 0.22, 0.06), 0)
                stem_prev = p.copy()
                if rng.random() < 0.85:
                    side_flip = -side_flip
                    leaf_size = rng.uniform(0.5, 0.95) * U * (1.0 - 0.35 * travelled / length)
                    tilt = Matrix.Rotation(rng.uniform(-0.6, 0.6), 3, out)
                    down = tilt @ Vector((0, 0, -1))
                    lateral = (tilt @ side) * side_flip
                    root = p + lateral * 0.06 * U + out * 0.05 * U
                    direction = (down * 0.55 + lateral * 0.65 + out * 0.35).normalized()
                    across = direction.cross(out).normalized()
                    shade = rng.uniform(0.75, 1.15)
                    kit.card(root, direction, across, leaf_size, leaf_size * 0.95, LEAF,
                             tuple(min(1, c * shade) for c in green), 0)

    # Glowing flowers in clusters on the cliffs (a fan of petals round a bright bulb).
    weights = np.array([f.calc_area() for f in rock_faces])
    weights = weights / weights.sum()
    clusters = int(rng.uniform(14, 20) * scale)
    for _ in range(clusters):
        f = rock_faces[int(np.searchsorted(np.cumsum(weights), rng.random()))]
        colour = rng.choice(GLOW_COLOURS)
        anchor = f.calc_center_median()
        for _ in range(rng.randint(3, 8)):
            jitter = Vector((rng.uniform(-1.5, 1.5), rng.uniform(-1.5, 1.5), rng.uniform(-1.2, 1.2))) * U
            hit, normal, _, _ = tree.find_nearest(anchor + jitter)
            if hit is None:
                continue
            n = normal.normalized()
            t1 = n.cross(Vector((0, 0, 1)))
            t1 = t1.normalized() if t1.length > 1e-3 else Vector((1, 0, 0))
            t2 = n.cross(t1)
            radius = rng.uniform(0.5, 1.2) * U
            centre_pt = hit + n * 0.08 * U
            petals = rng.choice((6, 7, 8))
            spin = rng.uniform(0, 6.28)
            for k in range(petals):
                a = spin + 2 * math.pi * k / petals
                along = (t1 * math.cos(a) + t2 * math.sin(a))
                across = n.cross(along)
                kit.card(centre_pt + n * 0.03 * U * k / petals, (along + n * 0.25).normalized(), across, radius,
                         radius * 0.42, PETAL, colour, 1)
            kit.blob(centre_pt + n * 0.06 * U, radius * 0.22, tuple(min(1, c * 0.6 + 0.4) for c in colour), 1, sides=5)
            if rng.random() < 0.5:  # a few loose glowing buds round it
                for _ in range(rng.randint(2, 4)):
                    bud = hit + (t1 * rng.uniform(-1, 1) + t2 * rng.uniform(-1, 1)) * radius * 1.6 + n * 0.1 * U
                    kit.blob(bud, rng.uniform(0.06, 0.13) * U, colour, 1, sides=4)

    # A few big glowing anemones, the eye-catchers.
    for _ in range(rng.randint(2, 4)):
        f = rock_faces[int(np.searchsorted(np.cumsum(weights), rng.random() * 0.999))]
        if f.normal.z < -0.5:
            continue
        hit, normal, _, _ = tree.find_nearest(f.calc_center_median())
        n = normal.normalized()
        t1 = n.cross(Vector((0, 0, 1)))
        t1 = t1.normalized() if t1.length > 1e-3 else Vector((1, 0, 0))
        t2 = n.cross(t1)
        colour = rng.choice(GLOW_COLOURS[:3])
        radius = rng.uniform(1.8, 2.8) * U
        for ring, (count, reach, lift) in enumerate(((12, 1.0, 0.15), (9, 0.65, 0.35))):
            spin = rng.uniform(0, 6.28)
            for k in range(count):
                a = spin + 2 * math.pi * k / count
                along = t1 * math.cos(a) + t2 * math.sin(a)
                kit.card(hit + n * (0.1 + 0.1 * ring) * U, (along + n * lift).normalized(), n.cross(along),
                         radius * reach, radius * reach * 0.36, PETAL, colour, 1)
        kit.blob(hit + n * 0.25 * U, radius * 0.2, (0.7, 1.0, 1.0), 1, sides=6)

    # Round the top: big-leaved plants, glowing ferns and glowing mushrooms, mostly near the edge.
    def top_spot(near_rim):
        for _ in range(20):
            f = rng.choice(top_faces)
            p = f.calc_center_median()
            r = Vector((p.x - centre.x, p.y - centre.y)).length
            if not near_rim or r > 0.55 * size / 2:
                return p
        return p

    # The whole top overgrown: a clump of big leaves every few metres, jittered.
    step = 2.4 * U
    xs = np.arange(lo.x, hi.x, step)
    ys = np.arange(lo.y, hi.y, step)
    for gx in xs:
        for gy in ys:
            start = Vector((gx + rng.uniform(0, step), gy + rng.uniform(0, step), hi.z + 5))
            hit, normal, index, _ = tree.ray_cast(start, Vector((0, 0, -1)), hi.z - lo.z + 10)
            if hit is None or bm.faces[index].material_index not in tops:
                continue
            green = leaf_green(rng)
            n_leaves = rng.randint(4, 7)
            for k in range(n_leaves):
                a = 2 * math.pi * k / n_leaves + rng.uniform(-0.4, 0.4)
                out = Vector((math.cos(a), math.sin(a), 0))
                side = Vector((-out.y, out.x, 0))
                length = rng.uniform(0.6, 1.2) * U
                kit.bent_card(hit, (Vector((0, 0, 1)) * 0.7 + out * 0.7).normalized(), side, out, length,
                              length * 0.8, 0.8, LEAF, green, 0, rows=2)
    for _ in range(int(rng.uniform(16, 24) * scale)):  # big-leaved plants
        p = top_spot(True)
        green = leaf_green(rng)
        n_leaves = rng.randint(5, 9)
        for k in range(n_leaves):
            a = 2 * math.pi * k / n_leaves + rng.uniform(-0.3, 0.3)
            out = Vector((math.cos(a), math.sin(a), 0))
            side = Vector((-out.y, out.x, 0))
            length = rng.uniform(0.7, 1.4) * U
            kit.bent_card(p, (Vector((0, 0, 1)) * 0.8 + out * 0.6).normalized(), side, out, length, length * 0.8,
                          0.9, LEAF, green, 0)
    for _ in range(int(rng.uniform(12, 18) * scale)):  # glowing ferns
        p = top_spot(False)
        colour = rng.choice(GLOW_COLOURS)
        fronds = rng.randint(5, 8)
        for k in range(fronds):
            a = 2 * math.pi * k / fronds + rng.uniform(-0.25, 0.25)
            out = Vector((math.cos(a), math.sin(a), 0))
            side = Vector((-out.y, out.x, 0))
            length = rng.uniform(0.9, 1.6) * U
            kit.bent_card(p, (Vector((0, 0, 1)) * 0.9 + out * 0.4).normalized(), side, out, length, length * 0.38,
                          1.1, FERN, colour, 1, rows=4)
    for _ in range(int(rng.uniform(4, 7) * scale)):  # glowing mushrooms
        p = top_spot(False)
        colour = rng.choice(GLOW_COLOURS[2:] + GLOW_COLOURS[:1])
        for _ in range(rng.randint(2, 4)):
            q = p + Vector((rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), 0)) * U
            height = rng.uniform(0.35, 0.9) * U
            cap = rng.uniform(0.18, 0.4) * U
            kit.cone(q + Vector((0, 0, height)), q, 0.05 * U, (0.75, 0.78, 0.8), 0, sides=4)
            kit.cone(q + Vector((0, 0, height + cap * 0.55)), q + Vector((0, 0, height - cap * 0.1)), cap, colour, 1)
    for _ in range(int(rng.uniform(14, 24) * scale)):  # little red flowers in the leaves
        p = top_spot(True) + Vector((0, 0, rng.uniform(0.2, 0.5) * U))
        for k in range(5):
            a = 2 * math.pi * k / 5
            along = Vector((math.cos(a), math.sin(a), 0.3)).normalized()
            kit.card(p, along, Vector((0, 0, 1)).cross(along).normalized(), 0.14 * U, 0.08 * U, PETAL, (0.85, 0.08, 0.06), 0)

    bm.free()
    obj = kit.mesh(path.stem + '_Dress')
    # Back into the floater's own frame (the import's transform undone), so it lines up on export.
    obj.matrix_world = world
    obj.data.transform(world.inverted())
    out = path.with_name(path.stem + '_Dress.fbx')
    bpy.data.objects.remove(rock)
    sl.export_fbx(str(out), [obj])
    return len(kit.f)


def main():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    holes = [int(a) for a in args if a.isdigit()]
    make_atlas()
    paths = sorted(p for p in ISLANDS.glob('SM_H*_Floater??.fbx'))
    names = [a for a in args if a.startswith('SM_H')]
    if holes:
        paths = [p for p in paths if int(p.name[4:6]) in holes]
    if names:
        paths = [p for p in paths if p.stem in names]
    total = 0
    for path in paths:
        tris = dress(path, random.Random(path.stem), strip_vines='novines' in args)
        total += tris
        print(f'DRESS {path.stem}: {tris} triangles')
    print(f'DRESS DONE: {len(paths)} floaters, {total} triangles in all')


if __name__ == '__main__':
    main()
