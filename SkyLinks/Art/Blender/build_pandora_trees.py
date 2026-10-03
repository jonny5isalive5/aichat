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
import numpy as np
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sl_common as sl  # noqa: E402
from build_floater_dressing import GLOW_COLOURS, PETAL, Kit, make_atlas  # noqa: E402

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


def build(path):
    kind, shadow, light, bark, glow, tendrils, bulbs = STYLES[path.stem]
    name = f'SM_PandoraTree_{kind}'
    bpy.ops.wm.read_factory_settings(use_empty=True)
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
