"""The Meshy golfers as players: body for Unreal plus every golf clip retargeted onto them.

    python Art/Blender/build_eccentric_golfer.py -- man      (bpy module, Blender 4.2; "woman", or both by default)

The man ("Eccentric Golfer", Art/Golfer/Meshy_Eccentric_Golfer -> Art/Golfer/Eccentric) and his wife ("Retro
Fairway Diva", Art/Golfer/Meshy_Eccentric_Woman -> Art/Golfer/Diva) are the same Meshy rig, so they're built the
same way. Both get the old golfer's golf clips and their own Meshy walk, jog and run (in place, speeds measured).

Reads Art/Golfer/Meshy_Eccentric_Golfer/ (Meshy export: Character_output.fbx is the body bound in its rest pose;
the Walking "withSkin" FBX has the same skeleton with mixamorig bone names, used only to rename the bones, as its
mesh is stored arms-down against an arms-out skeleton; the loose texture_0*.png are the colour / normal /
roughness / metallic maps) and the
existing clips in Art/Golfer/Animations (Fixed/ copies preferred), which were made on the old Tripo golfer.

Writes Art/Golfer/Eccentric/:
  Golfer.fbx              body (about 1.7 m, decimated for mobile), skeleton in the Mixamo layout (object scale
                          0.01, bones in cm) so Unreal reads it exactly like the old golfer
  Animations/<clip>.fbx   every clip, retargeted onto his skeleton
Scripts/import_golfer.py imports these when the folder exists.

Retargeting: the Meshy rig rests with its arms 20 degrees down and legs apart, the Mixamo rig in a strict T-pose.
Each target bone is first swung so it points the way the source bone points at rest, then given the source
bone's world-space rotation away from its rest. Hip travel is scaled so it covers the same distance in game as
before (the old golfer was scaled 1.9x, this one GAME_SCALE), and hip height by the ratio of hip heights, except
when seated in the buggy clips, where the hips keep the seat's real height.
"""
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

import sys

ROOT = Path(__file__).resolve().parents[2]
GOLFER = ROOT / 'Art' / 'Golfer'
RUN_FBX = GOLFER / 'Meshy_Eccentric_Woman' / 'Goofy Running.fbx'

OLD_SCALE = 1.9    # AGolfCharacter scaled the old golfer (whose clips these mostly are) by this
TRIANGLES = 32000  # mobile budget for the body

# Per character: Meshy folder and file prefix, output folder (Art/Golfer/<out>, /Game/Characters/<out>), height in
# game (cm; keep AGolfCharacter's body table in step) and whether the Meshy walk replaces the old golfer's.
CHARACTERS = {
    'man': dict(folder='Meshy_Eccentric_Golfer', prefix='Meshy_AI_Eccentric_Golfer_biped', out='Eccentric',
                material='M_EccentricGolfer', height=180.0, own_walk=True,
                jog='Jog Forward.fbx', run='Running (1).fbx'),
    'woman': dict(folder='Meshy_Eccentric_Woman', prefix='Meshy_AI_Retro_Fairway_Diva_biped', out='Diva',
                  material='M_FairwayDiva', height=172.0, own_walk=True,
                  jog='Jogging.fbx', run='Running.fbx'),
}

CLIPS = ['Golf Drive', 'Golf Drive alt1', 'Golf Drive Setup', 'Golf Tee Up', 'Golf Chip',
         'Golf Chip (replay if long shit in)', 'Golf Putt', 'Golf Putt Victory', 'Golf Putt Victory on long putt',
         'Golf Putt Failure missed putt', 'Golf Bad Shot', 'Hokey Pokey hole in one', 'Silly Dancing celebrate',
         'Silly Dancing celebrate alt1', 'Entering Car', 'Exiting Car', 'Walking', 'Idle', 'Jogging', 'Running']

# Set by build_body for the character being built.
MESHY = BODY_FBX = NAMES_FBX = OUT = None
TEXTURE = MATERIAL = ''
GAME_SCALE = 1.0
MESHY_NAMES = {}  # Meshy bone name -> Mixamo name, for clips made on the Meshy rig


def use_character(key):
    global MESHY, BODY_FBX, NAMES_FBX, OUT, TEXTURE, MATERIAL
    c = CHARACTERS[key]
    MESHY = GOLFER / c['folder']
    BODY_FBX = MESHY / f"{c['prefix']}_Character_output.fbx"
    NAMES_FBX = MESHY / f"{c['prefix']}_Animation_Walking_withSkin.fbx"
    TEXTURE = f"{c['prefix']}_texture_0"
    MATERIAL = c['material']
    OUT = GOLFER / c['out']
    return c


def clip_source(name, character):
    """(fbx, native): the old golfer's clip, or one made on the Meshy rig (native: in place, hips scaled by size)."""
    if name == 'Jogging':
        return MESHY / character['jog'], True
    if name == 'Running':
        return MESHY / character['run'], True
    if name == 'Walking' and character['own_walk']:
        return NAMES_FBX, True
    fixed = GOLFER / 'Animations' / 'Fixed' / f'{name}.fbx'
    return (fixed if fixed.is_file() else GOLFER / 'Animations' / f'{name}.fbx'), False


def short(name):
    return name.split(':')[-1]


def import_fbx(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(path))
    return [o for o in bpy.data.objects if o not in before]


def build_body():
    """Import the Meshy body, drop its extras, re-scale to the Mixamo layout, decimate and texture it."""
    new = import_fbx(BODY_FBX)
    arm = next(o for o in new if o.type == 'ARMATURE')
    body = max((o for o in new if o.type == 'MESH'), key=lambda o: len(o.data.vertices))
    for o in new:
        if o not in (arm, body):
            bpy.data.objects.remove(o)

    # Mixamo bone names (the game and the clips go by them): the Walking export has the same skeleton with
    # those names, so each bone takes the name of the bone resting at the same place there.
    named = import_fbx(NAMES_FBX)
    ref = next(o for o in named if o.type == 'ARMATURE')
    ref_heads = [(b.name, ref.matrix_world @ b.head_local) for b in ref.data.bones]
    renames = {}
    for b in arm.data.bones:
        head = arm.matrix_world @ b.head_local
        name, where = min(ref_heads, key=lambda item: (item[1] - head).length)
        if (where - head).length < 0.005:
            renames[b.name] = name
    for o in named:
        bpy.data.objects.remove(o)
    assert len(set(renames.values())) == len(renames), f'bone names clash: {renames}'
    MESHY_NAMES.clear()
    MESHY_NAMES.update(renames)
    for old, new_name in renames.items():
        group = body.vertex_groups.get(old)
        if group:
            group.name = new_name
        arm.data.bones[old].name = new_name
    print('RENAMED', renames)
    assert {'mixamorig:Hips', 'mixamorig:RightHand', 'mixamorig:LeftHand'} <= set(renames.values())
    arm.animation_data_clear()
    for b in arm.pose.bones:
        b.matrix_basis = Matrix.Identity(4)
    body.modifiers.clear()
    mod = body.modifiers.new('Armature', 'ARMATURE')
    mod.object = arm

    # Mixamo layout: bones and vertices in centimetres under an armature scaled 0.01.
    bpy.ops.object.select_all(action='DESELECT')
    for o in (arm, body):
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    arm.scale = (100.0, 100.0, 100.0)
    bpy.context.view_layer.update()
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    arm.scale = (0.01, 0.01, 0.01)
    bpy.context.view_layer.update()

    # Decimate for mobile (vertex weights and UVs are carried through the collapse).
    tris = sum(len(p.vertices) - 2 for p in body.data.polygons)
    if tris > TRIANGLES:
        dec = body.modifiers.new('Decimate', 'DECIMATE')
        dec.ratio = TRIANGLES / tris
        bpy.context.view_layer.objects.active = body
        bpy.ops.object.modifier_move_to_index(modifier='Decimate', index=0)
        bpy.ops.object.modifier_apply(modifier='Decimate')

    # One PBR material from the loose Meshy maps.
    mat = bpy.data.materials.new(MATERIAL)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']

    def tex(suffix, socket, colour):
        node = nodes.new('ShaderNodeTexImage')
        node.image = bpy.data.images.load(str(MESHY / f'{TEXTURE}{suffix}.png'))
        if not colour:
            node.image.colorspace_settings.name = 'Non-Color'
        return node

    links.new(tex('', 'Base Color', True).outputs['Color'], bsdf.inputs['Base Color'])
    links.new(tex('_roughness', 'Roughness', False).outputs['Color'], bsdf.inputs['Roughness'])
    links.new(tex('_metallic', 'Metallic', False).outputs['Color'], bsdf.inputs['Metallic'])
    normal = nodes.new('ShaderNodeNormalMap')
    links.new(tex('_normal', 'Normal', False).outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    body.data.materials.clear()
    body.data.materials.append(mat)

    body.name = 'SK_Golfer'
    arm.name = 'Armature'  # Unreal drops a root node called Armature instead of adding it as a bone.
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    body.select_set(True)
    bpy.ops.export_scene.fbx(filepath=str(OUT / 'Golfer.fbx'), use_selection=True, object_types={'ARMATURE', 'MESH'},
                             add_leaf_bones=False, bake_anim=False, path_mode='COPY', embed_textures=True,
                             mesh_smooth_type='FACE')
    height = max((arm.matrix_world @ b.head_local).z for b in arm.data.bones)
    print(f'BODY Golfer.fbx: {sum(len(p.vertices) - 2 for p in body.data.polygons)} triangles, '
          f'{len(arm.data.bones)} bones, head top {height:.2f} m')

    # Scale in game: the height asked for over the model's own height (AGolfCharacter scales the same way).
    global GAME_SCALE
    corners = [body.matrix_world @ Vector(v) for v in body.bound_box]
    GAME_SCALE = CHARACTER['height'] / 100.0 / (max(c.z for c in corners) - min(c.z for c in corners))
    print(f'SCALE in game x{GAME_SCALE:.3f}')

    # Retarget onto a mesh-free copy of the rig (fast), exported under the name Armature.
    rig = arm.copy()
    rig.data = arm.data
    rig.animation_data_clear()
    bpy.context.scene.collection.objects.link(rig)
    arm.name = 'BodyArmature'
    rig.name = 'Armature'
    bpy.data.objects.remove(body)
    bpy.data.objects.remove(arm)
    return rig


def rest_rotation(arm, bone):
    return (arm.matrix_world @ bone.bone.matrix_local).to_quaternion()


def rest_direction(arm, bone):
    return (arm.matrix_world.to_3x3() @ (bone.bone.tail_local - bone.bone.head_local)).normalized()


def retarget(dst, name):
    path, native = clip_source(name, CHARACTER)
    if not path.is_file():
        print(f'MISSING {name}')
        return
    known = set(bpy.data.actions)
    new = import_fbx(path)
    src = next(o for o in new if o.type == 'ARMATURE')
    # Meshy "with skin" exports carry a one-frame bind action as well as the motion: use the longest one.
    actions = [a for a in bpy.data.actions if a not in known]
    motion = max((a for a in actions if any(fc.data_path.startswith('pose.bones') for fc in a.fcurves)),
                 key=lambda a: a.frame_range[1] - a.frame_range[0])
    if src.animation_data is None:
        src.animation_data_create()
    src.animation_data.action = motion
    scene = bpy.context.scene
    first, last = (int(v) for v in src.animation_data.action.frame_range)
    scene.frame_start, scene.frame_end = first, last

    if dst.animation_data is None:
        dst.animation_data_create()
    dst.animation_data.action = bpy.data.actions.new(name)
    # Clips made on the Meshy rig carry Meshy bone names: match them through the rename made for the body.
    src_bones = {short(MESHY_NAMES.get(b.name, b.name)): b for b in src.pose.bones}
    pairs = [(b, src_bones[short(b.name)]) for b in dst.pose.bones if short(b.name) in src_bones]
    order = {b.name: len(b.parent_recursive) for b, _ in pairs}
    pairs.sort(key=lambda pair: order[pair[0].name])

    src_hips, dst_hips = src_bones['Hips'], next(b for b, s in pairs if short(b.name) == 'Hips')
    src_rest_hips = src.matrix_world @ src_hips.bone.head_local
    dst_rest_hips = dst.matrix_world @ dst_hips.bone.head_local
    lift = dst_rest_hips.z / src_rest_hips.z
    travel = lift if native else OLD_SCALE / GAME_SCALE
    # Meshy clips walk or run forward: take that out (the character moves them), noting the speed it matched.
    drift = Vector((0.0, 0.0, 0.0))
    if native:
        scene.frame_set(first)
        start = src.matrix_world @ src_hips.head
        scene.frame_set(last)
        drift = (src.matrix_world @ src_hips.head) - start
        drift.z = 0.0
        seconds = (last - first) / scene.render.fps
        speed = drift.length * lift * GAME_SCALE * 100 / max(seconds, 1e-3)
        print(f'SPEED {name}: the clip moves {speed:.0f} cm/s in game at play rate 1 (now in place)')
    src_rest = {s.name: rest_rotation(src, s) for _, s in pairs}
    # Target rest, swung to point the way the source bone points at rest (Meshy A-pose -> Mixamo T-pose).
    # Buggy clips: seated, the hips must be at the seat's real height, not a leg-length ratio of it.
    seat = None
    if 'Car' in name:
        lows = []
        for f in range(first, last + 1):
            scene.frame_set(f)
            lows.append((src.matrix_world @ src_hips.head).z)
        seat = min(lows)
    aligned = {d.name: rest_direction(dst, d).rotation_difference(rest_direction(src, s)) @ rest_rotation(dst, d)
               for d, s in pairs}

    for f in range(first, last + 1):
        scene.frame_set(f)
        for b in dst.pose.bones:
            b.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        for d, s in pairs:
            pose = (src.matrix_world @ s.matrix).to_quaternion()
            world_rot = pose @ src_rest[s.name].inverted() @ aligned[d.name]
            if d is dst_hips:
                offset = src.matrix_world @ s.head - src_rest_hips - drift * ((f - first) / max(last - first, 1))
                offset.x *= travel
                offset.y *= travel
                offset.z *= lift
                head = dst_rest_hips + offset
                if seat is not None:
                    z = (src.matrix_world @ s.head).z
                    sit = min(max((src_rest_hips.z - z) / max(src_rest_hips.z - seat, 1e-4), 0.0), 1.0)
                    head.z = head.z * (1 - sit) + z * travel * sit
            else:
                head = dst.matrix_world @ d.head
            arm_rot = dst.matrix_world.to_quaternion().inverted() @ world_rot
            arm_head = dst.matrix_world.inverted() @ head
            d.matrix = Matrix.Translation(arm_head) @ arm_rot.to_matrix().to_4x4()
            bpy.context.view_layer.update()
        for d in dst.pose.bones:
            d.keyframe_insert('scale', frame=f)
            d.keyframe_insert('rotation_quaternion' if d.rotation_mode == 'QUATERNION' else 'rotation_euler', frame=f)
            d.keyframe_insert('location', frame=f)

    for o in new:
        bpy.data.objects.remove(o)
    out = OUT / 'Animations' / f'{name}.fbx'
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    dst.select_set(True)
    bpy.context.view_layer.objects.active = dst
    bpy.ops.export_scene.fbx(filepath=str(out), use_selection=True, object_types={'ARMATURE'}, add_leaf_bones=False,
                             bake_anim=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                             bake_anim_force_startend_keying=True, bake_anim_simplify_factor=0.0)
    print(f'RETARGETED {name}: {len(pairs)} bones, {last - first + 1} frames ({path.name})')


CHARACTER = None


def main():
    global CHARACTER
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    for key in [a for a in args if a in CHARACTERS] or list(CHARACTERS):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        CHARACTER = use_character(key)
        print(f'===== {key}: {CHARACTER["out"]}')
        rig = build_body()
        for clip in CLIPS:
            retarget(rig, clip)


main()
