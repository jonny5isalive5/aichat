"""Retarget the Mixamo "Walking" and "Idle" clips onto the golfer's skeleton.

Those two were downloaded on a different Mixamo character (65 bones, about 1.75x the golfer's hip height),
so Unreal can't use them on SK_Golfer as they are. Both rigs are mixamorig skeletons bound in a T-pose, so
each bone's pose can be carried over as a world-space rotation away from its rest pose; the hips' movement
is scaled by the ratio of hip heights. Bones the golfer doesn't have (fingers) are dropped.

    python Art/Blender/retarget_walk_idle.py      (bpy module, Blender 4.2)

Reads Art/Golfer/Animations/{Walking,Idle}.fbx and, for the golfer's rest pose, "Golf Putt.fbx".
Writes Art/Golfer/Animations/Fixed/{Walking,Idle}.fbx; Scripts/import_golfer.py imports them as A_Walk, A_Idle.
"""
from pathlib import Path

import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'Art' / 'Golfer' / 'Animations'
TARGET_RIG = 'Golf Putt'   # any clip downloaded on the golfer carries its skeleton
CLIPS = ['Walking', 'Idle']


def load(name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(SOURCE / f'{name}.fbx'))
    arm = next(o for o in bpy.data.objects if o not in before and o.type == 'ARMATURE')
    for o in set(bpy.data.objects) - before - {arm}:
        bpy.data.objects.remove(o)
    return arm


def short(name):
    return name.split(':')[-1]


def rest_rotation(arm, bone):
    return (arm.matrix_world @ bone.bone.matrix_local).to_quaternion()


def retarget(name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    src = load(name)
    dst = load(TARGET_RIG)
    scene = bpy.context.scene
    first, last = (int(v) for v in src.animation_data.action.frame_range)
    scene.frame_start, scene.frame_end = first, last

    dst.animation_data.action = bpy.data.actions.new(name)
    src_bones = {short(b.name): b for b in src.pose.bones}
    pairs = [(b, src_bones[short(b.name)]) for b in dst.pose.bones if short(b.name) in src_bones]
    # Parents before children, so each bone is set against its parent's final pose.
    order = {b.name: len(b.parent_recursive) for b, _ in pairs}
    pairs.sort(key=lambda pair: order[pair[0].name])

    src_hips, dst_hips = src_bones['Hips'], next(b for b, s in pairs if short(b.name) == 'Hips')
    src_rest_hips = src.matrix_world @ src_hips.bone.head_local
    dst_rest_hips = dst.matrix_world @ dst_hips.bone.head_local
    ratio = dst_rest_hips.z / src_rest_hips.z
    src_rest = {b.name: rest_rotation(src, b) for b in src.pose.bones}
    dst_rest = {b.name: rest_rotation(dst, b) for b in dst.pose.bones}

    for f in range(first, last + 1):
        scene.frame_set(f)
        for b in dst.pose.bones:
            b.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        for d, s in pairs:
            pose = (src.matrix_world @ s.matrix).to_quaternion()
            delta = pose @ src_rest[s.name].inverted()
            world_rot = delta @ dst_rest[d.name]
            if d is dst_hips:
                head = dst_rest_hips + (src.matrix_world @ s.head - src_rest_hips) * ratio
            else:
                head = dst.matrix_world @ d.head
            # Into armature space as rotation + position only: the armature object carries a 0.01 scale, and
            # folding it into the bone matrices would scale every bone 100x (a giant golfer in game).
            arm_rot = dst.matrix_world.to_quaternion().inverted() @ world_rot
            arm_head = dst.matrix_world.inverted() @ head
            d.matrix = Matrix.Translation(arm_head) @ arm_rot.to_matrix().to_4x4()
            bpy.context.view_layer.update()
        for d, _ in pairs:
            d.keyframe_insert('scale', frame=f)
            d.keyframe_insert('rotation_quaternion' if d.rotation_mode == 'QUATERNION' else 'rotation_euler', frame=f)
            if d is dst_hips:
                d.keyframe_insert('location', frame=f)

    bpy.data.objects.remove(src)
    dst.name = 'Armature'  # Unreal drops a root node called Armature instead of adding it as a bone.
    out = SOURCE / 'Fixed' / f'{name}.fbx'
    out.parent.mkdir(exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    dst.select_set(True)
    bpy.context.view_layer.objects.active = dst
    bpy.ops.export_scene.fbx(filepath=str(out), use_selection=True, object_types={'ARMATURE'}, add_leaf_bones=False,
                             bake_anim=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                             bake_anim_force_startend_keying=True, bake_anim_simplify_factor=0.0)
    print(f'RETARGETED {name}: {len(pairs)} bones, {last - first + 1} frames, hips x{ratio:.2f} -> {out.name}')


for clip in CLIPS:
    retarget(clip)
