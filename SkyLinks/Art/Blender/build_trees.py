"""Stylised, phone-friendly trees and bushes for Sky Links (Pangya / Brushify look: chunky rounded canopies).

Each is one static mesh of about 1-3k triangles with two material slots (TreeBark, TreeLeaves), vertex colours
for all the colour (so no leaf textures), and the wind weight in vertex alpha (0 at the root, 1 at the canopy
top) for the sway shader in Scripts/import_trees.py. A UCX_ box round the trunk is the only collision, so the
ball hits trunks and flies through leaves. Origin on the ground at the trunk. Instanced by the foliage brush,
a hundred of these cost less than one Megaplant.

    python Art/Blender/build_trees.py            (bpy module, Blender 4.2)

Writes Art/Exports/Trees/SM_*.fbx and Trees_preview.png.
"""
import math
import os
import random
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector, noise

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sl_common as sl  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / 'Exports' / 'Trees'
BARK, LEAVES = 0, 1


class Builder:
    """Collects vertices, faces, per-vertex colour (RGBA, A = wind weight) and material per face."""

    def __init__(self, height):
        self.verts, self.faces, self.cols, self.mats = [], [], [], []
        self.height = height

    def add(self, verts, faces, colour_fn, mat):
        base = len(self.verts)
        for v in verts:
            self.verts.append(tuple(v))
            self.cols.append(colour_fn(Vector(v)))
        for f in faces:
            self.faces.append(tuple(base + i for i in f))
            self.mats.append(mat)

    def wind(self, v, canopy):
        h = max(0.0, v.z / self.height)
        return min(1.0, 0.45 + 0.55 * h) if canopy else 0.35 * h * h

    def tube(self, points, radii, colour, segments=8):
        """Tapered tube through points (a trunk or branch), capped at the top."""
        verts, faces = [], []
        for i, (p, r) in enumerate(zip(points, radii)):
            p = Vector(p)
            d = (Vector(points[min(i + 1, len(points) - 1)]) - Vector(points[max(i - 1, 0)])).normalized()
            side = d.orthogonal().normalized()
            up = d.cross(side)
            for s in range(segments):
                a = 2 * math.pi * s / segments
                wobble = 1 + 0.08 * noise.noise(p * 3 + Vector((s, 0, 0)))
                verts.append(p + (side * math.cos(a) + up * math.sin(a)) * r * wobble)
        for i in range(len(points) - 1):
            for s in range(segments):
                a, b = i * segments + s, i * segments + (s + 1) % segments
                faces.append((a, b, b + segments, a + segments))
        top = len(verts)
        verts.append(Vector(points[-1]))
        last = (len(points) - 1) * segments
        for s in range(segments):
            faces.append((last + s, last + (s + 1) % segments, top))

        def paint(v):
            shade = 0.8 + 0.2 * noise.noise(v * 1.7)
            return (*[c * shade for c in colour], self.wind(v, False))
        self.add(verts, faces, paint, BARK)

    def blob(self, centre, radius, colour, rng, squash=0.8, subdiv=3, lumpy=0.22, light_centre=None):
        """A lumpy leaf clump: displaced icosphere, darker underneath, a touch of hue variation."""
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0)
        centre = Vector(centre)
        seed = Vector((rng.uniform(0, 100), rng.uniform(0, 100), rng.uniform(0, 100)))
        verts = []
        for v in bm.verts:
            n = v.co.normalized()
            r = radius * (1 + lumpy * noise.noise(n * 1.8 + seed) + 0.08 * noise.noise(n * 5 + seed))
            verts.append(centre + Vector((n.x * r, n.y * r, n.z * r * squash)))
        faces = [[v.index for v in f.verts] for f in bm.faces]
        bm.free()
        tint = [c * rng.uniform(0.88, 1.12) for c in colour]
        light_from = Vector(light_centre) if light_centre is not None else centre

        def paint(v):
            n = (v - light_from).normalized()
            up = n.z * 0.5 + 0.5                               # 0 underneath, 1 on top
            up = min(1.0, max(0.0, up + 0.12 * noise.noise(v * 0.9 + seed)))
            # Cool, dark blue-green in the shade to warm yellow-green where the sun hits (Pangya-style).
            shade = [c * (0.42 + 0.78 * up) for c in tint]
            shade = (shade[0] * (0.85 + 0.3 * up), shade[1], shade[2] * (1.15 - 0.45 * up))
            return (*[min(1.0, c) for c in shade], self.wind(v, True))
        self.add(verts, faces, paint, LEAVES)

    def clump(self, centre, radius, colour, rng, squash=0.85, lobes=6):
        """A cauliflower canopy: a core blob crowded with smaller lobes over its top and sides, all lit as one."""
        centre = Vector(centre)
        self.blob(centre, radius * 0.82, colour, rng, squash=squash, subdiv=2, lumpy=0.15, light_centre=centre)
        for i in range(lobes):
            a = 2 * math.pi * (i + rng.uniform(-0.3, 0.3)) / lobes
            z = rng.uniform(-0.15, 0.75)
            h = math.sqrt(max(0.0, 1 - z * z))
            n = Vector((math.cos(a) * h, math.sin(a) * h, z))
            c = centre + Vector((n.x * radius * 0.62, n.y * radius * 0.62, n.z * radius * 0.62 * squash))
            self.blob(c, radius * rng.uniform(0.4, 0.52), colour, rng, squash=0.9, subdiv=2, lumpy=0.12,
                      light_centre=centre)
        self.blob(centre + Vector((0, 0, radius * 0.6 * squash)), radius * 0.45, colour, rng, squash=0.85, subdiv=2,
                  lumpy=0.12, light_centre=centre)

    def cone(self, base_z, top_z, radius, colour, rng, segments=12):
        """A jagged conifer tier."""
        verts = []
        for s in range(segments):
            a = 2 * math.pi * s / segments
            spike = s % 2 == 0
            r = radius * (1.0 if spike else 0.72) * rng.uniform(0.92, 1.08)
            droop = rng.uniform(0.25, 0.45) if spike else -0.05   # branch tips hang lower than the gaps
            verts.append(Vector((math.cos(a) * r, math.sin(a) * r, base_z - droop)))
        verts.append(Vector((0, 0, top_z)))
        verts.append(Vector((0, 0, base_z + (top_z - base_z) * 0.15)))
        apex, under = segments, segments + 1
        faces = [(s, (s + 1) % segments, apex) for s in range(segments)]
        faces += [((s + 1) % segments, s, under) for s in range(segments)]
        tint = [c * rng.uniform(0.9, 1.1) for c in colour]

        def paint(v):
            light = 0.55 + 0.45 * min(1.0, (v.z - base_z) / max(0.1, top_z - base_z))
            return (*[c * light for c in tint], self.wind(v, True))
        self.add(verts, faces, paint, LEAVES)

    def mesh(self, name):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([tuple(v) for v in self.verts], [], self.faces)
        mesh.materials.append(vertex_colour_material('TreeBark', 0.9))
        mesh.materials.append(vertex_colour_material('TreeLeaves', 0.75))
        mesh.polygons.foreach_set('material_index', self.mats)
        attribute = mesh.color_attributes.new('Col', 'BYTE_COLOR', 'POINT')
        attribute.data.foreach_set('color_srgb', [c for col in self.cols for c in col])
        mesh.color_attributes.active_color = attribute
        uv = mesh.uv_layers.new(name='UVMap')
        for poly in mesh.polygons:
            for li in poly.loop_indices:
                co = mesh.vertices[mesh.loops[li].vertex_index].co
                uv.data[li].uv = (co.x + co.y, co.z)  # bark detail runs up the trunk
        for poly in mesh.polygons:
            poly.use_smooth = True
        mesh.validate()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        return obj


def vertex_colour_material(name, roughness):
    """Preview material showing the vertex colours (Unreal builds its own, with the wind)."""
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = roughness
    attr = nodes.new('ShaderNodeVertexColor')
    attr.layer_name = 'Col'
    links.new(attr.outputs['Color'], bsdf.inputs['Base Color'])
    return mat


def branch_path(start, direction, length, rise, steps=4):
    return [tuple(Vector(start) + Vector(direction) * length * t + Vector((0, 0, rise * t * (1.2 - 0.4 * t))))
            for t in [i / steps for i in range(steps + 1)]]


BARK_BROWN = (0.30, 0.20, 0.12)
BIRCH_WHITE = (0.82, 0.80, 0.74)
GREENS = {'oak': (0.30, 0.50, 0.14), 'poplar': (0.34, 0.54, 0.16), 'pine': (0.17, 0.36, 0.18),
          'birch': (0.50, 0.66, 0.22), 'bush': (0.26, 0.46, 0.13)}


def broadleaf(name, seed, height=10.0, spread=3.0):
    rng = random.Random(seed)
    b = Builder(height)
    trunk_top = height * 0.42
    b.tube([(0, 0, -0.2), (0, 0, 0.35), (0.05, 0, trunk_top * 0.5), (-0.05, 0.05, trunk_top)], [0.62, 0.4, 0.28, 0.22], BARK_BROWN)
    tips = []
    for i in range(4):
        a = 2 * math.pi * i / 4 + rng.uniform(-0.4, 0.4)
        d = (math.cos(a), math.sin(a), 0)
        start = (0, 0, trunk_top * rng.uniform(0.75, 1.0))
        path = branch_path(start, d, spread * rng.uniform(0.7, 1.0), height * 0.22)
        b.tube(path, [0.16, 0.12, 0.09, 0.07, 0.05], BARK_BROWN, segments=6)
        tips.append(path[-1])
    b.clump((0, 0, height * 0.72), height * 0.3, GREENS['oak'], rng, lobes=7)
    for tip in tips:
        b.clump(Vector(tip) + Vector((0, 0, 0.6)), height * rng.uniform(0.2, 0.25), GREENS['oak'], rng, lobes=4)
    b.clump((rng.uniform(-1, 1), rng.uniform(-1, 1), height * 0.88), height * 0.2, GREENS['oak'], rng, lobes=4)
    return b.mesh(name), 0.4


def poplar(name, seed, height=14.0):
    rng = random.Random(seed)
    b = Builder(height)
    b.tube([(0, 0, 0), (0, 0, height * 0.5), (0, 0, height * 0.85)], [0.3, 0.2, 0.1], BARK_BROWN)
    for i, t in enumerate((0.3, 0.45, 0.6, 0.75, 0.88)):
        r = 2.0 * (1.1 - abs(t - 0.52) * 1.3)
        b.clump((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), height * t), r, GREENS['poplar'], rng, squash=1.25, lobes=4)
    return b.mesh(name), 0.3


def pine(name, seed, height=12.0):
    rng = random.Random(seed)
    b = Builder(height)
    b.tube([(0, 0, 0), (0, 0, height * 0.9)], [0.3, 0.08], BARK_BROWN)
    tiers = 7
    for i in range(tiers):
        base = height * (0.12 + 0.115 * i)
        r = 3.4 * (1 - i / (tiers + 0.4))
        b.cone(base, base + height * 0.24, r, GREENS['pine'], rng, segments=18)
    return b.mesh(name), 0.3


def birch(name, seed, height=11.0):
    rng = random.Random(seed)
    b = Builder(height)
    lean = (rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4))
    b.tube([(0, 0, 0), (lean[0] * 0.5, lean[1] * 0.5, height * 0.4), (lean[0], lean[1], height * 0.8)], [0.2, 0.15, 0.07], BIRCH_WHITE)
    for i in range(7):
        a = rng.uniform(0, 2 * math.pi)
        h = height * rng.uniform(0.5, 0.92)
        r = rng.uniform(1.0, 2.0) * (1.2 - h / height * 0.5)
        b.clump((lean[0] + math.cos(a) * r, lean[1] + math.sin(a) * r, h), rng.uniform(1.2, 1.8), GREENS['birch'], rng, squash=0.9, lobes=3)
    return b.mesh(name), 0.25


def bush(name, seed, flowers=False):
    rng = random.Random(seed)
    b = Builder(2.0)
    b.tube([(0, 0, 0), (0, 0, 0.5)], [0.08, 0.05], BARK_BROWN, segments=5)
    blobs = []
    for i in range(rng.randint(4, 6)):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(0.2, 0.9)
        c = (math.cos(a) * d, math.sin(a) * d, rng.uniform(0.55, 0.95))
        r = rng.uniform(0.55, 0.85)
        b.blob(c, r, GREENS['bush'], rng, squash=0.75, subdiv=2)
        blobs.append((Vector(c), r))
    if flowers:
        for i in range(40):
            c, r = rng.choice(blobs)
            n = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0.1, 1))).normalized()
            colour = rng.choice([(0.95, 0.55, 0.75), (0.98, 0.95, 0.9), (0.95, 0.8, 0.25)])
            b.blob(c + Vector((n.x * r, n.y * r, n.z * r * 0.75)), 0.1, colour, rng, squash=1.0, subdiv=1, lumpy=0.0)
    return b.mesh(name), None


SPECIES = [
    ('SM_Tree_Oak_A', lambda n: broadleaf(n, 1)),
    ('SM_Tree_Oak_B', lambda n: broadleaf(n, 7, height=8.5, spread=3.6)),
    ('SM_Tree_Poplar', lambda n: poplar(n, 3)),
    ('SM_Tree_Pine', lambda n: pine(n, 4)),
    ('SM_Tree_Birch', lambda n: birch(n, 5)),
    ('SM_Bush_Round', lambda n: bush(n, 6)),
    ('SM_Bush_Flowering', lambda n: bush(n, 8, flowers=True)),
]


def preview(objects):
    spacing = [0, 11, 21, 30, 39, 47, 52]
    for obj, x in zip(objects, spacing):
        obj.location.x = x - 26.0
    sl.preview_render(str(OUT / 'Trees_preview.png'), target=(0.0, 0.0, 5.0), distance=64, height=9,
                      yaw_degrees=-90, ground_size=80, resolution=(1800, 620), lens=36)


def main():
    sl.reset_scene()
    OUT.mkdir(parents=True, exist_ok=True)
    built = []
    for name, make in SPECIES:
        obj, trunk_radius = make(name)
        exported = [obj]
        if trunk_radius:
            r = trunk_radius
            collision = sl.box(f'UCX_{name}_00', -r, r, -r, r, 0.0, 4.0)
            collision.hide_render = True
            exported.append(collision)
        sl.export_fbx(str(OUT / f'{name}.fbx'), exported)
        for extra in exported[1:]:
            bpy.data.objects.remove(extra)
        tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
        size = [round(v, 1) for v in obj.dimensions]
        print(f'TREE {name}: {tris} triangles, {size} m')
        built.append(obj)
    if '--no-render' not in sys.argv:
        preview(built)


main()
