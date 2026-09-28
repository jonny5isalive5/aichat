"""Floating-island terrain for Sky Links holes (Pangya-style islands hanging in the sky).

Replaces a hole's flat landscape with meshes:
  SM_H01_IslandTop    the playable grass top, one material slot per surface so the ball physics reads
                      the lie (Rough, Fairway, Green, Bunker, TeeBox); crisp mown edges along the
                      fairway/green/bunker outlines
  SM_H01_IslandRock   rocky undersides hanging below each island, soil band under the grass lip,
                      layered rock strata in the vertex colours
  SM_H01_Floaters     small decorative islands drifting around the hole (grass top + rock)

Everything between the islands is empty sky: a ball that misses falls below GolfPhysics::KillZ (-50 m)
and is out of bounds. A natural stone bridge joins the tee island to the fairway so the buggy can cross.

Coordinates here are Unreal world metres of the hole (x toward the green, y to the right). The FBX
export mirrors y for Blender's right-handed axes, so the meshes land in place with the actor at the
world origin. Heights: tee at 0; the cup height is printed for the import script, which traces it anyway.

    python Art/Blender/build_floating_islands.py        (bpy module, numpy, shapely, triangle)

Writes Art/Exports/Islands/*.fbx, preview renders, and tiling detail textures in Art/Textures.
Scripts/apply_floating_islands.py imports and places them in the Course map.
"""
import ast
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh  # noqa: F401  (needs bpy first)
import numpy as np
import shapely
import triangle
from mathutils import Vector
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sl_common as sl  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'Art' / 'Exports' / 'Islands'
TEXTURES = ROOT / 'Art' / 'Textures'

# Region ids, their FBX material names (the import script maps them to Unreal materials) and triangle sizes.
ROUGH, FAIRWAY, GREEN, BUNKER, TEE = range(5)
REGION_MATERIAL = {ROUGH: 'Rough', FAIRWAY: 'Fairway', GREEN: 'Green', BUNKER: 'Bunker', TEE: 'TeeBox'}
REGION_MAX_AREA = {ROUGH: 1.2, FAIRWAY: 0.8, GREEN: 0.35, BUNKER: 0.5, TEE: 0.5}
EDGE_SPACING = 0.8  # metres between vertices along every outline (rims match exactly between top and rock)
GREEN_SLOPES = [(0.012, 0.009)]  # same putting slopes as Scripts/generate_golf_terrain.py

# Island designs per hole. Shapes are built from the hole layout; these add the parts only a designer knows.
DESIGNS = {
    1: dict(
        # Clubhouse lawn and the tee on the home island; the tee sticks out on a tongue toward the hole.
        home=[('ellipse', (-110, -45), (72, 52)), ('rect', (-75, 12, -17, 17), None)],
        # Main island starts a 22 m carry past the tee and runs to behind the green.
        main_start=33,
        # Natural stone bridge (7 m wide) for the buggy, off the line of play.
        bridges=[[(2, -12), (18, -24), (40, -32)]],
        # Decorative floaters: centre (x, y), radius, top height (m).
        floaters=[((70, -100), 11, -14), ((185, -112), 16, 6), ((265, 98), 13, -22), ((125, 96), 8, -6),
                  ((335, -86), 9, -28), ((-35, 62), 12, -18), ((430, 40), 14, -12), ((-190, 30), 10, -30),
                  ((20, 75), 6, 9), ((400, -60), 7, 4)],
        depth=(62, 48),  # underside depth of the biggest island and of the home island
        # Flat pads (centre, radius): clubhouse with its putting green and car park, buggy parking behind the tee.
        pads=[((-110, -45), 44), ((-14, 0), 9)],
        clubhouse=(-110, -45),
    ),
}


# ---------------------------------------------------------------- noise

def _hash(ix, iy, seed):
    h = (ix * 374761393 + iy * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return (h ^ (h >> 16)) & 0xFFFFFFFF


def noise2(x, y, seed=0):
    """Gradient noise in about [-1, 1], vectorised."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx, fy = x - x0, y - y0

    def grad(ix, iy, dx, dy):
        angle = _hash(ix, iy, seed).astype(float) / 4294967296.0 * 2 * math.pi
        return np.cos(angle) * dx + np.sin(angle) * dy

    u = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
    v = fy * fy * fy * (fy * (fy * 6 - 15) + 10)
    n00 = grad(x0, y0, fx, fy)
    n10 = grad(x0 + 1, y0, fx - 1, fy)
    n01 = grad(x0, y0 + 1, fx, fy - 1)
    n11 = grad(x0 + 1, y0 + 1, fx - 1, fy - 1)
    return 1.4 * ((n00 * (1 - u) + n10 * u) * (1 - v) + (n01 * (1 - u) + n11 * u) * v)


def fbm(x, y, octaves=4, seed=0):
    total, amplitude, frequency, norm = 0.0, 1.0, 1.0, 0.0
    for octave in range(octaves):
        total = total + amplitude * noise2(x * frequency, y * frequency, seed + octave * 17)
        norm += amplitude
        amplitude *= 0.5
        frequency *= 2.03
    return total / norm


def smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- layout

def hole_layouts():
    source = (ROOT / 'Scripts' / 'build_blockout_course.py').read_text()
    node = next(n for n in ast.parse(source).body
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'HOLES' for t in n.targets))
    return eval(compile(ast.Expression(node.value), '<holes>', 'eval'), {'__builtins__': {}, 'dict': dict, 'range': range})


def shape(kind, centre, size):
    if kind == 'ellipse':
        return shapely.affinity.scale(Point(centre).buffer(1.0, 48), size[0], size[1])
    x0, x1, y0, y1 = centre
    return box(x0, y0, x1, y1)


def wobble(poly, amplitude, wavelength, seed, keep_inside=None):
    """Organic outline: push each outline point along its normal by noise, never inside `keep_inside`."""
    ring = shapely.segmentize(poly.exterior, 2.0)
    pts = np.array(ring.coords)[:-1]
    prev, nxt = np.roll(pts, 1, 0), np.roll(pts, -1, 0)
    tangent = nxt - prev
    normal = np.stack([tangent[:, 1], -tangent[:, 0]], 1)
    normal /= np.linalg.norm(normal, axis=1, keepdims=True) + 1e-9
    if Polygon(pts).exterior.is_ccw:
        normal = -normal  # outward
    offset = amplitude * fbm(pts[:, 0] / wavelength, pts[:, 1] / wavelength, 3, seed)
    result = Polygon(pts + normal * offset[:, None]).buffer(0)
    if isinstance(result, MultiPolygon):
        result = max(result.geoms, key=lambda g: g.area)
    if keep_inside is not None:
        result = result.union(keep_inside)
    # Round off pinches and needle points.
    return result.buffer(3.0, 24).buffer(-3.0, 24)


def design_hole(number, hole):
    d = DESIGNS[number]
    fairways = unary_union([box(x0, y0, x1, y1).buffer(3.0, 16).buffer(-3.0, 16) for x0, x1, y0, y1 in hole['fairway']])
    cx, cy = hole['cup']
    green = Point(cx, cy).buffer(hole['green'], 96)
    bunkers = [Point(x, y).buffer(r, 64) for x, y, r in hole.get('bunkers', [])]
    tee = box(-4, -6, 4, 6)

    # Everything that must be on solid ground, with a safety margin to the cliff edge.
    essentials = [fairways.buffer(24), green.buffer(20)] + [b.buffer(9) for b in bunkers]
    essentials += [Point(x, y).buffer(11) for x, y in hole.get('trees', [])]
    main = unary_union(essentials).buffer(8, 24).buffer(-8, 24)
    main = main.intersection(box(d['main_start'], -1e4, 1e4, 1e4))
    main = wobble(main, 7.0, 45.0, number * 7 + 1,
                  keep_inside=unary_union([fairways.buffer(9), green.buffer(9)] + [b.buffer(5) for b in bunkers]))

    home = unary_union([shape(k, c, s) for k, c, s in d['home']])
    home = wobble(home, 6.0, 35.0, number * 7 + 2, keep_inside=tee.buffer(8))
    bridges = [LineString(p).buffer(3.5, 16) for p in d['bridges']]
    land = unary_union([main, home] + bridges).buffer(1.5, 16).buffer(-1.5, 16)
    if isinstance(land, MultiPolygon):
        land = max(land.geoms, key=lambda g: g.area)

    floaters = []
    for i, ((fx, fy), radius, top) in enumerate(d['floaters']):
        blob = wobble(Point(fx, fy).buffer(radius, 48), radius * 0.35, radius * 1.4, 300 + i)
        floaters.append((blob.difference(land.buffer(6)), top))
    floaters = [(p, top) for p, top in floaters if not p.is_empty and p.area > 20]

    regions = {
        BUNKER: unary_union(bunkers).intersection(land),
        GREEN: green.difference(unary_union(bunkers)),
        TEE: tee,
    }
    regions[FAIRWAY] = fairways.intersection(land).difference(unary_union([regions[BUNKER], green, tee]))
    regions[ROUGH] = land.difference(unary_union([regions[BUNKER], regions[GREEN], regions[FAIRWAY], tee]))
    return dict(land=land, main=main, home=home, regions=regions, fairways=fairways, green=green, pads=d['pads'],
                bunkers=bunkers, tee=tee, cup=(cx, cy), floaters=floaters, trees=hole.get('trees', []))


# ---------------------------------------------------------------- heights

def top_height(x, y, layout, number):
    """Surface height (m) of the playable top at points x, y."""
    pts = shapely.points(x, y)
    land = layout['land']
    edge = shapely.distance(land.exterior, pts)

    # Rolling rough, calmer fairway, flat tee, planar putting green, sunken bunkers, rounded rim.
    rough = 1.6 * fbm(x / 70, y / 70, 4, number) + 0.5 * fbm(x / 22, y / 22, 3, number + 50)
    fair_dist = shapely.distance(layout['fairways'], pts)
    fair = 1 - smooth(fair_dist / 10)
    h = rough * (1 - 0.8 * fair) + 0.25 * fbm(x / 40, y / 40, 2, number + 90) * fair

    cx, cy = layout['cup']
    sx, sy = GREEN_SLOPES[(number - 1) % len(GREEN_SLOPES)]
    r = np.hypot(x - cx, y - cy)
    radius = layout['green'].exterior.distance(Point(cx, cy))
    green_h = 0.3 + sx * (x - cx) + sy * (y - cy)
    blend = 1 - smooth((r - radius - 1) / 12)
    h = h * (1 - blend) + green_h * blend

    for b in layout['bunkers']:
        c = b.centroid
        br = b.exterior.distance(c)
        bowl = 1 - smooth((np.hypot(x - c.x, y - c.y) / br - 0.35) / 0.65)
        h = h - 0.45 * bowl

    tee_d = shapely.distance(layout['tee'], pts)
    h = h * smooth(tee_d / 8)
    for (px, py), pr in layout['pads']:
        h = h * smooth((np.hypot(x - px, y - py) - pr) / 10)

    # Grass lip rolls over at the cliff edge.
    h = h - 0.9 * (1 - smooth(edge / 5))
    return h


# ---------------------------------------------------------------- triangulation

def polygon_rings(poly):
    polys = poly.geoms if isinstance(poly, MultiPolygon) else [poly]
    for p in polys:
        yield p.exterior
        yield from p.interiors


def pslg(lines, spacing):
    """Noded, densified line work -> triangle vertices and segments (shared vertices merged).
    `lines` items are LineStrings, or (LineString, own spacing) pairs."""
    noded = unary_union([shapely.segmentize(*(l if isinstance(l, tuple) else (l, spacing))) for l in lines])
    geoms = noded.geoms if hasattr(noded, 'geoms') else [noded]
    index, vertices, segments = {}, [], []

    def vid(p):
        key = (round(p[0], 4), round(p[1], 4))
        if key not in index:
            index[key] = len(vertices)
            vertices.append(key)
        return index[key]

    for g in geoms:
        coords = list(g.coords)
        for a, b in zip(coords[:-1], coords[1:]):
            ia, ib = vid(a), vid(b)
            if ia != ib:
                segments.append((ia, ib))
    return np.array(vertices, float), np.array(segments, int)


def triangulate_top(layout):
    lines = [LineString(r.coords) for region in layout['regions'].values() for r in polygon_rings(region)]
    # Extra outlines to keep as mesh edges (footpath borders), so painted-in features get crisp edges.
    lines += [LineString(r.coords) for g in layout.get('extra_lines', []) for r in polygon_rings(g)]
    vertices, segments = pslg(lines, EDGE_SPACING)
    seeds = []
    for region_id, region in layout['regions'].items():
        for part in (region.geoms if hasattr(region, 'geoms') else [region]):
            if part.area > 0.5:
                p = part.representative_point()
                seeds.append([p.x, p.y, region_id, REGION_MAX_AREA[region_id]])
    result = triangle.triangulate(dict(vertices=vertices, segments=segments, regions=np.array(seeds)), 'pq28aAY')
    return result['vertices'], result['triangles'], result['triangle_attributes'][:, 0].astype(int)


def triangulate_underside(poly, ring_offsets, max_area):
    lines = [LineString(r.coords) for r in polygon_rings(poly)]
    for offset in ring_offsets:
        inner = poly.buffer(-offset, 4).simplify(0.4 + offset * 0.08)
        if not inner.is_empty:
            # Inner rings only shape the cliff profile; they can be much coarser than the rim.
            lines += [(LineString(r.coords), 1.5 + offset * 0.35) for r in polygon_rings(inner)]
    vertices, segments = pslg(lines, EDGE_SPACING)
    # Keep the outline spacing (so the rim matches the top) but let the inside grow coarse.
    result = triangle.triangulate(dict(vertices=vertices, segments=segments), f'pq20a{max_area}Y')
    return result['vertices'], result['triangles']


def underside(xy, poly, top_fn, depth, seed):
    """Rock hanging below an island: sheer cliff under the lip, strata ledges, tapering to a point."""
    x, y = xy[:, 0], xy[:, 1]
    pts = shapely.points(x, y)
    d = shapely.distance(poly.exterior, pts)
    for hole in poly.interiors:
        d = np.minimum(d, shapely.distance(hole, pts))
    inscribed = max(float(d.max()), 1.0)
    top = top_fn(x, y)
    t = np.clip(d / inscribed, 0, 1)
    # Hanging lobes: the bottom is a cluster of rocky stalactites, not one wedge.
    lobes = 0.35 + 1.25 * smooth(0.5 + 0.9 * fbm(x / 26, y / 26, 3, seed + 41)) ** 1.6
    drop = 3.5 * (1 - np.exp(-d / 0.8)) + 3.0 * smooth(d / 5) + depth * t ** 0.8 * lobes
    drop *= 1 + 0.15 * fbm(x / 12, y / 12, 3, seed)
    z = top - drop
    # Horizontal strata: ledges every few metres, broken up by noise.
    z = z + 0.7 * np.sin(z * 1.4 + 2.0 * fbm(x / 15, y / 15, 2, seed + 5)) * smooth(d / 3)
    # Bulge the walls in and out so the cliff reads as rock, not an extrusion (rim stays put).
    push = smooth(d / 2.5) * (1 - 0.6 * t)
    dx = 2.4 * fbm(x / 9 + z / 7, y / 9, 3, seed + 11) * push
    dy = 2.4 * fbm(x / 9, y / 9 - z / 7, 3, seed + 23) * push
    return np.stack([x + dx, y + dy, z], 1), d, t


# ---------------------------------------------------------------- colours

def srgb(c):
    return np.asarray(c, float)


def rock_colours(z, d, t, x, y, seed):
    soil = srgb((0.36, 0.23, 0.13))
    rock_a = srgb((0.58, 0.44, 0.31))
    rock_b = srgb((0.44, 0.34, 0.26))
    rock_c = srgb((0.66, 0.57, 0.45))
    band = 0.5 + 0.5 * np.sin(z * 0.9 + 3.0 * fbm(x / 20, y / 20, 2, seed))
    grain = 0.5 + 0.5 * fbm(x / 4 + z, y / 4 - z, 2, seed + 3)
    rock = rock_a[None] * (1 - band[:, None]) + rock_b[None] * band[:, None]
    rock = rock * (1 - 0.35 * grain[:, None]) + rock_c[None] * 0.35 * grain[:, None]
    soil_mix = 1 - smooth((d - 0.4) / 2.2)
    colour = rock * (1 - soil_mix[:, None]) + soil[None] * soil_mix[:, None]
    # Darker, mossy toward the tip underneath.
    colour = colour * (1 - 0.35 * smooth((t - 0.5) / 0.5))[:, None]
    return np.clip(colour, 0, 1)


def top_colours(x, y, number):
    """R: broad colour variation, G: mowing stripes along the hole, B: unused."""
    variation = 0.5 + 0.5 * fbm(x / 18, y / 18, 3, number + 200)
    stripes = (np.floor(x / 6.0) % 2).astype(float)
    return np.stack([variation, stripes, np.zeros_like(x)], 1)


# ---------------------------------------------------------------- Blender meshes

def make_mesh(name, verts_ue, faces, face_materials, material_names, colours, smooth_shading=True, uv_scale=4.0):
    """verts_ue: Unreal-frame metres. Mirrors y for Blender and flips winding so normals stay outward."""
    verts = [(float(v[0]), float(-v[1]), float(v[2])) for v in verts_ue]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], [tuple(int(i) for i in f[::-1]) for f in faces])
    for material_name in material_names:
        mesh.materials.append(bpy.data.materials.get(material_name) or bpy.data.materials.new(material_name))
    mesh.polygons.foreach_set('material_index', np.asarray(face_materials, np.int32))
    mesh.polygons.foreach_set('use_smooth', np.full(len(faces), smooth_shading))

    attribute = mesh.color_attributes.new('Col', 'BYTE_COLOR', 'POINT')
    rgba = np.concatenate([np.asarray(colours, np.float32), np.ones((len(verts), 1), np.float32)], 1)
    attribute.data.foreach_set('color_srgb', rgba.ravel())
    mesh.color_attributes.active_color = attribute

    # Box-projected UVs, uv_scale metres per tile.
    uv = mesh.uv_layers.new(name='UVMap')
    co = np.asarray(verts)
    loops_v = np.zeros(len(mesh.loops), np.int32)
    mesh.loops.foreach_get('vertex_index', loops_v)
    normals = np.zeros(len(mesh.polygons) * 3, np.float32)
    mesh.update()
    mesh.polygons.foreach_get('normal', normals)
    normals = np.abs(normals.reshape(-1, 3))
    loop_poly = np.zeros(len(mesh.loops), np.int32)
    for poly in mesh.polygons:
        loop_poly[poly.loop_start:poly.loop_start + poly.loop_total] = poly.index
    n = normals[loop_poly]
    p = co[loops_v]
    u = np.where(n[:, 2] >= np.maximum(n[:, 0], n[:, 1]), p[:, 0], np.where(n[:, 0] >= n[:, 1], p[:, 1], p[:, 0]))
    v = np.where(n[:, 2] >= np.maximum(n[:, 0], n[:, 1]), p[:, 1], p[:, 2])
    uv.data.foreach_set('uv', (np.stack([u, v], 1) / uv_scale).astype(np.float32).ravel())

    mesh.validate()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def preview_material(name, base, variation=0.0, stripes=0.0, use_colour=False, roughness=0.85):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = roughness
    links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    attr = nodes.new('ShaderNodeVertexColor')
    attr.layer_name = 'Col'
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 0.6
    noise.inputs['Detail'].default_value = 8
    if use_colour:
        mix = nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 0.35
        links.new(attr.outputs['Color'], mix.inputs['A'])
        links.new(noise.outputs['Color'], mix.inputs['B'])
        links.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
        return mat
    sep = nodes.new('ShaderNodeSeparateColor')
    links.new(attr.outputs['Color'], sep.inputs['Color'])
    # base * (1 - variation * (0.5 - R)) * (1 - stripes * G)
    ramp = nodes.new('ShaderNodeMath')
    ramp.operation = 'MULTIPLY_ADD'
    ramp.inputs[1].default_value = variation
    ramp.inputs[2].default_value = 1 - variation * 0.5
    links.new(sep.outputs['Red'], ramp.inputs[0])
    stripe = nodes.new('ShaderNodeMath')
    stripe.operation = 'MULTIPLY_ADD'
    stripe.inputs[1].default_value = -stripes
    stripe.inputs[2].default_value = 1.0
    links.new(sep.outputs['Green'], stripe.inputs[0])
    both = nodes.new('ShaderNodeMath')
    both.operation = 'MULTIPLY'
    links.new(ramp.outputs[0], both.inputs[0])
    links.new(stripe.outputs[0], both.inputs[1])
    tint = nodes.new('ShaderNodeMix')
    tint.data_type = 'RGBA'
    tint.blend_type = 'MULTIPLY'
    tint.inputs['Factor'].default_value = 1.0
    tint.inputs['A'].default_value = (*base, 1)
    comb = nodes.new('ShaderNodeCombineColor')
    for socket in ('Red', 'Green', 'Blue'):
        links.new(both.outputs[0], comb.inputs[socket])
    links.new(comb.outputs['Color'], tint.inputs['B'])
    links.new(tint.outputs['Result'], bsdf.inputs['Base Color'])
    return mat


def build_materials():
    # Linear base colours; the Unreal materials use the same values (Scripts/apply_floating_islands.py).
    preview_material('Rough', (0.045, 0.12, 0.02), variation=0.5)
    preview_material('Fairway', (0.07, 0.2, 0.03), variation=0.25, stripes=0.14)
    preview_material('Green', (0.08, 0.25, 0.035), variation=0.12)
    preview_material('TeeBox', (0.075, 0.21, 0.032), variation=0.1)
    preview_material('Bunker', (0.42, 0.33, 0.2), variation=0.15, roughness=1.0)
    preview_material('IslandRock', (1, 1, 1), use_colour=True, roughness=0.95)


# ---------------------------------------------------------------- build

def build(number):
    hole = hole_layouts()[number - 1]
    layout = design_hole(number, hole)
    d = DESIGNS[number]
    sl.reset_scene()
    build_materials()
    top_fn = lambda x, y: top_height(x, y, layout, number)  # noqa: E731

    # Playable top.
    xy, tris, attrs = triangulate_top(layout)
    z = top_fn(xy[:, 0], xy[:, 1])
    verts = np.column_stack([xy, z])
    names = [REGION_MATERIAL[i] for i in range(5)]
    top = make_mesh(f'SM_H{number:02d}_IslandTop', verts, tris, attrs, names, top_colours(xy[:, 0], xy[:, 1], number))

    # Rock undersides: the connected island (home + bridge + fairway) is one piece.
    land = layout['land']
    uxy, utris = triangulate_underside(land, [0.8, 2.0, 4.0, 7.5, 13, 21, 32], 14)
    pts = shapely.points(uxy[:, 0], uxy[:, 1])
    # Deeper under the big fairway island than under the home island and the bridge.
    in_main = shapely.distance(layout['main'], pts) < 1e-6
    depth = np.where(in_main, d['depth'][0], d['depth'][1])
    rock_v, dist, t = underside(uxy, land, top_fn, depth, number * 13)
    utris = utris[:, ::-1]  # the underside faces down and out, the opposite way to the grass top
    rock = make_mesh(f'SM_H{number:02d}_IslandRock', rock_v, utris, np.zeros(len(utris), int), ['IslandRock'],
                     rock_colours(rock_v[:, 2], dist, t, uxy[:, 0], uxy[:, 1], number))

    # Floaters: grass top plus rock, one mesh with two slots.
    f_verts, f_tris, f_mats, f_cols = [], [], [], []
    offset = 0
    for i, (poly, top_z) in enumerate(layout['floaters']):
        fn = lambda x, y, tz=top_z, s=i: tz + 0.8 * fbm(x / 12, y / 12, 3, 500 + s) - 0.6 * (1 - smooth(  # noqa: E731
            shapely.distance(poly.exterior, shapely.points(x, y)) / 3))
        vx, tx = triangulate_underside(poly, [], 1.5)
        vz = fn(vx[:, 0], vx[:, 1])
        f_verts.append(np.column_stack([vx, vz]))
        f_tris.append(tx + offset)
        f_mats.append(np.zeros(len(tx), int))
        f_cols.append(top_colours(vx[:, 0], vx[:, 1], number))
        offset += len(vx)
        ux, ut = triangulate_underside(poly, [0.8, 2.0, 4.0, 7.0], 6)
        radius = math.sqrt(poly.area / math.pi)
        rv, rd, rt = underside(ux, poly, fn, radius * 1.7, 700 + i)
        f_verts.append(rv)
        f_tris.append(ut[:, ::-1] + offset)  # rock faces down and out
        f_mats.append(np.ones(len(ut), int))
        f_cols.append(rock_colours(rv[:, 2], rd, rt, ux[:, 0], ux[:, 1], 700 + i))
        offset += len(ux)
    floaters = make_mesh(f'SM_H{number:02d}_Floaters', np.concatenate(f_verts), np.concatenate(f_tris),
                         np.concatenate(f_mats), ['Rough', 'IslandRock'], np.concatenate(f_cols))

    OUT.mkdir(parents=True, exist_ok=True)
    for obj in (top, rock, floaters):
        sl.export_fbx(str(OUT / f'{obj.name}.fbx'), [obj])

    # Ground heights the Unreal script needs to seat things on the islands (metres, Unreal frame).
    def ground(x, y):
        return round(float(top_fn(np.array([x], float), np.array([y], float))[0]), 4)
    cx, cy = layout['cup']
    spots = {'cup': [cx, cy, ground(cx, cy)],
             'trees': [[x, y, ground(x, y)] for x, y in layout['trees']],
             'tee_markers': [[1.5, s * 2.5, ground(1.5, s * 2.5)] for s in (-1, 1)],
             'clubhouse': [*d['clubhouse'], ground(*d['clubhouse'])],
             'player_start': [-5.0, 0.0, ground(-5.0, 0.0)]}
    (OUT / f'Hole{number:02d}_spots.json').write_text(json.dumps(spots, indent=2) + '\n')
    print(f'ISLANDS hole {number}: top {len(tris)} tris, rock {len(utris)} tris, {len(layout["floaters"])} floaters; '
          f'land {land.area:.0f} m2; spots {json.dumps(spots)}')
    return layout, (top, rock, floaters)


def render_previews(number, layout):
    """Two Cycles previews: the golfer's view from the tee and a wide view of the hole."""
    scene = bpy.context.scene
    world = bpy.data.worlds.new('Sky')
    world.use_nodes = True
    sky = world.node_tree.nodes.new('ShaderNodeTexSky')
    sky.sun_elevation = math.radians(55)
    sky.sun_rotation = math.radians(200)
    world.node_tree.links.new(sky.outputs['Color'], world.node_tree.nodes['Background'].inputs['Color'])
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.18
    scene.world = world
    sun_data = bpy.data.lights.new('Sun', 'SUN')
    sun_data.energy = 3.2
    sun_data.angle = math.radians(1.5)
    sun = bpy.data.objects.new('Sun', sun_data)
    sun.rotation_euler = (math.radians(38), 0, math.radians(-160))
    scene.collection.objects.link(sun)
    # Sea far below for depth.
    sea = sl.box('Sea', -3000, 3000, -3000, 3000, -251, -250, sl.material('Sea', (0.02, 0.09, 0.16), 0.15))

    # Stand-in trees so the preview reads at scale.
    trunk = sl.material('Trunk', (0.12, 0.07, 0.035), 1.0)
    leaves = sl.material('Leaves', (0.03, 0.11, 0.02), 1.0)
    for x, y in layout['trees']:
        z = float(top_height(np.array([x]), np.array([y]), layout, number)[0])
        sl.cylinder('Trunk', (x, -y, z), (x, -y, z + 7), 0.35, trunk)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=5.5, location=(x, -y, z + 10))
        bpy.context.object.scale = (1, 1, 1.25)
        bpy.context.object.data.materials.append(leaves)
    flag = sl.material('Flag', (0.9, 0.75, 0.0), 0.6)
    cx, cy = layout['cup']
    cz = float(top_height(np.array([cx]), np.array([cy]), layout, number)[0])
    sl.cylinder('Pin', (cx, -cy, cz), (cx, -cy, cz + 2.2), 0.03, sl.material('Pole', (0.9, 0.9, 0.9), 0.4))
    sl.box('Flag', cx, cx + 0.8, -cy - 0.02, -cy + 0.02, cz + 1.6, cz + 2.2, flag)

    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 40
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 1280, 560
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Medium High Contrast'
    views = {
        'tee': ((-8, 0, 3.2), (140, 0, -6), 30),
        'aerial': ((-120, 190, 120), (170, 0, -25), 28),
        'side': ((180, -330, -20), (180, 0, -20), 30),
    }
    for label, (eye, target, lens) in views.items():
        cam_data = bpy.data.cameras.new(label)
        cam_data.lens = lens
        cam_data.clip_end = 8000
        cam = bpy.data.objects.new(label, cam_data)
        cam.location = Vector((eye[0], -eye[1], eye[2]))
        cam.rotation_euler = (Vector((target[0], -target[1], target[2])) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        scene.collection.objects.link(cam)
        scene.camera = cam
        scene.render.filepath = str(OUT / f'Hole{number:02d}_preview_{label}.png')
        bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(sea)


def detail_textures():
    """Tiling greyscale detail textures (512 px) the Unreal materials multiply over their colours."""
    from PIL import Image
    TEXTURES.mkdir(parents=True, exist_ok=True)
    n = 512
    u, v = np.meshgrid(np.arange(n) / n, np.arange(n) / n)

    def tiled(period, octaves, seed):
        # Sample noise on a torus so the texture wraps seamlessly.
        total, amp, norm = 0.0, 1.0, 0.0
        for o in range(octaves):
            p = period * 2 ** o
            a, b = u * 2 * math.pi, v * 2 * math.pi
            r = p / (2 * math.pi)
            total = total + amp * noise2(np.cos(a) * r + np.sin(b) * r * 0.37, np.sin(a) * r + np.cos(b) * r, seed + o)
            norm += amp
            amp *= 0.55
        return total / norm

    specs = {'T_GrassDetail': (8, 5, 1, 0.55), 'T_SandDetail': (24, 3, 2, 0.35), 'T_RockDetail': (6, 6, 3, 0.7)}
    for name, (period, octaves, seed, contrast) in specs.items():
        value = 0.78 + 0.22 * contrast * tiled(period, octaves, seed) / 0.5
        Image.fromarray((np.clip(value, 0, 1) * 255).astype(np.uint8)).save(TEXTURES / f'{name}.png')
    print('TEXTURES', sorted(specs))


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    holes = [int(a) for a in args if a.isdigit()] or [1]
    detail_textures()
    for number in holes:
        layout, _ = build(number)
        if '--no-render' not in args:
            render_previews(number, layout)
