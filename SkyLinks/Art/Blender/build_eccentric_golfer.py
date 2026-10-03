"""The Meshy golfers as players: body for Unreal plus every golf clip retargeted onto them.

    python Art/Blender/build_eccentric_golfer.py -- man      (bpy module, Blender 4.2; "woman", or both by default)
    blender -b --factory-startup --python Art/Blender/build_eccentric_golfer.py -- clips   (Blender 5.0 too;
                                                             "clips" leaves Golfer.fbx alone)

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
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

import sys

ROOT = Path(__file__).resolve().parents[2]
GOLFER = ROOT / 'Art' / 'Golfer'
RUN_FBX = GOLFER / 'Meshy_Eccentric_Woman' / 'Goofy Running.fbx'

OLD_SCALE = 1.9    # AGolfCharacter scaled the old golfer (whose clips these mostly are) by this
# Mixamo clips downloaded on Y-Bot (life-size, standard Mixamo rig): Art/Golfer/YBot/<clip>[ female].fbx. Where one
# exists it replaces the old golfer's clip (Golf Drive, Golf Chip, Golf Putt so far); each golfer's ybot_walk (in place)
# replaces the Meshy walk.
YBOT = GOLFER / 'YBot'
YBOT_SUFFIX = {'male': '', 'female': ' female'}
TRIANGLES = 32000  # mobile budget for the body

# Per character: Meshy folder and file prefix, output folder (Art/Golfer/<out>, /Game/Characters/<out>), height in
# game (cm; keep AGolfCharacter's body table in step) and whether the Meshy walk replaces the old golfer's.
CHARACTERS = {
    # Both are the same Meshy rig, so she runs with his run (hers never puts the left foot down). Both Meshy jogs
    # are jogs on the spot (feet travel 30-40 cm/s), so the game jogs with the run clip and A_Jog goes unused.
    'man': dict(folder='Meshy_Eccentric_Golfer', prefix='Meshy_AI_Eccentric_Golfer_biped', out='Eccentric',
                material='M_EccentricGolfer', height=180.0, own_walk=True, ybot='male', ybot_walk='Walking man',
                jog='Jog Forward.fbx', run='Running (1).fbx'),
    'woman': dict(folder='Meshy_Eccentric_Woman', prefix='Meshy_AI_Retro_Fairway_Diva_biped', out='Diva',
                  material='M_FairwayDiva', height=172.0, own_walk=True, ybot='female', ybot_walk='Walking female',
                  jog='Jogging.fbx', run='../Meshy_Eccentric_Golfer/Running (1).fbx'),
    # The teenage girl came rigged but with no clips: she walks and jogs with the wife's, runs with the man's.
    'teen': dict(folder='Meshy_Teen_Girl', prefix='Meshy_AI_Fairway_Flair', out='Teen',
                 material='M_FairwayFlair', height=163.0, own_walk=False, ybot='female', ybot_walk='Walking female',
                 walk='../Meshy_Eccentric_Woman/Meshy_AI_Retro_Fairway_Diva_biped_Animation_Walking_withSkin.fbx',
                 jog='../Meshy_Eccentric_Woman/Jogging.fbx', run='../Meshy_Eccentric_Golfer/Running (1).fbx'),
    # The lad came unrigged: Art/Blender/rig_from_donor.py gave him the man's skeleton and weights, and his clips.
    'lad': dict(folder='Meshy_Lad', prefix='Meshy_AI_Flamingo_Fairway', out='Lad',
                material='M_FlamingoFairway', height=178.0, own_walk=False, ybot='male', ybot_walk='lad walking',
                walk='../Meshy_Eccentric_Golfer/Meshy_AI_Eccentric_Golfer_biped_Animation_Walking_withSkin.fbx',
                jog='../Meshy_Eccentric_Golfer/Jog Forward.fbx', run='../Meshy_Eccentric_Golfer/Running (1).fbx'),
}

# Every Meshy biped rig has the same bones: their Mixamo names, for a body that came without a Walking export.
MESHY_TO_MIXAMO = {
    'Hips': 'mixamorig:Hips', 'Spine02': 'mixamorig:Spine', 'Spine01': 'mixamorig:Spine1', 'Spine': 'mixamorig:Spine2',
    'neck': 'mixamorig:Neck', 'Head': 'mixamorig:Head', 'head_end': 'mixamorig:HeadTop_End',
    'LeftShoulder': 'mixamorig:LeftShoulder', 'LeftArm': 'mixamorig:LeftArm', 'LeftForeArm': 'mixamorig:LeftForeArm',
    'LeftHand': 'mixamorig:LeftHand', 'LeftHand_End': 'mixamorig:LeftHandMiddle4',
    'RightShoulder': 'mixamorig:RightShoulder', 'RightArm': 'mixamorig:RightArm',
    'RightForeArm': 'mixamorig:RightForeArm', 'RightHand': 'mixamorig:RightHand',
    'RightHand_End': 'mixamorig:RightHandMiddle4', 'LeftUpLeg': 'mixamorig:LeftUpLeg', 'LeftLeg': 'mixamorig:LeftLeg',
    'LeftFoot': 'mixamorig:LeftFoot', 'LeftToeBase': 'mixamorig:LeftToeBase', 'LeftToe_end': 'mixamorig:LeftToe_End',
    'RightUpLeg': 'mixamorig:RightUpLeg', 'RightLeg': 'mixamorig:RightLeg', 'RightFoot': 'mixamorig:RightFoot',
    'RightToeBase': 'mixamorig:RightToeBase', 'RightToe_end': 'mixamorig:RightToe_End',
}

# Clips where both hands hold the club: the bigger Meshy bodies push the hands 15-35 cm apart, so the left hand
# is pulled back onto the grip (two-bone IK) wherever the source hands were together.
CLUB_CLIPS = {'Golf Drive', 'Golf Drive alt1', 'Golf Chip', 'Golf Chip (replay if long shit in)', 'Golf Putt'}
# Source frames to use, in order. The Mixamo idle twists the hips 90 and the shoulders 150 degrees looking round,
# which read as the golfer turning at random: loop its calm stretch instead (end, then start: still, breathing).
SOURCE_FRAMES = {}  # (the looped calm stretch of the idle snapped where it wrapped: the whole original clip is back)
# Gaits whose planted feet are locked and whose ground speed AGolfCharacter's body table needs (printed as SPEED).
GAITS = {'Walking', 'Jogging', 'Running'}

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
    """(fbx, native, full_size): the old golfer's clip, a Y-Bot one, or one made on the Meshy rig (native: in place).
    full_size: the source character is life-size (Meshy, Y-Bot), so hip travel scales by hip height; the old
    golfer's clips were made on a 95 cm body the game scaled 1.9x."""
    # Y-Bot jog and run (Art/Golfer/YBot/Jog Forward.fbx, Running.fbx) for every golfer; the Meshy ones are the fallback.
    for gait, ybot_file, meshy_key in (('Jogging', 'Jog Forward', 'jog'), ('Running', 'Running', 'run')):
        if name == gait:
            if (YBOT / f'{ybot_file}.fbx').is_file():
                return YBOT / f'{ybot_file}.fbx', True, True
            return (MESHY / character[meshy_key]).resolve(), True, True
    if name == 'Walking' and (YBOT / f"{character['ybot_walk']}.fbx").is_file():
        return YBOT / f"{character['ybot_walk']}.fbx", True, True
    if name == 'Walking' and character['own_walk']:
        return NAMES_FBX, True, True
    if name == 'Walking' and character.get('walk'):
        return (MESHY / character['walk']).resolve(), True, True
    # The female clip where there is one (the golf shots), else the male Y-Bot one (the buggy clips).
    for suffix in (YBOT_SUFFIX[character['ybot']], ''):
        ybot = YBOT / f"{name}{suffix}.fbx"
        if ybot.is_file():
            return ybot, False, True
    fixed = GOLFER / 'Animations' / 'Fixed' / f'{name}.fbx'
    return (fixed if fixed.is_file() else GOLFER / 'Animations' / f'{name}.fbx'), False, False


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
    renames = {}
    if NAMES_FBX.is_file():
        named = import_fbx(NAMES_FBX)
        ref = next(o for o in named if o.type == 'ARMATURE')
        ref_heads = [(b.name, ref.matrix_world @ b.head_local) for b in ref.data.bones]
        for b in arm.data.bones:
            head = arm.matrix_world @ b.head_local
            name, where = min(ref_heads, key=lambda item: (item[1] - head).length)
            if (where - head).length < 0.005:
                renames[b.name] = name
        for o in named:
            bpy.data.objects.remove(o)
    else:
        renames = {b.name: MESHY_TO_MIXAMO[b.name] for b in arm.data.bones if b.name in MESHY_TO_MIXAMO}
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
    if EXPORT_BODY:
        bpy.ops.object.select_all(action='DESELECT')
        arm.select_set(True)
        body.select_set(True)
        bpy.ops.export_scene.fbx(filepath=str(OUT / 'Golfer.fbx'), use_selection=True,
                                 object_types={'ARMATURE', 'MESH'}, add_leaf_bones=False, bake_anim=False,
                                 path_mode='COPY', embed_textures=True, mesh_smooth_type='FACE')
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


def channel_fcurves(action, slot=None):
    """An action's F-curves: Blender 4.4+ keeps them per slot (5.0 dropped Action.fcurves), 4.2 on the action."""
    if not hasattr(action, 'layers'):
        return list(action.fcurves)
    curves = []
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                if slot is None or bag.slot == slot:
                    curves += list(bag.fcurves)
    return curves


def use_action(obj, action):
    if obj.animation_data is None:
        obj.animation_data_create()
    obj.animation_data.action = action
    if hasattr(action, 'slots') and len(action.slots) and obj.animation_data.action_slot is None:
        obj.animation_data.action_slot = action.slots[0]


def two_bone_ik(arm, upper, lower, hand, target):
    """Swing upper and lower so the hand's head reaches target (armature space), keeping the elbow's bend plane
    and the hand's own rotation."""
    keep = hand.matrix.to_quaternion()
    s, e, w = upper.head.copy(), lower.head.copy(), hand.head.copy()
    a, b = (e - s).length, (w - e).length
    to = target - s
    d = min(to.length, (a + b) * 0.999)
    if d < 1e-6:
        return
    u = to.normalized()
    side = (e - s) - u * (e - s).dot(u)
    if side.length < 1e-6:
        side = (w - s).orthogonal()
    side.normalize()
    x = (a * a - b * b + d * d) / (2 * d)
    elbow = s + u * x + side * max(a * a - x * x, 0.0) ** 0.5

    def swing(bone, pivot, before, after):
        rot = before.rotation_difference(after).to_matrix().to_4x4()
        bone.matrix = Matrix.Translation(pivot) @ rot @ Matrix.Translation(-pivot) @ bone.matrix
        bpy.context.view_layer.update()

    swing(upper, s, e - s, elbow - s)
    swing(lower, lower.head.copy(), hand.head - lower.head, (s + u * d) - lower.head)
    hand.matrix = Matrix.Translation(hand.head.copy()) @ keep.to_matrix().to_4x4()
    bpy.context.view_layer.update()


FOOT_POINTS = ('LeftFoot', 'RightFoot', 'LeftToeBase', 'RightToeBase', 'LeftToe_End', 'RightToe_End')


def foot_points(arm):
    """Per foot, (pose bone, rest height in world) for the ankle, ball and toe tip that exist."""
    bones = {short(b.name): b for b in arm.pose.bones}
    return {side: [(bones[n], (arm.matrix_world @ bones[n].bone.head_local).z)
                   for n in FOOT_POINTS if n.startswith(side) and n in bones]
            for side in ('Left', 'Right')}


def foot_low(arm, points):
    """How far below its resting height the lowest part of this foot is (0: sole on the floor, as at rest)."""
    return min((arm.matrix_world @ b.head).z - rest for b, rest in points)


def put_on_floor(arm, hips, first, last, name):
    """Shift the whole clip up or down so the planted feet are on the floor: the retarget carries the source's
    hip height over by a leg-length ratio, which left the jogs 7-20 cm into the ground and other clips floating."""
    feet = foot_points(arm)
    lows = []
    for f in range(first, last + 1):
        bpy.context.scene.frame_set(f)
        lows.append(min(foot_low(arm, p) for p in feet.values()))
    # Loops (walk, jog, run, idle): the lower fifth, the frames with a foot planted (runs spend the rest in the
    # air). Every other clip starts standing on both feet: its first frame (the missed putt kneels for most of it).
    rise = -sorted(lows)[len(lows) // 5] if name in ('Walking', 'Jogging', 'Running') else -lows[0]
    lows.sort()
    world_up = arm.matrix_world.inverted().to_3x3() @ Vector((0.0, 0.0, rise))
    local = hips.bone.matrix_local.to_3x3().inverted() @ world_up
    path = f'pose.bones["{hips.name}"].location'
    for fc in channel_fcurves(arm.animation_data.action, getattr(arm.animation_data, 'action_slot', None)):
        if fc.data_path == path:
            for key in fc.keyframe_points:
                key.co.y += local[fc.array_index]
                key.handle_left.y += local[fc.array_index]
                key.handle_right.y += local[fc.array_index]
            fc.update()
    print(f'FLOOR {name}: raised {rise * 100:+.1f} cm (lowest foot was {lows[0] * 100:+.1f} cm, '
          f'now {(lows[0] + rise) * 100:+.1f} cm)')


def lock_feet(arm, first, last, name, contact=0.03):
    """In-place gait: make each planted foot slide straight back at one steady speed, bending the leg (two-bone IK)
    to follow, and return that speed in cm/s in game. The Meshy walk / jog / run wobble their planted feet back and
    forth (his jog even slides one forward), so no play rate could stop them skating; now the game's
    speed / clip speed play rate keeps them still on the ground. The clips face -Y, so planted feet move +Y."""
    scene = bpy.context.scene
    fps = scene.render.fps / scene.render.fps_base
    bones = {short(b.name): b for b in arm.pose.bones}
    feet = foot_points(arm)
    frames = list(range(first, last + 1))
    n = len(frames)
    track = {side: [] for side in feet}
    for f in frames:
        scene.frame_set(f)
        for side, points in feet.items():
            # The ball of the foot is what stays on the ground (the heel lifts late in the step).
            track[side].append((foot_low(arm, points), (arm.matrix_world @ bones[side + 'ToeBase'].head).copy(),
                                (arm.matrix_world @ bones[side + 'Foot'].head).copy()))

    # Planted spans per foot, wrapping round the loop (lists of frame indices).
    spans = {}
    for side in feet:
        # Planted: low, and not moving forward (-Y). A swinging foot can stay low too (a shuffling walk barely lifts
        # its feet, a toe can drag through the floor), but it always moves forward.
        down = [step[0] < contact and track[side][(i + 1) % n][1].y - step[1].y > -0.002
                for i, step in enumerate(track[side])]
        for i in range(n):  # a one-frame lift inside a step is still the same step
            if not down[i] and down[i - 1] and down[(i + 1) % n]:
                down[i] = True
        if all(down) or not any(down):
            spans[side] = []
            continue
        start = down.index(False)
        runs, cur = [], []
        for k in range(n):
            i = (start + k) % n
            if down[i]:
                cur.append(i)
            elif cur:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        # A toe dragging forward at the start of the swing isn't planted: trim the ends while the foot goes forward.
        for r in runs:
            while len(r) > 1 and track[side][r[1]][1].y < track[side][r[0]][1].y:
                r.pop(0)
            while len(r) > 1 and track[side][r[-1]][1].y < track[side][r[-2]][1].y:
                r.pop()
        spans[side] = [r for r in runs if len(r) >= 3]

    # One speed for the clip: the planted feet's average backward travel per second.
    travel = time = 0.0
    for side, runs in spans.items():
        for r in runs:
            travel += track[side][r[-1]][1].y - track[side][r[0]][1].y
            time += (len(r) - 1) / fps
    speed = travel / time if time > 0 else 0.0
    if speed <= 0.0:
        print(f'FEET {name}: no clean planted steps, left as they are')
        return 0.0

    targets = {}  # frame index -> {side: world target}
    for side, runs in spans.items():
        for r in runs:
            mid = sum((track[side][i][1] for i in r), Vector()) / len(r)
            for k, i in enumerate(r):
                was = track[side][i][1]
                want = Vector((mid.x, mid.y + speed * (k - (len(r) - 1) / 2) / fps, was.z))
                weight = min(1.0, (k + 1) / 2, (len(r) - k) / 2)  # ease in and out of the step
                # The leg reaches with the ankle: move it as far as the ball of the foot has to go.
                targets.setdefault(i, {})[side] = track[side][i][2] + (was.lerp(want, weight) - was)
    to_arm = arm.matrix_world.inverted()
    moved = 0.0
    for i, sides in targets.items():
        scene.frame_set(frames[i])
        for side, target in sides.items():
            moved = max(moved, (target - track[side][i][2]).length)
            chain = [bones[side + 'UpLeg'], bones[side + 'Leg'], bones[side + 'Foot']]
            two_bone_ik(arm, *chain, to_arm @ target)
            for b in chain:
                b.keyframe_insert('rotation_quaternion' if b.rotation_mode == 'QUATERNION' else 'rotation_euler',
                                  frame=frames[i])
                b.keyframe_insert('location', frame=frames[i])
    steps = sum(len(r) for r in spans.values())
    print(f'FEET {name}: {steps} planted steps locked, feet moved up to {moved * 100:.1f} cm '
          f'(fps {scene.render.fps}/{scene.render.fps_base:.3f}, {travel * 100:.1f} cm over {time:.2f} s)')
    return speed * 100 * GAME_SCALE


def rest_rotation(arm, bone):
    return (arm.matrix_world @ bone.bone.matrix_local).to_quaternion()


def rest_direction(arm, bone):
    return (arm.matrix_world.to_3x3() @ (bone.bone.tail_local - bone.bone.head_local)).normalized()


def retarget(dst, name):
    path, native, full_size = clip_source(name, CHARACTER)
    if not path.is_file():
        print(f'MISSING {name}')
        return
    known = set(bpy.data.actions)
    new = import_fbx(path)
    src = next(o for o in new if o.type == 'ARMATURE')
    # Meshy "with skin" exports carry a one-frame bind action as well as the motion: use the longest one.
    actions = [a for a in bpy.data.actions if a not in known]
    motion = max((a for a in actions if any(fc.data_path.startswith('pose.bones') for fc in channel_fcurves(a))),
                 key=lambda a: a.frame_range[1] - a.frame_range[0])
    use_action(src, motion)
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
    travel = lift if full_size else OLD_SCALE / GAME_SCALE
    # Meshy clips walk or run forward: take that out (the character moves them), noting the speed it matched.
    drift = Vector((0.0, 0.0, 0.0))
    if native:
        scene.frame_set(first)
        start = src.matrix_world @ src_hips.head
        scene.frame_set(last)
        drift = (src.matrix_world @ src_hips.head) - start
        drift.z = 0.0
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

    dst_bone = {short(b.name): b for b in dst.pose.bones}
    grip = name in CLUB_CLIPS and all(k in src_bones and k in dst_bone for k in
                                      ('LeftArm', 'LeftForeArm', 'LeftHand', 'RightHand'))
    regrips = []

    source_frames = SOURCE_FRAMES.get(name, range(first, last + 1))
    for f, at in enumerate(source_frames, first):
        scene.frame_set(at)
        for b in dst.pose.bones:
            b.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        for d, s in pairs:
            pose = (src.matrix_world @ s.matrix).to_quaternion()
            world_rot = pose @ src_rest[s.name].inverted() @ aligned[d.name]
            if d is dst_hips:
                offset = src.matrix_world @ s.head - src_rest_hips - drift * ((at - first) / max(last - first, 1))
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
        if grip:
            # Both hands on the club: put the left hand where it was against the right in the source clip (scaled
            # like the rest of the clip), fully while the source hands were together, fading out as they part.
            src_gap = ((src.matrix_world @ src_bones['LeftHand'].head) - (src.matrix_world @ src_bones['RightHand'].head)) * travel
            weight = min(max((0.30 - src_gap.length) / 0.10, 0.0), 1.0)
            if weight > 0.0:
                to_arm = dst.matrix_world.inverted()
                right = dst.matrix_world @ dst_bone['RightHand'].head
                left = dst.matrix_world @ dst_bone['LeftHand'].head
                regrips.append((left - right).length - src_gap.length)
                target = left.lerp(right + src_gap, weight)
                two_bone_ik(dst, dst_bone['LeftArm'], dst_bone['LeftForeArm'], dst_bone['LeftHand'], to_arm @ target)
        for d in dst.pose.bones:
            d.keyframe_insert('scale', frame=f)
            d.keyframe_insert('rotation_quaternion' if d.rotation_mode == 'QUATERNION' else 'rotation_euler', frame=f)
            d.keyframe_insert('location', frame=f)
    last = first + len(source_frames) - 1
    scene.frame_end = last
    if regrips:
        print(f'GRIP {name}: left hand moved back onto the club on {len(regrips)} frames '
              f'(was up to {max(regrips) * 100:.0f} cm off)')

    if seat is None:
        put_on_floor(dst, dst_hips, first, last, name)
    if name in GAITS:
        print(f'SPEED {name}: feet move {lock_feet(dst, first, last, name):.0f} cm/s in game at play rate 1 '
              f'(AGolfCharacter body table)')

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
EXPORT_BODY = True


def main():
    global CHARACTER, EXPORT_BODY
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    EXPORT_BODY = 'clips' not in args  # "clips": rebuild the animations only, leave Golfer.fbx as it is
    for key in [a for a in args if a in CHARACTERS] or list(CHARACTERS):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        CHARACTER = use_character(key)
        print(f'===== {key}: {CHARACTER["out"]}')
        rig = build_body()
        for clip in [a for a in args if a in CLIPS] or CLIPS:  # name clips to rebuild only those
            retarget(rig, clip)


main()
