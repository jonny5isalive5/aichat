"""Build the floating-island course: holes 1-6, the jungle rope bridges between them, vines, fog and tree plans.

    python Art/Blender/build_course_islands.py            all holes 1-6 plus bridges, then a course preview
    python Art/Blender/build_course_islands.py -- 3 4     just those holes (bridges need their neighbours)
    ... --no-render                                        skip the Cycles previews

Per hole n (world coordinates, Unreal metres; Scripts/apply_floating_islands.py places them at the origin):
  SM_Hnn_IslandTop / IslandRock             as hole 1 (build_floating_islands.py), placed, turned and raised
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

PATH_EDGE = 0.2  # m: half the soft band along a footpath's border


def footpaths(number, land):
    """Footpaths drawn in the editor (Scripts/apply_floating_islands.py export_paths -> Paths.json) that cross this
    hole's island, as one local-coordinate polygon kept 1.5 m inside the rim (the rim must match the rock)."""
    source = OUT / 'Paths.json'
    if not source.is_file():
        return None
    shapes = []
    for path in json.loads(source.read_text()).get('paths', []):
        pts = np.array(path['points'], float)
        lx, ly = C.to_local(number, pts[:, 0], pts[:, 1])
        if len(pts) >= 2:
            shapes.append(LineString(np.column_stack([lx, ly])).buffer(path.get('width', 3.0) / 2, 16))
    if not shapes:
        return None
    area = unary_union(shapes).intersection(land.buffer(-1.5))
    area = shapely.set_precision(area, 0.05)
    return None if area.is_empty or area.area < 1.0 else area


def design_new(number):
    """Island shape and play regions of holes 2-6 (local metres)."""
    h = C.HOLES[number]
    fairways = unary_union(h['fairways'])
    (cx, cy), gr = h['green']
    green = Point(cx, cy).buffer(gr, 96)
    bunkers = [b if hasattr(b, 'geom_type') else Point(b[0], b[1]).buffer(b[2], 64) for b in h['bunkers']]
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
        self.v, self.f, self.c, self.m, self.uv = [], [], [], [], []

    def _add(self, verts, faces, colour, mat, alpha, uvs=None):
        base = len(self.v)
        self.v.extend(verts)
        self.uv.extend(uvs if uvs is not None else [None] * len(verts))
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

    def ribbon(self, points, width, facing, colour, alpha, mat=2, tile=2.0):
        """A leafy vine card: a strip `width` wide through `points`, facing `facing` (horizontal), UV v along it."""
        side = Vector((-facing[1], facing[0], 0)).normalized()
        verts, uvs, faces = [], [], []
        run = 0.0
        for i, p in enumerate(points):
            p = Vector(p)
            if i:
                run += (p - Vector(points[i - 1])).length
            w = width * (1.0 - 0.35 * i / max(1, len(points) - 1))
            verts += [tuple(p - side * w / 2), tuple(p + side * w / 2)]
            uvs += [(0.0, run / tile), (1.0, run / tile)]
        for i in range(len(points) - 1):
            a = i * 2
            faces.append((a, a + 1, a + 3, a + 2))
        self._add(verts, faces, colour, mat, alpha, uvs)

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
                vi = mesh.loops[li].vertex_index
                given = self.uv[vi]
                co = mesh.vertices[vi].co
                uv.data[li].uv = given if given is not None else (co.x + co.y, co.z)
        mesh.validate()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        return obj


def vc_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    attr = nodes.new('ShaderNodeVertexColor')
    attr.layer_name = 'Col'
    texture_path = B.TEXTURES / 'T_Vines.png'
    if name == 'Vines' and texture_path.is_file():
        # Preview only (Unreal builds M_Tree_Vines): ivy texture x vertex colour, cut out by its alpha.
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = bpy.data.images.load(str(texture_path), check_existing=True)
        mix = nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        links.new(tex.outputs['Color'], mix.inputs[6])
        links.new(attr.outputs['Color'], mix.inputs[7])
        links.new(mix.outputs[2], bsdf.inputs['Base Color'])
        links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
        mat.blend_method = 'CLIP'
        return mat
    links.new(attr.outputs['Color'], bsdf.inputs['Base Color'])
    return mat


# ---------------------------------------------------------------- vines

VINE_GREENS = [(0.22, 0.42, 0.12), (0.30, 0.50, 0.15), (0.18, 0.34, 0.12), (0.36, 0.52, 0.18)]
ROOT_BROWN = (0.30, 0.20, 0.12)


def hang(parts, rim_xy, outward, top_z, length, rng, leafy):
    """One strand hanging from the rim, drifting away from the cliff as it falls: a leafy ivy card (crossed
    with a second card when long), or a bare root."""
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
    if not leafy:
        parts.tube(pts, lambda t: 0.06 * (1 - 0.6 * t), ROOT_BROWN, 0, wind, sides=4)
        return
    tint = rng.uniform(0.75, 1.1)
    colour = (tint, tint * rng.uniform(0.95, 1.05), tint * rng.uniform(0.85, 1.0))
    width = rng.uniform(1.3, 2.2)
    tile = width * 3.4  # T_Vines is 1:4, so leaves keep (nearly) their shape
    parts.ribbon(pts, width, outward, colour, wind, tile=tile)
    if length > 6:
        a = math.radians(rng.choice((55, -55)))
        crossed = (outward[0] * math.cos(a) - outward[1] * math.sin(a), outward[0] * math.sin(a) + outward[1] * math.cos(a))
        parts.ribbon(pts, width * 0.8, crossed, colour, wind, tile=tile * 0.8)


def vine_texture():
    """T_Vines.png: a hanging ivy strip (stem and leaves, transparent around them), tiling top to bottom."""
    from PIL import Image, ImageDraw
    w, h = 256, 1024
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    rng = random.Random(11)

    def stem_x(y, k=0):
        # Two stems twining round each other (k = 0, 1), each a whole number of waves so the strip tiles.
        return w / 2 + (30 - 8 * k) * math.sin(2 * math.pi * y / h * (2 + k) + k * 2.1) + 8 * math.sin(2 * math.pi * y / h * 5)
    for k in (0, 1):
        for y in range(0, h, 2):
            x = stem_x(y, k)
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(70, 80, 40, 255))
    greens = [(52, 110, 38), (70, 130, 45), (40, 92, 34), (88, 145, 55), (60, 118, 42)]
    for _ in range(190):
        y = rng.uniform(0, h)
        side = rng.choice((-1, 1))
        length = rng.uniform(40, 78)
        angle = math.radians(rng.uniform(25, 70)) * side
        base = (stem_x(y, rng.randint(0, 1)), y)
        tip = (base[0] + math.sin(angle) * length, base[1] + math.cos(angle) * length * 0.6)
        colour = rng.choice(greens)
        for dy in (-h, 0, h):  # wrap so the strip tiles
            pts = []
            for k in range(14):
                t = k / 13
                bulge = math.sin(math.pi * t) * length * 0.32 * (1.15 if t < 0.5 else 0.9)
                cx = base[0] + (tip[0] - base[0]) * t
                cy = base[1] + (tip[1] - base[1]) * t + dy
                nx, ny = -(tip[1] - base[1]), tip[0] - base[0]
                n = math.hypot(nx, ny) or 1
                pts.append((cx + nx / n * bulge, cy + ny / n * bulge))
            for k in range(13, -1, -1):
                t = k / 13
                bulge = math.sin(math.pi * t) * length * 0.32
                cx = base[0] + (tip[0] - base[0]) * t
                cy = base[1] + (tip[1] - base[1]) * t + dy
                nx, ny = -(tip[1] - base[1]), tip[0] - base[0]
                n = math.hypot(nx, ny) or 1
                pts.append((cx - nx / n * bulge, cy - ny / n * bulge))
            draw.polygon(pts, fill=(*colour, 255))
            draw.line([(base[0], base[1] + dy), (tip[0], tip[1] + dy)], fill=tuple(int(c * 0.7) for c in colour) + (255,), width=2)
    B.TEXTURES.mkdir(parents=True, exist_ok=True)
    img.save(B.TEXTURES / 'T_Vines.png')


def add_vines(parts, poly, height_local, number, rng, skip=(), density=1.0):
    """Ivy and roots along the island rim (local polygon), written into `parts` in world coordinates."""
    ring = poly.exterior
    pts = np.array([ring.interpolate(s).coords[0] for s in np.arange(0, ring.length, 0.75)])
    ccw = ring.is_ccw
    for i, p in enumerate(pts):
        if rng.random() > density:
            continue
        if any(math.hypot(p[0] - sx, p[1] - sy) < sr for sx, sy, sr in skip):
            continue
        q = pts[(i + 1) % len(pts)] - pts[i - 1]
        outward = np.array([q[1], -q[0]]) / (np.linalg.norm(q) + 1e-9)
        if not ccw:
            outward = -outward
        z = float(height_local(np.array([p[0]]), np.array([p[1]]))[0])
        leafy = rng.random() < 0.85
        length = (rng.uniform(4, 11) if rng.random() < 0.45 else rng.uniform(11, 30)) if leafy else rng.uniform(3, 9)
        # Write straight into world space: turn the outward direction with the hole.
        wx, wy = C.to_world(number, p[0], p[1])
        yaw = math.radians(C.PLACE[number][1])
        ox = outward[0] * math.cos(yaw) - outward[1] * math.sin(yaw)
        oy = outward[0] * math.sin(yaw) + outward[1] * math.cos(yaw)
        hang(parts, (float(wx), float(wy)), (ox, oy), z + C.PLACE[number][2], length, rng, leafy)


def add_cliff_vines(parts, rock_v, rock_tris, dist, poly, number, rng, per_metre=0.7):
    """Ivy and roots scattered over the whole underside (not only the rim): strands start on the rock itself,
    anywhere from just under the lip to deep down the hanging cliffs, and hang free below it (the underside is
    a height field, so a strand dropping from its surface never runs back into rock)."""
    corners = rock_v[rock_tris]                               # (n, 3, 3) local metres
    centre = corners.mean(1)
    area = 0.5 * np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
    d = dist[rock_tris].mean(1)
    weight = area * np.clip((d - 0.6) / 1.5, 0, 1) * np.exp(-d / 14.0)   # thickest near the lip, thinning inward
    if weight.sum() <= 0:
        return
    count = int(poly.exterior.length * per_metre)
    picks = np.random.default_rng(rng.randint(0, 2 ** 31)).choice(len(centre), size=count, p=weight / weight.sum())
    yaw = math.radians(C.PLACE[number][1])
    for i in picks:
        a, b, c = corners[i]
        u, v = rng.random(), rng.random()
        if u + v > 1:
            u, v = 1 - u, 1 - v
        p = a + (b - a) * u + (c - a) * v
        edge = poly.exterior.interpolate(poly.exterior.project(Point(p[0], p[1])))
        out = np.array([edge.x - p[0], edge.y - p[1]])
        out = out / (np.linalg.norm(out) + 1e-9)
        ox = out[0] * math.cos(yaw) - out[1] * math.sin(yaw)
        oy = out[0] * math.sin(yaw) + out[1] * math.cos(yaw)
        wx, wy = C.to_world(number, p[0], p[1])
        leafy = rng.random() < 0.85
        length = (rng.uniform(3, 9) if rng.random() < 0.55 else rng.uniform(9, 22)) if leafy else rng.uniform(3, 8)
        hang(parts, (float(wx), float(wy)), (ox, oy), float(p[2]) + C.PLACE[number][2] + 0.3, length, rng, leafy)


# ---------------------------------------------------------------- bridges

WOOD = [(0.42, 0.30, 0.18), (0.36, 0.25, 0.15), (0.48, 0.34, 0.20)]
ROPE = (0.62, 0.52, 0.34)


def rope_bridge(deck_parts, parts, a, b, rng, width=2.4, sag_ratio=0.055, leafy=True, ground=None, guard=None):
    """Planks on a sagging deck between two anchor points (world x, y, z) into `deck_parts` (looks only: the
    buggy drives on a smooth slab in `guard`); rope rails, hangers, log posts and a gate tall enough for the buggy into `parts` (no
    collision). ground(x, y) -> island height or None: over land the deck never dips under the grass, so the
    buggy meets no lip at the cliff edge. `guard` gets low walls along both edges (hidden, they only collide)
    so the buggy can't drive off the side."""
    a, b = Vector(a), Vector(b)
    span = (b - a).length
    sag = 0.8 + span * sag_ratio
    along = (b - a).normalized()
    flat = Vector((along.x, along.y, 0)).normalized()
    across = Vector((-flat.y, flat.x, 0))

    # Deck height along the span: the sagging rope curve, lifted flush with the grass over land, then eased so it
    # never falls away faster than a gentle ramp (no lip where it leaves the cliff edge).
    ts = np.linspace(0.0, 1.0, 401)
    zs = np.array([(a.lerp(b, t)).z - sag * 4 * t * (1 - t) for t in ts])
    if ground:
        for i, t in enumerate(ts):
            p = a.lerp(b, t)
            g = ground(p.x, p.y)
            if g is not None:
                zs[i] = max(zs[i], g - 0.02)
    dz = 0.3 * span / 400
    for i in range(1, len(zs)):
        zs[i] = max(zs[i], zs[i - 1] - dz)
    for i in range(len(zs) - 2, -1, -1):
        zs[i] = max(zs[i], zs[i + 1] - dz)

    def deck(t):
        p = a.lerp(b, t)
        p.z = float(np.interp(t, ts, zs))
        return p

    count = int(span / 0.42)
    for i in range(count + 1):
        t = i / count
        p = deck(t)
        tangent = (deck(min(1, t + 0.01)) - deck(max(0, t - 0.01))).normalized()
        jitter = Vector((0, 0, rng.uniform(-0.02, 0.02)))
        deck_parts.box(p + jitter, tangent, across, (0.17, width / 2 * rng.uniform(0.9, 1.0), 0.04), rng.choice(WOOD))
    steps = max(8, int(span / 1.2))
    for side in (-1, 1):
        edge = [tuple(deck(i / steps) + across * side * width / 2) for i in range(steps + 1)]
        rail = [tuple(deck(i / steps) + across * side * width / 2 + Vector((0, 0, 1.1 - 0.25 * math.sin(math.pi * i / steps))))
                for i in range(steps + 1)]
        parts.tube(edge, 0.045, ROPE, sides=4)
        parts.tube(rail, 0.05, ROPE, sides=4)
        for i in range(0, steps + 1, 2):
            parts.tube([edge[i], rail[i]], 0.02, ROPE, sides=3)
            if leafy and rng.random() < 0.45:
                # A short strand of ivy trailing off the rope rail, outside the deck.
                top = Vector(rail[i]) + across * side * 0.05
                drop = rng.uniform(1.0, 3.2)
                strand = [tuple(top + across * side * 0.25 * (k / 4) ** 2 - Vector((0, 0, drop * k / 4))) for k in range(5)]
                w = rng.uniform(0.45, 0.7)
                parts.ribbon(strand, w, tuple(across * side), (0.9, 0.95, 0.85), 0.5, tile=w * 3.4)
        for end, sign in ((a, 1), (b, -1)):
            post = end + across * side * (width / 2 + 0.2) - flat * sign * 0.6
            parts.tube([tuple(post - Vector((0, 0, 0.8))), tuple(post + Vector((0, 0, 2.95)))], 0.16, rng.choice(WOOD), sides=6)
            parts.tube([tuple(post + Vector((0, 0, 1.4))), tuple(end + across * side * width / 2 + Vector((0, 0, 1.1)))], 0.035, ROPE, sides=4)
    for end, sign in ((a, 1), (b, -1)):   # crossbar over each end, jungle-gate style
        centre = end - flat * sign * 0.6 + Vector((0, 0, 2.8))  # the buggy's roof clears it
        parts.tube([tuple(centre - across * (width / 2 + 0.4)), tuple(centre + across * (width / 2 + 0.4))], 0.1, rng.choice(WOOD), sides=6)
    if guard is not None:
        # The smooth surface the buggy actually drives on (the planks are looks only): a thin slab just at
        # plank-top height, running 1.5 m past each anchor and dipping into the grass so there's no lip.
        path = [a - flat * 1.5 - Vector((0, 0, 0.2))] + [deck(i / (4 * steps)) + Vector((0, 0, 0.04))
                                                          for i in range(4 * steps + 1)] + [b + flat * 1.5 - Vector((0, 0, 0.2))]
        half = across * (width / 2)
        top_v = [q for p in path for q in (tuple(p - half), tuple(p + half))]
        bottom_v = [tuple(Vector(q) - Vector((0, 0, 0.08))) for q in top_v]
        quads = [(2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1) for i in range(len(path) - 1)]
        guard._add(top_v, quads, ROPE, 0, 0.0)
        guard._add(bottom_v, [q[::-1] for q in quads], ROPE, 0, 0.0)
        for side in (-1, 1):
            for i in range(steps):
                p0, p1 = deck(i / steps), deck((i + 1) / steps)
                d = p1 - p0
                mid = (p0 + p1) / 2 + across * side * (width / 2 + 0.08) + Vector((0, 0, 0.6))
                guard.box(mid, d, across, (d.length / 2 + 0.05, 0.06, 0.6), ROPE)
    return span, sag


FOOTBRIDGE_WIDTH = 3.0  # m: the Fab bridge (2 m wide) is stretched to this so the buggy fits


def footbridge(parts, number, height_local, centre, heading, length, rng):
    """A footbridge over a brook (local placement). The looks come from the Fab bridge mesh placed by
    Scripts/apply_floating_islands.py; this writes only the flat deck it drives on (hidden in game, it
    collides) and returns where the bridge goes: world x, y, deck z (m), yaw (deg), length (m)."""
    ang = math.radians(heading)
    d = np.array([math.cos(ang), math.sin(ang)])
    ends = [np.array(centre) - d * length / 2, np.array(centre) + d * length / 2]
    zs = [float(height_local(np.array([e[0]]), np.array([e[1]]))[0]) for e in ends]
    base = C.PLACE[number][2]
    deck_z = max(zs) + base + 0.08
    wa = C.to_world(number, *ends[0])
    wb = C.to_world(number, *ends[1])
    a = Vector((float(wa[0]), float(wa[1]), deck_z))
    b = Vector((float(wb[0]), float(wb[1]), deck_z))
    flat = (b - a).normalized()
    across = Vector((-flat.y, flat.x, 0))
    # Flat across the brook, easing down into each bank over 1.5 m so there's no lip to drive over.
    deck = [a - flat * 1.5 - Vector((0, 0, deck_z - zs[0] - base + 0.25))] + [a.lerp(b, i / 20) for i in range(21)] \
        + [b + flat * 1.5 - Vector((0, 0, deck_z - zs[1] - base + 0.25))]
    half = across * (FOOTBRIDGE_WIDTH / 2)
    top_v = [q for p in deck for q in (tuple(p - half), tuple(p + half))]
    bottom_v = [tuple(Vector(q) - Vector((0, 0, 0.1))) for q in top_v]
    quads = [(2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1) for i in range(len(deck) - 1)]
    parts._add(top_v, quads, WOOD[1], 0, 0.0)
    parts._add(bottom_v, [q[::-1] for q in quads], WOOD[1], 0, 0.0)
    mid = (a + b) / 2
    yaw = math.degrees(math.atan2(flat.y, flat.x))
    return [round(mid.x, 3), round(mid.y, 3), round(deck_z, 3), round(yaw, 2), round(length, 2)]


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

    paths = footpaths(number, layout['land'])
    if paths is not None:
        # Path borders become mesh edges: a thin band between an inner and an outer outline carries the fade.
        layout = dict(layout, extra_lines=[paths.buffer(-PATH_EDGE), paths.buffer(PATH_EDGE).intersection(layout['land'].buffer(-1.0))])
    xy, tris, attrs = B.triangulate_top(layout)
    z = local_h(xy[:, 0], xy[:, 1])
    top_cols = B.top_colours(xy[:, 0], xy[:, 1], number)
    if paths is not None:
        inner = paths.buffer(-PATH_EDGE + 0.01)
        top_cols[:, 2] = shapely.contains_xy(inner, xy[:, 0], xy[:, 1]).astype(float)  # B: 1 on the path
    top = B.make_mesh(f'{name}_IslandTop', place(number, np.column_stack([xy, z])), tris, attrs,
                      [B.REGION_MATERIAL[i] for i in range(5)], top_cols)

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

    # Floaters: hole 1 keeps its hand-placed ones; the others get a ring of small islands. They hang high above
    # the hole (background decoration, clear of play) and each is its own mesh with its pivot at its middle,
    # so they can be moved one by one in the editor.
    floaters = layout['floaters'] if number == 1 else ring_of_floaters(number, land, rng)
    for stale in OUT.glob(f'{name}_Floater*.fbx'):
        stale.unlink()
    floater_spots = []
    vines = Parts()
    skip = [(0, 0, 18)]  # keep the tee edge clear
    for i, (poly, _) in enumerate(floaters):
        top_z = rng.uniform(50, 120)
        fn = lambda x, y, tz=top_z, s=i, pl=poly: tz + 0.8 * B.fbm(x / 12, y / 12, 3, 500 + s) - 0.6 * (1 - B.smooth(  # noqa: E731
            shapely.distance(pl.exterior, shapely.points(x, y)) / 3))
        cx, cy = poly.centroid.x, poly.centroid.y
        wcx, wcy = (float(v) for v in C.to_world(number, cx, cy))
        pivot = np.array([wcx, wcy, top_z + C.PLACE[number][2]])
        vx, tx = B.triangulate_underside(poly, [], 1.5)
        ux, ut = B.triangulate_underside(poly, [0.8, 2.0, 4.0, 7.0], 6)
        radius = math.sqrt(poly.area / math.pi)
        rv, rd, rt = B.underside(ux, poly, fn, radius * 1.7, 700 + i + number * 50)
        verts = np.concatenate([place(number, np.column_stack([vx, fn(vx[:, 0], vx[:, 1])])), place(number, rv)]) - pivot
        f_tris = np.concatenate([tx, ut[:, ::-1] + len(vx)])
        f_mats = np.concatenate([np.zeros(len(tx), int), np.ones(len(ut), int)])
        cols = np.concatenate([B.top_colours(vx[:, 0], vx[:, 1], number),
                               moss(B.rock_colours(rv[:, 2], rd, rt, ux[:, 0], ux[:, 1], 700 + i), rv[:, 2], rd, ux[:, 0], ux[:, 1], i)])
        floater_name = f'{name}_Floater{i + 1:02d}'
        rock_obj = B.make_mesh(floater_name, verts, f_tris, f_mats, ['Rough', 'IslandRock'], cols)
        ivy = Parts()
        add_vines(ivy, poly, fn, number, rng, density=0.8)
        add_cliff_vines(ivy, rv, ut, rd, poly, number, rng, per_metre=0.5)
        ivy.v = [tuple(np.asarray(v, float) - pivot) for v in ivy.v]
        ivy_obj = ivy.mesh(f'{floater_name}_Ivy', ('TreeBark', 'TreeLeaves', 'Vines')) if ivy.f else None
        sl.export_fbx(str(OUT / f'{floater_name}.fbx'), [rock_obj, ivy_obj] if ivy.f else [rock_obj])
        floater_spots.append([floater_name, *[round(float(v), 2) for v in pivot]])

    add_vines(vines, land, local_h, number, rng, skip=skip)
    add_cliff_vines(vines, rock_v, utris, dist, land, number, rng)
    vine_obj = vines.mesh(f'{name}_Vines', ('TreeBark', 'TreeLeaves', 'Vines'))
    exported = [top, rock, vine_obj]

    if layout.get('water') is not None:
        wxy, wtris = B.triangulate_underside(layout['water'], [], 6)
        wv = place(number, np.column_stack([wxy, np.full(len(wxy), WATER_LEVEL)]))
        exported.append(B.make_mesh(f'{name}_Water', wv, wtris, np.zeros(len(wtris), int), ['Water'],
                                    np.tile([0.5, 0.0, 0.0], (len(wv), 1))))
    footbridge_spots = []
    if layout.get('footbridges'):
        props = Parts()
        for centre, heading, length in layout['footbridges']:
            footbridge_spots.append(footbridge(props, number, local_h, centre, heading, length, rng))
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
             'forest': forest_plan(number, layout, local_h, rng), 'floaters': floater_spots, 'footbridges': footbridge_spots}
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
    for n in range(1, max(C.PLACE)):
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
        def ground(x, y, n=n, ha=ha, hb=hb, wa=wa, wb=wb):
            for num, land, h in ((n, wa, ha), (n + 1, wb, hb)):
                if land.contains(Point(x, y)):
                    lx, ly = C.to_local(num, x, y)
                    return float(h(np.array([lx]), np.array([ly]))[0]) + C.PLACE[num][2]
            return None
        deck, rails, guard = Parts(), Parts(), Parts()
        span, sag = rope_bridge(deck, rails, (ax, ay, za - 0.02), (bx, by, zb - 0.02), rng, ground=ground, guard=guard)
        base = f'SM_Bridge_{n:02d}_{n + 1:02d}'
        obj, rails_obj, guard_obj = deck.mesh(base), rails.mesh(f'{base}_Rails', ('TreeBark', 'TreeLeaves', 'Vines')), guard.mesh(f'{base}_Guard')
        for o in (obj, rails_obj, guard_obj):
            sl.export_fbx(str(OUT / f'{o.name}.fbx'), [o])
        bridges.append(dict(name=obj.name, rails=rails_obj.name, guard=guard_obj.name, a=[ax, ay, za], b=[bx, by, zb],
                            span=round(span, 1), sag=round(sag, 1)))
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
    ivy = vc_material('Vines')
    for obj in bpy.data.objects:
        for slot in obj.material_slots:
            if slot.material and slot.material.name.startswith('Vines') and slot.material != ivy:
                slot.material = ivy
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
    for label, eye, target, lens in (('course', (-1500, 900, 1300), (0, 900, -20), 24),
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
    wanted = [int(a) for a in args if a.isdigit()] or sorted(C.PLACE)
    OUT.mkdir(parents=True, exist_ok=True)
    vine_texture()
    layouts = {}
    for number in sorted(set(wanted) | {n for w in wanted for n in (w - 1, w + 1) if n in C.PLACE}):
        layouts[number] = (layout_for(number), None)
    for number in layouts:
        layouts[number] = (layouts[number][0], height_fn(number, layouts[number][0]))
    if '--check' in args:
        check_course(layouts)
        return
    # --links-only: skip the islands (already built) and redo the bridges, fog and previews for the whole course.
    if '--links-only' in args:
        layouts = {n: (layout_for(n), None) for n in C.PLACE}
        layouts = {n: (lay, height_fn(n, lay)) for n, (lay, _) in layouts.items()}
        wanted = sorted(C.PLACE)
    # --props-only: rebuild just the footbridges (SM_Hnn_Props) of the wanted holes.
    if '--props-only' in args:
        for number in wanted:
            sl.reset_scene()
            layout = layout_for(number)
            if layout.get('footbridges'):
                local_h = height_fn(number, layout)
                props = Parts()
                rng = random.Random(number * 1009)
                placed = [footbridge(props, number, local_h, centre, heading, length, rng)
                          for centre, heading, length in layout['footbridges']]
                obj = props.mesh(f'SM_H{number:02d}_Props')
                sl.export_fbx(str(OUT / f'{obj.name}.fbx'), [obj])
                spots_path = OUT / f'Hole{number:02d}_spots.json'
                spots = json.loads(spots_path.read_text())
                spots['footbridges'] = placed
                spots_path.write_text(json.dumps(spots, indent=1) + '\n')
                print(f'PROPS {number}: {len(layout["footbridges"])} footbridges')
        return
    for number in (wanted if '--links-only' not in args else []):
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
