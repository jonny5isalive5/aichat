"""Rig an unrigged Meshy character (T-pose, facing -Y) by borrowing a rigged one's skeleton and skin weights.

    python Art/Blender/rig_from_donor.py -- <unrigged.fbx> <donor Character_output.fbx> <out Character_output.fbx>

The donor's skeleton and body are warped onto the new body, landmark by landmark (feet, crotch, arm line, top of
the head; the torso's width and the arm span; the body's depth), the joints of the arms and legs are re-centred
inside the new limbs, and the skin weights are copied across from the warped donor body. The result is the same
Meshy rig (same bone names) as Meshy's own rigging gives, so build_eccentric_golfer.py takes it like the others.
"""
import sys

import bpy
import numpy as np
from mathutils import Vector

HEIGHT = 1.7  # Meshy's rigged exports stand 1.7 m tall on the floor


def import_fbx(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(path))
    return [o for o in bpy.data.objects if o not in before]


def apply_transform(objs):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def verts(mesh):
    co = np.empty(len(mesh.data.vertices) * 3)
    mesh.data.vertices.foreach_get('co', co)
    return co.reshape(-1, 3)


def landmarks(v):
    low, high = v[:, 2].min(), v[:, 2].max()
    span = np.abs(v[:, 0]).max()
    crotch = None
    for z in np.linspace(low, low + 0.6 * (high - low), 400):
        ring = v[np.abs(v[:, 2] - z) < 0.005]
        if len(ring) and (np.abs(ring[:, 0]) < 0.01).any():
            crotch = z
            break
    arms = v[(np.abs(v[:, 0]) > 0.5 * span) & (np.abs(v[:, 0]) < 0.7 * span)]
    arm_z = float(np.median(arms[:, 2]))
    middle = v[np.abs(v[:, 2] - (crotch + arm_z) / 2) < 0.01]
    torso = float(np.abs(middle[:, 0]).max())
    return dict(low=low, crotch=crotch, arm=arm_z, high=high, torso=torso, span=span,
                depth=v[:, 1].max() - v[:, 1].min())


def slice_centre_y(v, z, half_width):
    ring = v[(np.abs(v[:, 2] - z) < 0.02) & (np.abs(v[:, 0]) < half_width)]
    return float(ring[:, 1].mean()) if len(ring) else 0.0


def make_warp(src_v, dst_v):
    a, b = landmarks(src_v), landmarks(dst_v)
    print('DONOR', {k: round(float(x), 3) for k, x in a.items()})
    print('TARGET', {k: round(float(x), 3) for k, x in b.items()})
    zk_a = [a['low'], a['crotch'], a['arm'], a['high']]
    zk_b = [b['low'], b['crotch'], b['arm'], b['high']]
    xk_a = [0.0, a['torso'], a['span']]
    xk_b = [0.0, b['torso'], b['span']]
    depth = b['depth'] / a['depth']

    def warp(p):
        z = float(np.interp(p[2], zk_a, zk_b, left=p[2] - zk_a[0] + zk_b[0], right=p[2] - zk_a[-1] + zk_b[-1]))
        x = float(np.sign(p[0]) * np.interp(abs(p[0]), xk_a, xk_b, right=abs(p[0]) - xk_a[-1] + xk_b[-1]))
        y = (p[1] - slice_centre_y(src_v, p[2], a['torso'])) * depth + slice_centre_y(dst_v, z, b['torso'])
        return Vector((x, y, z))
    return warp, b


def recentre(arm, dst_v, marks):
    """Arm joints to the middle of the arm's cross-section, leg joints to the middle of the leg's."""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    bones = arm.data.edit_bones
    connected = {b.name: b.parent.name for b in bones if b.parent and (b.parent.tail - b.head).length < 1e-4}
    for b in bones:
        side = 1.0 if b.name.startswith('Left') else -1.0 if b.name.startswith('Right') else 0.0
        h = b.head
        if any(k in b.name for k in ('Arm', 'ForeArm', 'Hand')) and 'End' not in b.name:
            ring = dst_v[(np.abs(dst_v[:, 0] - h.x) < 0.015) & (np.abs(dst_v[:, 2] - h.z) < 0.15)]
            if len(ring) > 20:
                h.y = float(ring[:, 1].mean())
                if 'ForeArm' in b.name or 'Hand' in b.name:  # the shoulder's slice runs into the chest
                    h.z = float((ring[:, 2].min() + ring[:, 2].max()) / 2)
        elif any(k in b.name for k in ('UpLeg', 'Leg')) and 'Foot' not in b.name and side:
            ring = dst_v[(np.abs(dst_v[:, 2] - h.z) < 0.015) & (dst_v[:, 0] * side > 0.01)]
            if len(ring) > 20 and h.z < marks['crotch']:
                h.x, h.y = float((ring[:, 0].min() + ring[:, 0].max()) / 2), float(ring[:, 1].mean())
        b.head = h
    for child, parent in connected.items():
        bones[parent].tail = bones[child].head
    bpy.ops.object.mode_set(mode='OBJECT')


def main():
    args = sys.argv[sys.argv.index('--') + 1:]
    target_path, donor_path, out_path = args[:3]
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # The new body, standing on the floor at Meshy's rigged height.
    new = import_fbx(target_path)
    body = max((o for o in new if o.type == 'MESH'), key=lambda o: len(o.data.vertices))
    apply_transform([body])
    v = verts(body)
    scale = HEIGHT / (v[:, 2].max() - v[:, 2].min())
    body.scale = (scale, scale, scale)
    apply_transform([body])
    v = verts(body)
    body.location = (-(v[:, 0].max() + v[:, 0].min()) / 2, -(v[:, 1].max() + v[:, 1].min()) / 2, -v[:, 2].min())
    apply_transform([body])
    dst_v = verts(body)

    # The donor, warped onto it.
    donor = import_fbx(donor_path)
    arm = next(o for o in donor if o.type == 'ARMATURE')
    skin = max((o for o in donor if o.type == 'MESH'), key=lambda o: len(o.data.vertices))
    for o in donor:
        if o not in (arm, skin):
            bpy.data.objects.remove(o)
    arm.animation_data_clear()
    skin.parent = None
    skin.modifiers.clear()
    apply_transform([skin])
    apply_transform([arm])
    src_v = verts(skin)
    warp, marks = make_warp(src_v, dst_v)

    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for b in arm.data.edit_bones:
        roll = b.roll
        b.head, b.tail = warp(b.head), warp(b.tail)
        b.roll = roll
    bpy.ops.object.mode_set(mode='OBJECT')
    recentre(arm, dst_v, marks)

    moved = np.array([warp(p) for p in src_v])
    skin.data.vertices.foreach_set('co', moved.ravel())
    skin.data.update()

    # Skin weights from the nearest point of the warped donor body.
    for group in skin.vertex_groups:
        body.vertex_groups.new(name=group.name)
    transfer = body.modifiers.new('Weights', 'DATA_TRANSFER')
    transfer.object = skin
    transfer.use_vert_data = True
    transfer.data_types_verts = {'VGROUP_WEIGHTS'}
    transfer.vert_mapping = 'POLYINTERP_NEAREST'
    transfer.layers_vgroup_select_src = 'ALL'
    transfer.layers_vgroup_select_dst = 'NAME'
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.modifier_apply(modifier='Weights')
    bpy.data.objects.remove(skin)
    bpy.ops.object.vertex_group_normalize_all(lock_active=False)

    body.parent = arm
    mod = body.modifiers.new('Armature', 'ARMATURE')
    mod.object = arm
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    body.select_set(True)
    bpy.ops.export_scene.fbx(filepath=out_path, use_selection=True, object_types={'ARMATURE', 'MESH'},
                             add_leaf_bones=False, bake_anim=False, path_mode='COPY', embed_textures=True)
    print(f'RIGGED {out_path}: {len(arm.data.bones)} bones, {len(body.vertex_groups)} weight groups')


main()
