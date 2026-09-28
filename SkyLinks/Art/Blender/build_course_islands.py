"""Build the floating-island course: holes 1-6, the jungle rope bridges between them, vines, fog and tree plans.

    python Art/Blender/build_course_islands.py            all holes 1-6 plus bridges, then a course preview
    python Art/Blender/build_course_islands.py -- 3 4     just those holes (bridges need their neighbours)
    ... --no-render                                        skip the Cycles previews

Per hole n (world coordinates, Unreal metres; Scripts/apply_floating_islands.py places them at the origin):
  SM_Hnn_IslandTop / IslandRock / Floaters   as hole 1 (build_floating_islands.py), placed, turned and raised
  SM_Hnn_Vines     ivy and roots hanging off every cliff edge (sway in the leaf shader), moss on the rock
  SM_Hnn_Water     ponds and brooks (Water surface: a penalty, and the buggy won't drive in)
  SM_Hnn_Props     wooden footbridges over the brooks (the buggy drives over them)
  Holenn_spots.json  tee, aim, cup, tee markers, par/name, the tree plan ("forest") and fog patches
Course-wide:
  SM_Bridge_nn_mm  a sagging jungle rope bridge from hole n's green end to hole n+1's tee island
"""
import json
import math
import random
import sys
from pathlib import Path

import bpy
import numpy as np
import shapely
from mathutils import Vector
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import nearest_points, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_floating_islands as B  # noqa: E402
import course_layout as C  # noqa: E402
import sl_common as sl  # noqa: E402

OUT = B.OUT
TREE_KINDS = ['Oak_A', 'Oak_B', 'Poplar', 'Pine', 'Birch', 'Bush_Round', 'Bush_Flowering']
WATER_LEVEL = -0.6   # water surface below the hole's tee height (m)
STEEL = 1.0


# ---------------------------------------------------------------- layouts

def design_new(number):
    """Island shape and play regions of holes 2-6 (local metres)."""
    h = C.HOLES[number]
    fairways = unary_union(h['fairways'])
    (cx, cy), gr = h['green']
    green = Point(cx, cy).buffer(gr, 96)
    bunkers = [Point(x, y).buffer(r, 64) for x, y, r in h['bunkers']]
    tee = box(-4, -6, 4, 6)
    ponds = list(h['ponds'])
    streams = [C.path(pts, w) for pts, w in h['streams']]
    woods = unary_union(h['woods']) if h['woods'] else Point(0, 0).buffer(0.01)

    essentials = [fairways.buffer(22), green.buffer(20), tee.buffer(24), woods.buffer(7)]
    essentials += [b.buffer(10) for b in bunkers] + [p.buffer(10) for p in ponds]
    essentials += [LineString(pts).buffer(4) for pts, _ in h['streams']]
    land = unary_union(essentials).buffer(8, 24).buffer(-8, 24)
    land = B.wobble(land, 6.0, 42.0, number * 7 + 1,
                    keep_inside=unary_union([fairways.buffer(8), green.buffer(10), tee.buffer(14)] + [b.buffer(5) for b in bunkers]))
    if isinstance(land, MultiPolygon):
        land = max(land.geoms, key=lambda g: g.area)

    water = unary_union(ponds + streams).intersection(land.buffer(-1.5)) if (ponds or streams) else None
    wet = water if water is not None and not water.is_empty else None
    blocked = unary_union([b for b in bunkers] + [green, tee] + ([wet] if wet else []))
    regions = {
        B.BUNKER: unary_union(bunkers).intersection(land),
        B.GREEN: green.difference(unary_union(bunkers)),
        B.TEE: tee,
    }
    regions[B.FAIRWAY] = fairways.intersection(land).difference(blocked)
    regions[B.ROUGH] = land.difference(unary_union([regions[B.BUNKER], regions[B.GREEN], regions[B.FAIRWAY], tee]))
    return dict(land=land, main=land, regions=regions, fairways=fairways, green=green, bunkers=bunkers, tee=tee,
                cup=(cx, cy), pads=[((-14, 0), 9)], water=wet, woods=woods, streams=streams, ponds=ponds,
                footbridges=h['footbridges'], trees=[], floaters=[])


def layout_for(number):
    if number == 1:
        return B.design_hole(1, B.hole_layouts()[0])
    return design_new(number)


def height_fn(number, layout):
    """Local surface height (m, relative to the tee) as a function of local x, y."""
    if number == 1:
        return lambda x, y: B.top_height(x, y, layout, 1)
    base = lambda x, y: B.top_height(x, y, layout, number)  # noqa: E731
    water = layout['water']
    if water is None:
        return base

    def with_water(x, y):
        h = base(x, y)
        pts = shapely.points(x, y)
        outside = shapely.distance(water, pts)
        inside = shapely.distance(water.boundary, pts) * (outside == 0)
        # Keep the banks above the water line, then drop into a basin under the surface.
        bank = 1 - B.smooth(outside / 8)
        h = np.where(outside > 0, h * (1 - bank) + np.maximum(h, 0.15) * bank, h)
        basin = B.smooth(inside / 2.5)
        return np.where(outside > 0, h, 0.1 * (1 - basin) - 1.8 * basin)
    return with_water


# ---------------------------------------------------------------- mesh helpers (world placement)

def place(number, verts):
    """Local (x, y, z) -> world, adding the hole's height."""
    wx, wy = C.to_world(number, verts[:, 0], verts[:, 1])
    return np.column_stack([wx, wy, verts[:, 2] + C.PLACE[number][2]])


def moss(colours, z, d, x, y, seed):
    """Moss creeping down from the grass lip and in patches on the rock."""
    green = np.array([0.20, 0.30, 0.11])
    patches = B.smooth(0.5 + 1.2 * B.fbm(x / 11, y / 11 + z / 9, 3, seed + 77))
    lip = 1 - B.smooth((d - 0.8) / 4.0)
    amount = np.clip(0.75 * lip * (0.6 + 0.4 * patches) + 0.45 * patches * (1 - lip) * B.smooth((z + 30) / 30), 0, 0.85)
    return colours * (1 - amount[:, None]) + green[None] * amount[:, None]


class Parts:
    """Loose geometry (planks, ropes, posts, vines) with vertex colour RGBA; material 0 bark/wood, 1 leaves."""

    def __init__(self):
        self.v, self.f, self.c, self.m = [], [], [], []

    def _add(self, verts, faces, colour, mat, alpha):
        base = len(self.v)
        self.v.extend(verts)
        cols = colour if callable(colour) else (lambda p: colour)
        for p in verts:
            self.c.append((*cols(p), alpha(p) if callable(alpha) else alpha))
        self.f.extend([tuple(base + i for i in face) for face in faces])
        self.m.extend([mat] * len(faces))

    def box(self, centre, along, across, half, colour, mat=0, alpha=0.0):
        """Oriented box: half = (length, width, height) half sizes along `along`, `across`, their cross."""
        c, a, b = Vector(centre), Vector(along).normalized(), Vector(across).normalized()
        up = a.cross(b).normalized()
        hl, hw, hh = half
        verts = [tuple(c + a * sx * hl + b * sy * hw + up * sz * hh) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        self._add(verts, faces, colour, mat, alpha)

    def tube(self, points, radius, colour, mat=0, alpha=0.0, sides=5):
        pts = [Vector(p) for p in points]
        verts, faces = [], []
        for i, p in enumerate(pts):
            d = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
            side = d.orthogonal().normalized()
            up = d.cross(side)
            r = radius(i / max(1, len(pts) - 1)) if callable(radius) else radius
            for k in range(sides):
                a = 2 * math.pi * k / sides
                verts.append(tuple(p + (side * math.cos(a) + up * math.sin(a)) * r))
        for i in range(len(pts) - 1):
            for k in range(sides):
                a, b = i * sides + k, i * sides + (k + 1) % sides
                faces.append((a, b, b + sides, a + sides))
        self._add(verts, faces, colour, mat, alpha)

    def leaf(self, centre, radius, colour, alpha, rng):
        """Small low-poly leaf clump (icosahedron, 20 triangles)."""
        t = (1 + 5 ** 0.5) / 2
        base = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
                (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
        faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
                 (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
                 (6, 2, 10), (8, 6, 7), (9, 8, 1)]
        c = Vector(centre)
        scale = radius / math.sqrt(1 + t * t)
        verts = [tuple(c + Vector((x * rng.uniform(0.8, 1.2), y * rng.uniform(0.8, 1.2), z * 0.7)) * scale) for x, y, z in base]
        tint = tuple(min(1.0, k * rng.uniform(0.85, 1.15)) for k in colour)
        self._add(verts, [f[::-1] for f in faces], tint, 1, alpha)

    def mesh(self, name, mats=('TreeBark', 'TreeLeaves')):
        v = np.asarray(self.v, float)
        verts = [(float(p[0]), float(-p[1]), float(p[2])) for p in v]  # Unreal -> Blender
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, [], [tuple(int(i) for i in f[::-1]) for f in self.f])
        for name_ in mats:
            mesh.materials.append(bpy.data.materials.get(name_) or vc_material(name_))
        mesh.polygons.foreach_set('material_index', np.asarray(self.m, np.int32))
        attribute = mesh.color_attributes.new('Col', 'BYTE_COLOR', 'POINT')
        attribute.data.foreach_set('color_srgb', np.asarray(self.c, np.float32).ravel())
        mesh.color_attributes.active_color = attribute
        uv = mesh.uv_layers.new(name='UVMap')
        for poly in mesh.polygons:
            for li in poly.loop_indices:
                co = mesh.vertices[mesh.loops[li].vertex_index].co
                uv.data[li].uv = (co.x + co.y, co.z)
        mesh.validate()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        return obj


def vc_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    attr = mat.node_tree.nodes.new('ShaderNodeVertexColor')
    attr.layer_name = 'Col'
    mat.node_tree.links.new(attr.outputs['Color'], mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    return mat


# ---------------------------------------------------------------- vines

VINE_GREENS = [(0.22, 0.42, 0.12), (0.30, 0.50, 0.15), (0.18, 0.34, 0.12), (0.36, 0.52, 0.18)]
ROOT_BROWN = (0.30, 0.20, 0.12)


def hang(parts, rim_xy, outward, top_z, length, rng, leafy):
    """One strand hanging from the rim, drifting away from the cliff as it falls."""
    steps = max(3, int(length / 0.9))
    pts = []
    sway = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)) * 0.25
    for i in range(steps + 1):
        t = i / steps
        p = Vector((rim_xy[0], rim_xy[1], top_z - 0.25)) + Vector((*outward, 0)) * (0.35 + 1.6 * t ** 1.3) \
            + sway * math.sin(t * 5 + rng.uniform(0, 6)) - Vector((0, 0, length * t))
        pts.append(tuple(p))

    def wind(p):
        return min(1.0, 0.1 + (top_z - p[2]) / max(length, 1.0) * 0.9)
    parts.tube(pts, lambda t: 0.06 * (1 - 0.6 * t), ROOT_BROWN if not leafy else (0.25, 0.3, 0.12), 0, wind, sides=4)
    if leafy:
        colour = rng.choice(VINE_GREENS)
        for i, p in enumerate(pts[1:], start=1):
            for _ in range(1 if i % 3 else 2):
                off = Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), rng.uniform(-0.2, 0.2)))
                parts.leaf(Vector(p) + off, rng.uniform(0.35, 0.55), colour, wind(p), rng)


def add_vines(parts, poly, height_local, number, rng, skip=(), density=1.0):
    """Ivy and roots along the island rim (local polygon), written into `parts` in world coordinates."""
    ring = poly.exterior
    pts = np.array([ring.interpolate(s).coords[0] for s in np.arange(0, ring.length, 3.5)])
    ccw = ring.is_ccw
    for i, p in enumerate(pts):
        if rng.random() > 0.55 * density:
            continue
        if any(math.hypot(p[0] - sx, p[1] - sy) < sr for sx, sy, sr in skip):
            continue
        q = pts[(i + 1) % len(pts)] - pts[i - 1]
        outward = np.array([q[1], -q[0]]) / (np.linalg.norm(q) + 1e-9)
        if not ccw:
            outward = -outward
        z = float(height_local(np.array([p[0]]), np.array([p[1]]))[0])
        leafy = rng.random() < 0.72
        length = rng.uniform(4, 16) if leafy else rng.uniform(3, 9)
        # Write straight into world space: turn the outward direction with the hole.
        wx, wy = C.to_world(number, p[0], p[1])
        yaw = math.radians(C.PLACE[number][1])
        ox = outward[0] * math.cos(yaw) - outward[1] * math.sin(yaw)
        oy = outward[0] * math.sin(yaw) + outward[1] * math.cos(yaw)
        hang(parts, (float(wx), float(wy)), (ox, oy), z + C.PLACE[number][2], length, rng, leafy)


# ---------------------------------------------------------------- bridges

WOOD = [(0.42, 0.30, 0.18), (0.36, 0.25, 0.15), (0.48, 0.34, 0.20)]
ROPE = (0.62, 0.52, 0.34)


def rope_bridge(parts, a, b, rng, width=2.4, sag_ratio=0.055, leafy=True):
    """Planks on a sagging deck between two anchor points (world x, y, z), rope rails, hangers, log posts."""
    a, b = Vector(a), Vector(b)
    span = (b - a).length
    sag = 0.8 + span * sag_ratio
    along = (b - a).normalized()
    flat = Vector((along.x, along.y, 0)).normalized()
    across = Vector((-flat.y, flat.x, 0))

    def deck(t):
        return a.lerp(b, t) - Vector((0, 0, sag * 4 * t * (1 - t)))

    count = int(span / 0.42)
    for i in range(count + 1):
        t = i / count
        p = deck(t)
        tangent = (deck(min(1, t + 0.01)) - deck(max(0, t - 0.01))).normalized()
        jitter = Vector((0, 0, rng.uniform(-0.02, 0.02)))
        parts.box(p + jitter, tangent, across, (0.17, width / 2 * rng.uniform(0.9, 1.0), 0.04), rng.choice(WOOD))
    steps = max(8, int(span / 1.2))
    for side in (-1, 1):
        edge = [tuple(deck(i / steps) + across * side * width / 2) for i in range(steps + 1)]
        rail = [tuple(deck(i / steps) + across * side * width / 2 + Vector((0, 0, 1.1 - 0.25 * math.sin(math.pi * i / steps))))
                for i in range(steps + 1)]
        parts.tube(edge, 0.045, ROPE, sides=4)
        parts.tube(rail, 0.05, ROPE, sides=4)
        for i in range(0, steps + 1, 2):
            parts.tube([edge[i], rail[i]], 0.02, ROPE, sides=3)
            if leafy and rng.random() < 0.35:
                for k in range(rng.randint(2, 5)):
                    q = Vector(rail[i]) + Vector((rng.uniform(-0.4, 0.4), rng.uniform(-0.2, 0.2), -k * 0.35))
                    parts.leaf(q, rng.uniform(0.25, 0.4), rng.choice(VINE_GREENS), 0.4, rng)
        for end, sign in ((a, 1), (b, -1)):
            post = end + across * side * (width / 2 + 0.2) - flat * sign * 0.6
            parts.tube([tuple(post - Vector((0, 0, 0.8))), tuple(post + Vector((0, 0, 1.9)))], 0.16, rng.choice(WOOD), sides=6)
            parts.tube([tuple(post + Vector((0, 0, 1.4))), tuple(end + across * side * width / 2 + Vector((0, 0, 1.1)))], 0.035, ROPE, sides=4)
    for end, sign in ((a, 1), (b, -1)):   # crossbar over each end, jungle-gate style
        centre = end - flat * sign * 0.6 + Vector((0, 0, 1.85))
        parts.tube([tuple(centre - across * (width / 2 + 0.4)), tuple(centre + across * (width / 2 + 0.4))], 0.1, rng.choice(WOOD), sides=6)
    return span, sag


def footbridge(parts, number, height_local, centre, heading, length, rng):
    """A short arched wooden footbridge over a brook (local placement), wide enough for the buggy."""
    cx, cy = centre
    ang = math.radians(heading)
    d = np.array([math.cos(ang), math.sin(ang)])
    ends = [np.array(centre) - d * length / 2, np.array(centre) + d * length / 2]
    zs = [float(height_local(np.array([e[0]]), np.array([e[1]]))[0]) for e in ends]
    base = C.PLACE[number][2]
    wa = C.to_world(number, *ends[0])
    wb = C.to_world(number, *ends[1])
    a = Vector((float(wa[0]), float(wa[1]), zs[0] + base + 0.05))
    b = Vector((float(wb[0]), float(wb[1]), zs[1] + base + 0.05))
    along = (b - a).normalized()
    flat = Vector((along.x, along.y, 0)).normalized()
    across = Vector((-flat.y, flat.x, 0))
    width = 3.4
    count = int(length / 0.35)
    for i in range(count + 1):
        t = i / count
        p = a.lerp(b, t) + Vector((0, 0, 0.7 * math.sin(math.pi * t)))
        parts.box(p, flat, across, (0.15, width / 2, 0.06), rng.choice(WOOD))
    for side in (-1, 1):
        rail = [tuple(a.lerp(b, i / 8) + across * side * width / 2 + Vector((0, 0, 0.7 * math.sin(math.pi * i / 8) + 0.95)))
                for i in range(9)]
        parts.tube(rail, 0.06, rng.choice(WOOD), sides=5)
        for i in range(0, 9, 2):
            base_p = a.lerp(b, i / 8) + across * side * width / 2 + Vector((0, 0, 0.7 * math.sin(math.pi * i / 8)))
            parts.tube([tuple(base_p), rail[i]], 0.06, rng.choice(WOOD), sides=5)


# ---------------------------------------------------------------- forest plan

def forest_plan(number, layout, height_local, rng):
    """Where trees and bushes go (world x, y, z, yaw, scale, kind): thick in the woods, sparse in the rough."""
    land = layout['land']
    keep_clear = unary_union([layout['fairways'].buffer(6), layout['green'].buffer(9), layout['tee'].buffer(16)]
                             + [b.buffer(3) for b in layout['bunkers']]
                             + ([layout['water'].buffer(2.5)] if layout.get('water') is not None else []))
    mix = C.HOLES[number]['mix'] if number in C.HOLES else {'Oak_A': 3, 'Oak_B': 3, 'Poplar': 1, 'Birch': 2, 'Bush_Round': 2, 'Bush_Flowering': 1}
    kinds, weights = zip(*mix.items())
    woods = layout.get('woods')
    minx, miny, maxx, maxy = land.bounds
    placed = []
    plan = []
    for _ in range(9000):
        x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
        p = Point(x, y)
        if not land.buffer(-3).contains(p) or keep_clear.contains(p):
            continue
        in_wood = woods is not None and woods.contains(p)
        spacing = 6.5 if in_wood else 15.0
        if any((x - px) ** 2 + (y - py) ** 2 < spacing ** 2 for px, py in placed):
            continue
        if not in_wood and rng.random() < 0.55:
            continue
        kind = rng.choices(kinds, weights)[0]
        z = float(height_local(np.array([x]), np.array([y]))[0])
        wx, wy = C.to_world(number, x, y)
        plan.append([round(float(wx), 2), round(float(wy), 2), round(z + C.PLACE[number][2] - 0.1, 2),
                     round(rng.uniform(0, 360), 1), round(rng.uniform(0.8, 1.2), 2), kind])
        placed.append((x, y))
    return plan


# ---------------------------------------------------------------- build one hole

def build_hole(number, rng):
    layout = layout_for(number)
    local_h = height_fn(number, layout)
    sl.reset_scene()
    B.build_materials()
    name = f'SM_H{number:02d}'

    xy, tris, attrs = B.triangulate_top(layout)
    z = local_h(xy[:, 0], xy[:, 1])
    top = B.make_mesh(f'{name}_IslandTop', place(number, np.column_stack([xy, z])), tris, attrs,
                      [B.REGION_MATERIAL[i] for i in range(5)], B.top_colours(xy[:, 0], xy[:, 1], number))

    land = layout['land']
    uxy, utris = B.triangulate_underside(land, [0.8, 2.0, 4.0, 7.5, 13, 21, 32], 14)
    if number == 1:
        pts = shapely.points(uxy[:, 0], uxy[:, 1])
        depth = np.where(shapely.distance(layout['main'], pts) < 1e-6, B.DESIGNS[1]['depth'][0], B.DESIGNS[1]['depth'][1])
    else:
        depth = np.full(len(uxy), 40.0 + 0.1 * math.sqrt(land.area))
    rock_v, dist, t = B.underside(uxy, land, local_h, depth, number * 13)
    colours = moss(B.rock_colours(rock_v[:, 2], dist, t, uxy[:, 0], uxy[:, 1], number), rock_v[:, 2], dist,
                   uxy[:, 0], uxy[:, 1], number)
    rock = B.make_mesh(f'{name}_IslandRock', place(number, rock_v), utris[:, ::-1], np.zeros(len(utris), int),
                       ['IslandRock'], colours)

    # Floaters: hole 1 keeps its hand-placed ones; the others get a ring of small islands.
    floaters = layout['floaters'] if number == 1 else ring_of_floaters(number, land, rng)
    f_parts = [], [], [], []
    offset = 0
    vines = Parts()
    skip = [(0, 0, 18)]  # keep the tee edge clear
    for i, (poly, top_z) in enumerate(floaters):
        fn = lambda x, y, tz=top_z, s=i, pl=poly: tz + 0.8 * B.fbm(x / 12, y / 12, 3, 500 + s) - 0.6 * (1 - B.smooth(  # noqa: E731
            shapely.distance(pl.exterior, shapely.points(x, y)) / 3))
        vx, tx = B.triangulate_underside(poly, [], 1.5)
        f_parts[0].append(place(number, np.column_stack([vx, fn(vx[:, 0], vx[:, 1])])))
        f_parts[1].append(tx + offset)
        f_parts[2].append(np.zeros(len(tx), int))
        f_parts[3].append(B.top_colours(vx[:, 0], vx[:, 1], number))
        offset += len(vx)
        ux, ut = B.triangulate_underside(poly, [0.8, 2.0, 4.0, 7.0], 6)
        radius = math.sqrt(poly.area / math.pi)
        rv, rd, rt = B.underside(ux, poly, fn, radius * 1.7, 700 + i + number * 50)
        f_parts[0].append(place(number, rv))
        f_parts[1].append(ut[:, ::-1] + offset)
        f_parts[2].append(np.ones(len(ut), int))
        f_parts[3].append(moss(B.rock_colours(rv[:, 2], rd, rt, ux[:, 0], ux[:, 1], 700 + i), rv[:, 2], rd, ux[:, 0], ux[:, 1], i))
        offset += len(ux)
        add_vines(vines, poly, fn, number, rng, density=0.8)
    floater_obj = B.make_mesh(f'{name}_Floaters', np.concatenate(f_parts[0]), np.concatenate(f_parts[1]),
                              np.concatenate(f_parts[2]), ['Rough', 'IslandRock'], np.concatenate(f_parts[3]))

    add_vines(vines, land, local_h, number, rng, skip=skip)
    vine_obj = vines.mesh(f'{name}_Vines')
    exported = [top, rock, floater_obj, vine_obj]

    if layout.get('water') is not None:
        wxy, wtris = B.triangulate_underside(layout['water'], [], 6)
        wv = place(number, np.column_stack([wxy, np.full(len(wxy), WATER_LEVEL)]))
        exported.append(B.make_mesh(f'{name}_Water', wv, wtris, np.zeros(len(wtris), int), ['Water'],
                                    np.tile([0.5, 0.0, 0.0], (len(wv), 1))))
    if layout.get('footbridges'):
        props = Parts()
        for centre, heading, length in layout['footbridges']:
            footbridge(props, number, local_h, centre, heading, length, rng)
        exported.append(props.mesh(f'{name}_Props'))

    for obj in exported:
        sl.export_fbx(str(OUT / f'{obj.name}.fbx'), [obj])

    def ground(x, y):
        return round(float(local_h(np.array([x], float), np.array([y], float))[0]) + C.PLACE[number][2], 3)

    def world(x, y):
        wx, wy = C.to_world(number, x, y)
        return [round(float(wx), 3), round(float(wy), 3), ground(x, y)]
    cx, cy = layout['cup']
    info = C.HOLES.get(number, dict(name='Harbor Point', par=4, aim=(240, 0)))
    spots = {'hole': number, 'name': info['name'], 'par': info['par'],
             'tee': world(0, 0), 'yaw': C.PLACE[number][1], 'aim_local': list(info['aim']),
             'cup': world(cx, cy), 'tee_markers': [world(1.5, s * 2.5) for s in (-1, 1)],
             'player_start': world(-5.0, 0.0),
             'gameplay_trees': [world(x, y) for x, y in layout['trees']],
             'forest': forest_plan(number, layout, local_h, rng)}
    if number == 1:
        spots['trees'] = [[x, y, ground(x, y)] for x, y in layout['trees']]
        spots['clubhouse'] = [*B.DESIGNS[1]['clubhouse'], ground(*B.DESIGNS[1]['clubhouse'])]
    (OUT / f'Hole{number:02d}_spots.json').write_text(json.dumps(spots, indent=1) + '\n')
    print(f'HOLE {number} {spots["name"]}: top {len(tris)}, rock {len(utris)}, vines {len(vines.f)} faces, '
          f'{len(floaters)} floaters, {len(spots["forest"])} trees, water {layout.get("water") is not None}')
    return layout, local_h


def ring_of_floaters(number, land, rng):
    """Seven small islands scattered round a hole (local), clear of the island itself."""
    out = []
    for i in range(40):
        if len(out) >= 7:
            break
        edge = land.exterior.interpolate(rng.uniform(0, land.exterior.length))
        c = land.centroid
        away = np.array([edge.x - c.x, edge.y - c.y])
        away /= np.linalg.norm(away) + 1e-9
        centre = np.array([edge.x, edge.y]) + away * rng.uniform(28, 70) + np.array([rng.uniform(-15, 15), rng.uniform(-15, 15)])
        radius = rng.uniform(6, 15)
        blob = B.wobble(Point(*centre).buffer(radius, 48), radius * 0.35, radius * 1.4, 900 + number * 20 + i)
        if blob.distance(land) < 12 or any(blob.distance(o) < 8 for o, _ in out):
            continue
        out.append((blob, rng.uniform(-30, 10)))
    return out


# ---------------------------------------------------------------- course: bridges and fog

def world_land(number, layout):
    return C.world_geom(number, layout['land'])


def build_bridges(layouts, rng):
    """Rope bridge from each hole's green end to the next hole's tee island."""
    bridges = []
    for n in range(1, 6):
        if n not in layouts or n + 1 not in layouts:
            continue
        la, ha = layouts[n]
        lb, hb = layouts[n + 1]
        wa, wb = world_land(n, la), world_land(n + 1, lb)
        cup = Point(*C.to_world(n, *la['cup']))
        tee = Point(*C.to_world(n + 1, 0, 0))
        near_a = wa.intersection(cup.buffer(110))
        near_b = wb.intersection(tee.buffer(90))
        pa, pb = nearest_points(near_a.boundary, near_b.boundary)
        va = np.array([pb.x - pa.x, pb.y - pa.y])
        va /= np.linalg.norm(va)
        # Step 4 m in from each cliff edge so the posts stand on grass.
        ax, ay = pa.x - va[0] * 4, pa.y - va[1] * 4
        bx, by = pb.x + va[0] * 4, pb.y + va[1] * 4
        za = float(ha(*[np.array([v]) for v in C.to_local(n, ax, ay)])[0]) + C.PLACE[n][2]
        zb = float(hb(*[np.array([v]) for v in C.to_local(n + 1, bx, by)])[0]) + C.PLACE[n + 1][2]
        parts = Parts()
        span, sag = rope_bridge(parts, (ax, ay, za + 0.1), (bx, by, zb + 0.1), rng)
        obj = parts.mesh(f'SM_Bridge_{n:02d}_{n + 1:02d}')
        sl.export_fbx(str(OUT / f'{obj.name}.fbx'), [obj])
        bridges.append(dict(name=obj.name, a=[ax, ay, za], b=[bx, by, zb], span=round(span, 1), sag=round(sag, 1)))
        print(f'BRIDGE {n}->{n + 1}: {span:.0f} m, drop {za - zb:+.1f} m, sag {sag:.1f} m')
    return bridges


def fog_plan(layouts, bridges, rng):
    """Cloud-like fog patches: under every bridge and drifting in the gaps round each island."""
    fog = []
    for b in bridges:
        mid = (np.array(b['a']) + np.array(b['b'])) / 2
        fog.append([round(float(mid[0]), 1), round(float(mid[1]), 1), round(float(mid[2]) - rng.uniform(14, 26), 1),
                    round(rng.uniform(45, 70), 1)])
    for n, (layout, _) in layouts.items():
        land = world_land(n, layout)
        for _ in range(4):
            edge = land.exterior.interpolate(rng.uniform(0, land.exterior.length))
            away = np.array([edge.x - land.centroid.x, edge.y - land.centroid.y])
            away /= np.linalg.norm(away)
            p = np.array([edge.x, edge.y]) + away * rng.uniform(40, 90)
            fog.append([round(float(p[0]), 1), round(float(p[1]), 1),
                        round(C.PLACE[n][2] - rng.uniform(20, 45), 1), round(rng.uniform(55, 95), 1)])
    return fog


def check_course(layouts):
    """No two islands closer than 25 m (floaters aside)."""
    worlds = {n: world_land(n, l) for n, (l, _) in layouts.items()}
    for n, w in worlds.items():
        print(f'BOUNDS hole {n}: x {w.bounds[0]:.0f}..{w.bounds[2]:.0f}, y {w.bounds[1]:.0f}..{w.bounds[3]:.0f}, z {C.PLACE[n][2]:+.0f}')
    ok = True
    for a in worlds:
        for b in worlds:
            if a < b:
                gap = worlds[a].distance(worlds[b])
                if gap < 25:
                    ok = False
                print(f'GAP hole {a} - hole {b}: {gap:.0f} m' + ('  <-- too close' if gap < 25 else ''))
    return ok


def render_course(layouts):
    """An aerial overview of all built islands, bridges included (imports the FBXs just written)."""
    sl.reset_scene()
    for fbx in sorted(OUT.glob('SM_*.fbx')):
        if fbx.stem.startswith(('SM_H', 'SM_Bridge')):
            bpy.ops.import_scene.fbx(filepath=str(fbx))
    for mat in bpy.data.materials:
        if mat.use_nodes and 'Principled BSDF' in mat.node_tree.nodes and not any(n.type == 'VERTEX_COLOR' for n in mat.node_tree.nodes):
            attr = mat.node_tree.nodes.new('ShaderNodeVertexColor')
            attr.layer_name = 'Col'
            colours = {'Rough': (0.05, 0.13, 0.02), 'Fairway': (0.08, 0.22, 0.03), 'Green': (0.09, 0.27, 0.04),
                       'TeeBox': (0.08, 0.22, 0.03), 'Bunker': (0.42, 0.33, 0.2), 'Water': (0.02, 0.07, 0.1)}
            key = next((k for k in colours if mat.name.startswith(k)), None)
            if key:
                mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (*colours[key], 1)
            else:
                mat.node_tree.links.new(attr.outputs['Color'], mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    scene = bpy.context.scene
    world = bpy.data.worlds.new('Sky')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.45, 0.62, 0.9, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.8
    scene.world = world
    sun_data = bpy.data.lights.new('Sun', 'SUN')
    sun_data.energy = 3.5
    sun = bpy.data.objects.new('Sun', sun_data)
    sun.rotation_euler = (math.radians(40), 0, math.radians(-150))
    scene.collection.objects.link(sun)
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 1600, 1000
    scene.view_settings.view_transform = 'AgX'
    for label, eye, target, lens in (('course', (-500, 900, 700), (330, 950, -20), 24),
                                     ('closeup', (150, 330, 60), (360, 300, 5), 28)):
        cam_data = bpy.data.cameras.new(label)
        cam_data.lens = lens
        cam_data.clip_end = 10000
        cam = bpy.data.objects.new(label, cam_data)
        cam.location = Vector((eye[0], -eye[1], eye[2]))
        cam.rotation_euler = (Vector((target[0], -target[1], target[2])) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        scene.collection.objects.link(cam)
        scene.camera = cam
        scene.render.filepath = str(OUT / f'Course_preview_{label}.png')
        bpy.ops.render.render(write_still=True)


def main():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    wanted = [int(a) for a in args if a.isdigit()] or [1, 2, 3, 4, 5, 6]
    OUT.mkdir(parents=True, exist_ok=True)
    layouts = {}
    for number in sorted(set(wanted) | {n for w in wanted for n in (w - 1, w + 1) if 1 <= n <= 6}):
        layouts[number] = (layout_for(number), None)
    for number in layouts:
        layouts[number] = (layouts[number][0], height_fn(number, layouts[number][0]))
    if '--check' in args:
        check_course(layouts)
        return
    for number in wanted:
        layout, local_h = build_hole(number, random.Random(number * 1009))
        layouts[number] = (layout, local_h)
    check_course(layouts)
    rng = random.Random(77)
    bridges = build_bridges(layouts, rng)
    fog = fog_plan({n: layouts[n] for n in wanted}, bridges, rng)
    (OUT / 'Course_links.json').write_text(json.dumps({'bridges': bridges, 'fog': fog}, indent=1) + '\n')
    if '--no-render' not in args:
        render_course(layouts)


if __name__ == '__main__':
    main()
