"""Pandora versions of the course's trees and bushes: the very same shapes (each original SM_Tree_* / SM_Bush_*
mesh, its collision too), restyled: blue-green, teal, lavender and lime canopies shaded the way the originals
are, dark violet bark with a glowing vein up the trunk, glowing bulbs dotted over the canopy, glowing tendrils
hanging from under it, glowing flowers on the bushes.

    python Art/Blender/build_pandora_trees.py

Writes Art/Exports/Trees/Pandora/SM_PandoraTree_<kind>.fbx: slots TreeBark and TreeLeaves (the old trees'
materials, so they look and sway the same) plus FloaterGlow (unlit, glowing). In Unreal,
apply_floating_islands.pandora_trees() swaps every tree in the level to its Pandora version without moving any
of them, and normal_trees() swaps them back.
"""
import math
import random
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Vector, noise

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sl_common as sl  # noqa: E402
from build_floater_dressing import GLOW_COLOURS, PETAL, PLAIN, Kit, make_atlas  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'Art' / 'Exports' / 'Trees'
OUT = SOURCE / 'Pandora'
CYAN, SKY, BLUE, VIOLET, MINT = GLOW_COLOURS

# Original file stem: (kind, canopy shadow -> light colour, bark colour, glow colour, tendrils, bulbs per 10 m2)
STYLES = {
    'SM_Tree_Oak_A': ('Oak_A', (0.04, 0.17, 0.22), (0.28, 0.8, 0.66), (0.24, 0.19, 0.27), CYAN, 22, 1.2),
    'SM_Tree_Oak_B': ('Oak_B', (0.06, 0.2, 0.1), (0.5, 0.88, 0.36), (0.24, 0.19, 0.27), VIOLET, 20, 1.2),
    'SM_Tree_Birch': ('Birch', (0.16, 0.1, 0.27), (0.7, 0.52, 0.9), (0.78, 0.74, 0.84), SKY, 16, 1.4),
    'SM_Tree_Poplar': ('Poplar', (0.04, 0.15, 0.2), (0.22, 0.72, 0.78), (0.24, 0.19, 0.27), MINT, 14, 1.4),
    'SM_Tree_Pine': ('Pine', (0.03, 0.11, 0.17), (0.16, 0.5, 0.58), (0.22, 0.17, 0.24), BLUE, 0, 2.0),
    'SM_Bush_Round': ('Bush_Round', (0.05, 0.2, 0.1), (0.36, 0.82, 0.42), (0.22, 0.17, 0.24), SKY, 0, 3.0),
    'SM_Bush_Flowering': ('Bush_Flowering', (0.08, 0.16, 0.2), (0.3, 0.72, 0.6), (0.22, 0.17, 0.24), VIOLET, 0, 2.0),
}
FLOWER = (0.95, 0.35, 0.85)  # the flowering bush's (lit) flowers turn orchid pink


def colours(mesh):
    attr = mesh.color_attributes[0]
    data = np.zeros(len(attr.data) * 4, np.float32)
    attr.data.foreach_get('color_srgb', data)
    return attr, data.reshape(-1, 4)


def element_material(mesh, attr):
    """Material index of every colour element (point or face corner)."""
    face_mat = np.zeros(len(mesh.polygons), np.int32)
    mesh.polygons.foreach_get('material_index', face_mat)
    loop_face = np.zeros(len(mesh.loops), np.int32)
    for poly in mesh.polygons:
        loop_face[poly.loop_start:poly.loop_start + poly.loop_total] = poly.index
    if attr.domain == 'CORNER':
        return face_mat[loop_face]
    per_point = np.zeros(len(mesh.vertices), np.int32)
    loops_v = np.zeros(len(mesh.loops), np.int32)
    mesh.loops.foreach_get('vertex_index', loops_v)
    per_point[loops_v] = face_mat[loop_face]
    return per_point


def restyle(mesh, shadow, light, bark, flowering):
    """New colours on the old shading: each element keeps how light or dark it was, the wind weight (alpha) too."""
    slots = [m.name.split('.')[0] if m else '' for m in mesh.materials]
    attr, c = colours(mesh)
    mats = element_material(mesh, attr)
    lum = c[:, 0] * 0.3 + c[:, 1] * 0.59 + c[:, 2] * 0.11
    leaves = np.array([slots[m] == 'TreeLeaves' for m in mats])
    flowers = leaves & (c[:, :3].max(axis=1) > 0.8) if flowering else np.zeros(len(c), bool)
    foliage = leaves & ~flowers
    lo, hi = np.percentile(lum[foliage], [4, 96]) if foliage.any() else (0, 1)
    t = np.clip((lum - lo) / max(hi - lo, 1e-3), 0, 1)[:, None]
    new = c.copy()
    new[foliage, :3] = (np.array(shadow) * (1 - t) + np.array(light) * t)[foliage]
    new[flowers, :3] = np.array(FLOWER) * (0.75 + 0.25 * t[flowers])
    bark_mask = ~leaves
    if bark_mask.any():
        blo, bhi = np.percentile(lum[bark_mask], [4, 96])
        bt = np.clip((lum - blo) / max(bhi - blo, 1e-3), 0, 1)[:, None]
        new[bark_mask, :3] = (np.array(bark) * (0.7 + 0.5 * bt))[bark_mask]
    attr.data.foreach_set('color_srgb', np.clip(new, 0, 1).ravel())


def faces_of(mesh, slot):
    index = next((i for i, m in enumerate(mesh.materials) if m and m.name.split('.')[0] == slot), -1)
    return [p for p in mesh.polygons if p.material_index == index]


def trunk_line(mesh, height):
    """The trunk's middle and radius every 30 cm up to 4 m (from the bark's vertices)."""
    bark = {i for p in faces_of(mesh, 'TreeBark') for i in p.vertices}
    pts = np.array([mesh.vertices[i].co[:] for i in bark]) if bark else np.zeros((0, 3))
    line = []
    for z in np.arange(0.2, min(4.0, height * 0.45), 0.3):
        ring = pts[np.abs(pts[:, 2] - z) < 0.15] if len(pts) else pts
        ring = ring[np.hypot(ring[:, 0], ring[:, 1]) < 1.2] if len(ring) else ring
        if len(ring) < 4:
            break
        centre = ring[:, :2].mean(axis=0)
        radius = float(np.hypot(*(ring[:, :2] - centre).T).max())
        line.append((Vector((centre[0], centre[1], z)), radius))
    return line


def add_glow(kit, mesh, rng, glow, tendrils, bulbs_per_10m2, flowering):
    # A glowing vein spiralling up the trunk.
    line = trunk_line(mesh, mesh.vertices and max(v.co.z for v in mesh.vertices) or 1)
    prev = None
    for i, (p, r) in enumerate(line):
        a = i * 0.9
        q = p + Vector((math.cos(a), math.sin(a), 0)) * (r * 1.03)
        if prev is not None:
            side = (q - prev).cross(Vector((math.cos(a), math.sin(a), 0))).normalized() * 0.03
            kit.quad([prev - side, prev + side, q + side, q - side], [(0.6, 0.6)] * 4, glow, 1)
        prev = q

    leaf_faces = faces_of(mesh, 'TreeLeaves')
    if not leaf_faces:
        return
    areas = np.array([p.area for p in leaf_faces])
    cumulative = np.cumsum(areas / areas.sum())

    def pick():
        return leaf_faces[min(len(leaf_faces) - 1, int(np.searchsorted(cumulative, rng.random())))]

    # Glowing bulbs dotted over the canopy's surface.
    for _ in range(min(45, int(areas.sum() / 10 * bulbs_per_10m2))):  # capped: phones draw hundreds of these
        face = pick()
        n = face.normal
        kit.blob(Vector(face.center) + n * 0.05, rng.uniform(0.09, 0.17), rng.choice((glow, glow, MINT)), 1, sides=4)
    # Glowing tendrils hanging from under the canopy.
    under = [p for p in leaf_faces if p.normal.z < -0.35]
    for _ in range(tendrils if under else 0):
        face = rng.choice(under)
        p = Vector(face.center)
        length = rng.uniform(0.8, 2.6)
        steps = max(3, int(length / 0.4))
        sway = rng.uniform(0, 6.28)
        for i in range(steps):
            q = p + Vector((math.sin(sway + i) * 0.04, math.cos(sway + i * 0.7) * 0.04, -length / steps))
            side = Vector((math.cos(sway), math.sin(sway), 0)) * 0.025
            kit.quad([p - side, p + side, q + side, q - side], [(0.6, 0.6)] * 4, glow, 1)
            p = q
        kit.blob(p, rng.uniform(0.06, 0.1), tuple(min(1, c * 0.6 + 0.4) for c in glow), 1, sides=4)
    # The flowering bush: glowing star flowers over its top.
    if flowering:
        tops = [p for p in leaf_faces if p.normal.z > 0.3] or leaf_faces
        for _ in range(10):
            face = rng.choice(tops)
            n = face.normal.normalized()
            t1 = n.cross(Vector((0, 0, 1)))
            t1 = t1.normalized() if t1.length > 1e-3 else Vector((1, 0, 0))
            t2 = n.cross(t1)
            centre = Vector(face.center) + n * 0.05
            radius = rng.uniform(0.15, 0.26)
            for k in range(7):
                a = 2 * math.pi * k / 7
                along = t1 * math.cos(a) + t2 * math.sin(a)
                kit.card(centre, (along + n * 0.3).normalized(), n.cross(along), radius, radius * 0.42, PETAL,
                         rng.choice((glow, FLOWER)), 1)
            kit.blob(centre + n * 0.03, radius * 0.25, (0.9, 0.95, 1.0), 1, sides=4)


def tube(kit, points, radii, colour, sides=7):
    """A trunk through points, radius per point (vertex coloured, a little lighter on one side)."""
    u, v = PLAIN[0] + 0.25, PLAIN[1] + 0.25
    rings = []
    for i, (p, r) in enumerate(zip(points, radii)):
        ahead = (points[min(i + 1, len(points) - 1)] - points[max(i - 1, 0)]).normalized()
        side = ahead.cross(Vector((0.31, 0.77, 0.55))).normalized()
        other = ahead.cross(side)
        ring = []
        for k in range(sides):
            a = 2 * math.pi * k / sides
            ring.append(len(kit.v))
            q = p + (side * math.cos(a) + other * math.sin(a)) * r
            kit.v.append(tuple(q))
            kit.uv.append((u + 0.0 * q.x, v))
            kit.col.append(tuple(c * (0.8 + 0.2 * math.cos(a)) for c in colour))
        rings.append(ring)
    for a_ring, b_ring in zip(rings, rings[1:]):
        for k in range(sides):
            j = (k + 1) % sides
            kit.f += [(a_ring[k], a_ring[j], b_ring[k]), (a_ring[j], b_ring[j], b_ring[k])]
            kit.mat += [0, 0]


def lumpy_pad(kit, centre, radius, thickness, top, under, rng, mat=0):
    """A flat, lumpy leaf pad (a squashed icosphere), lit like the other canopies: light on top, dark beneath.
    UVs are world-projected so the leaves material's detail texture lies across it."""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0)
    seed = Vector((rng.uniform(0, 50), rng.uniform(0, 50), rng.uniform(0, 50)))
    base = len(kit.v)
    for v in bm.verts:
        n = v.co.normalized()
        bump = 1 + 0.16 * noise.noise(n * 2.2 + seed) + 0.06 * noise.noise(n * 6 + seed)
        p = centre + Vector((n.x * radius * bump, n.y * radius * bump, n.z * thickness * bump))
        kit.v.append(tuple(p))
        kit.uv.append((p.x * 0.4, p.y * 0.4 + p.z * 0.4))
        t = min(1.0, max(0.0, n.z * 0.5 + 0.5 + 0.1 * noise.noise(p * 0.8 + seed)))
        kit.col.append(tuple(u * (1 - t) + o * t for u, o in zip(under, top)))
    for f in bm.faces:
        kit.f.append(tuple(base + v.index for v in f.verts))
        kit.mat.append(mat)
    bm.free()


def spire_tree(name, rng):
    """The pine's Pandora version, redesigned (a dark cone with lights read as a Christmas tree): a tall twisting
    violet trunk carrying stacked teal leaf pads, smaller towards the top, each with a glowing rim of bulbs and
    glowing tendrils hanging beneath. Same height and spread as the pine, so it stands where the pines were."""
    kit = Kit()
    height, glow = 12.6, BLUE
    trunk = [Vector((math.sin(t * 2.4) * 0.35, math.cos(t * 1.7) * 0.25 - 0.25, t * height * 0.93))
             for t in (i / 10 for i in range(11))]
    radii = [0.36 * (1 - 0.68 * i / 10) for i in range(11)]
    start = len(kit.f)
    tube(kit, trunk, radii, (0.24, 0.18, 0.28))
    for i in range(start, len(kit.f)):
        kit.mat[i] = 2  # bark
    vein_line = [(p, r) for p, r in zip(trunk[:6], radii[:6])]
    prev = None
    for i, (p, r) in enumerate(vein_line):
        a = i * 1.1
        q = p + Vector((math.cos(a), math.sin(a), 0)) * (r * 1.04)
        if prev is not None:
            side = (q - prev).cross(Vector((math.cos(a), math.sin(a), 0))).normalized() * 0.035
            kit.quad([prev - side, prev + side, q + side, q - side], [(0.6, 0.6)] * 4, glow, 1)
        prev = q
    cloud = []
    tiers = [(0.36, 3.3), (0.52, 2.8), (0.67, 2.2), (0.8, 1.6), (0.92, 1.0)]
    for i, (frac, radius) in enumerate(tiers):
        z = height * frac
        along = trunk[min(10, int(round(frac * 10 / 0.93)))]
        centre = Vector((along.x, along.y, z)) + Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 0))
        thickness = radius * 0.3
        top = (0.2 + 0.05 * i, 0.62 + 0.03 * i, 0.68)
        lumpy_pad(kit, centre, radius, thickness, top, (0.03, 0.09, 0.15), rng)
        for k in range(16):
            a = 2 * math.pi * k / 16
            rim = centre + Vector((math.cos(a) * radius * 0.94, math.sin(a) * radius * 0.94, -thickness * 0.35))
            cloud.append(rim + Vector((0, 0, thickness * 1.4)))
            cloud.append(rim)
            kit.blob(rim, rng.uniform(0.08, 0.13), rng.choice((glow, glow, CYAN)), 1, sides=4)
        for _ in range(5 if i < 4 else 2):  # tendrils from beneath the pad
            a, r = rng.uniform(0, 6.28), radius * rng.uniform(0.4, 0.85)
            p = centre + Vector((math.cos(a) * r, math.sin(a) * r, -thickness * 0.6))
            length = rng.uniform(0.6, 1.6)
            steps = 4
            for j in range(steps):
                q = p + Vector((0.03 * math.sin(a + j), 0.03 * math.cos(a + j), -length / steps))
                side = Vector((math.cos(a), math.sin(a), 0)) * 0.025
                kit.quad([p - side, p + side, q + side, q - side], [(0.6, 0.6)] * 4, glow, 1)
                p = q
            kit.blob(p, 0.08, (0.6, 0.85, 1.0), 1, sides=4)
    obj = kit.mesh(name, domain='CORNER')
    obj.data.materials[0] = bpy.data.materials.get('TreeLeaves') or bpy.data.materials.new('TreeLeaves')
    obj.data.materials.append(bpy.data.materials.get('TreeBark') or bpy.data.materials.new('TreeBark'))
    trunk_box = sl.box(f'UCX_{name}_00', -0.3, 0.3, -0.55, 0.05, 0.0, 4.0)
    return obj, [trunk_box, hull(cloud, f'UCX_{name}_01')], len(kit.f)


def hull(points, name, shrink=0.9):
    centre = sum(points, Vector()) / len(points)
    bm = bmesh.new()
    for p in points:
        bm.verts.new(centre + (p - centre) * shrink)
    result = bmesh.ops.convex_hull(bm, input=bm.verts)
    loose = {g for g in result['geom_interior'] + result['geom_unused'] if isinstance(g, bmesh.types.BMVert)}
    bmesh.ops.delete(bm, geom=list(loose), context='VERTS')
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def build(path):
    kind, shadow, light, bark, glow, tendrils, bulbs = STYLES[path.stem]
    name = f'SM_PandoraTree_{kind}'
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if kind == 'Pine':
        tree, collision, faces = spire_tree(name, random.Random(kind))
        sl.export_fbx(str(OUT / f'{name}.fbx'), [tree] + collision)
        print(f'TREE {name}: {faces} faces (redesigned spire tree), {len(collision)} collision hulls')
        return
    bpy.ops.import_scene.fbx(filepath=str(path))
    tree = bpy.data.objects[path.stem]
    collision = [o for o in bpy.data.objects if o.name.startswith('UCX_')]
    restyle(tree.data, shadow, light, bark, kind == 'Bush_Flowering')

    kit = Kit()
    add_glow(kit, tree.data, random.Random(kind), glow, tendrils, bulbs, kind == 'Bush_Flowering')
    glow_obj = kit.mesh(name + '_Glow', domain=tree.data.color_attributes[0].domain)
    glow_obj.matrix_world = tree.matrix_world
    glow_obj.data.transform(tree.matrix_world.inverted())
    # One mesh: the glow joined onto the tree (its FloaterLeaf slot goes unused).
    bpy.ops.object.select_all(action='DESELECT')
    glow_obj.select_set(True)
    tree.select_set(True)
    bpy.context.view_layer.objects.active = tree
    bpy.ops.object.join()
    tree.name = tree.data.name = name
    for i, hull in enumerate(sorted(collision, key=lambda o: o.name)):
        hull.name = f'UCX_{name}_{hull.name.rsplit("_", 1)[-1]}'
    sl.export_fbx(str(OUT / f'{name}.fbx'), [tree] + collision)
    print(f'TREE {name}: {len(tree.data.polygons)} faces ({len(kit.f)} glowing), {len(collision)} collision hulls')


def main():
    make_atlas()
    OUT.mkdir(parents=True, exist_ok=True)
    for stem in STYLES:
        build(SOURCE / f'{stem}.fbx')


if __name__ == '__main__':
    main()
