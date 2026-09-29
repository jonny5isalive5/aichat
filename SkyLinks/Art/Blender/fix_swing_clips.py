"""Remove the hip-rotation glitch from the Mixamo swing clips so the golfer's feet stay planted.

The Mixamo retarget of "Golf Chip" and "Golf Putt" onto the Tripo golfer has frames where the whole body
tips around the hips (in the putt both feet lift ~55 cm and the torso pitches down: the "handstand" seen in
game). Legs and spine are children of the hips, so one spurious hips rotation explains all of it.

For every frame this finds the rotation about the hips that puts both feet back where they were on the first
frame (hips->mid-feet and left->right foot directions) and applies it to the hips. Real swing motion is
untouched: in a clean frame the feet are already planted and the correction is the identity.

    python Art/Blender/fix_swing_clips.py      (bpy module, Blender 4.2)

Reads Art/Golfer/Animations/<clip>.fbx, writes Art/Golfer/Animations/Fixed/<clip>.fbx.
Scripts/import_golfer.py prefers the Fixed copy when it exists.
"""
import sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'Art' / 'Golfer' / 'Animations'
CLIPS = ['Golf Chip', 'Golf Putt']


def bone(arm, suffix):
    return next(p for p in arm.pose.bones if p.name.split(':')[-1] == suffix)


def frame_axes(a, b):
    """Orthonormal basis from the hips->feet vector and the left->right foot vector."""
    x = a.normalized()
    y = (b - x * b.dot(x)).normalized()
    return Matrix((x, y, x.cross(y))).transposed()


def feet_error(arm, frames, reference):
    worst = 0.0
    for f in frames:
        bpy.context.scene.frame_set(f)
        for name, ref in reference.items():
            worst = max(worst, ((arm.matrix_world @ bone(arm, name).head) - ref).length)
    return worst


def fix(name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(SOURCE / f'{name}.fbx'))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    arm.name = 'Armature'  # Unreal drops a root node called Armature instead of adding it as a bone.
    scene = bpy.context.scene
    first, last = (int(v) for v in arm.animation_data.action.frame_range)
    scene.frame_start, scene.frame_end = first, last
    frames = range(first, last + 1)
    hips = bone(arm, 'Hips')
    world = arm.matrix_world

    scene.frame_set(first)
    feet = {n: world @ bone(arm, n).head for n in ('LeftFoot', 'RightFoot')}
    hip0 = world @ hips.head
    reference = frame_axes((feet['LeftFoot'] + feet['RightFoot']) / 2 - hip0, feet['RightFoot'] - feet['LeftFoot'])
    before = feet_error(arm, frames, feet)

    for f in frames:
        scene.frame_set(f)
        h = world @ hips.head
        left = world @ bone(arm, 'LeftFoot').head
        right = world @ bone(arm, 'RightFoot').head
        correction = reference @ frame_axes((left + right) / 2 - h, right - left).transposed()
        pivot = Matrix.Translation(h) @ correction.to_4x4() @ Matrix.Translation(-h)
        hips.matrix = world.inverted() @ pivot @ world @ hips.matrix
        path = 'rotation_quaternion' if hips.rotation_mode == 'QUATERNION' else 'rotation_euler'
        hips.keyframe_insert(path, frame=f)
        hips.keyframe_insert('location', frame=f)

    after = feet_error(arm, frames, feet)
    out = SOURCE / 'Fixed' / f'{name}.fbx'
    out.parent.mkdir(exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.fbx(filepath=str(out), use_selection=True, object_types={'ARMATURE'}, add_leaf_bones=False,
                             bake_anim=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                             bake_anim_force_startend_keying=True, bake_anim_simplify_factor=0.0)
    print(f'FIXED {name}: feet drift {before * 100:.1f} cm -> {after * 100:.1f} cm ({len(frames)} frames) -> {out.name}')


for clip in (sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else CLIPS):
    fix(clip)
