"""Rig an unrigged Meshy character (T-pose, facing -Y) with the same skeleton as a rigged Meshy one.

    blender -b --factory-startup --python Art/Blender/rig_from_donor.py -- <unrigged.fbx> <donor Character_output.fbx> <out Character_output.fbx>

The donor gives the bones (names, hierarchy, orientations); every joint is then placed inside the new body by
measuring it: the spine and head on the body's centre line at heights matched by landmarks (floor, crotch, arm
line, neck, top of the head), hips / knees / ankles at the middle of each leg, shoulder / elbow / wrist along the
middle of each arm from where it leaves the torso to the fingertips, and the foot bones fitted to each shoe. Each
bone keeps the donor's twist about its own length. The skin is Blender's automatic (bone heat) weights; any loose
bits it can't reach (hair spikes, shoe studs) take the weights of the nearest skinned point. The result is the same
Meshy rig (same bone names) as Meshy's own rigging gives, so build_eccentric_golfer.py takes it like the others.

(A first version warped the donor's skeleton and weights by landmarks alone: the donor stands in Meshy's A-pose,
arms 20 degrees down and legs apart, so on the lad's T-pose the arm and leg bones ended up outside his limbs and
the copied weights bent his legs and tipped him forward.)
"""
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

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


def standing(body):
    """Scale the body to Meshy's 1.7 m and stand it centred on the floor."""
    apply_transform([body])
    v = verts(body)
    s = HEIGHT / (v[:, 2].max() - v[:, 2].min())
    body.scale = (s, s, s)
    apply_transform([body])
    v = verts(body)
    body.location = (-(v[:, 0].max() + v[:, 0].min()) / 2, -(v[:, 1].max() + v[:, 1].min()) / 2, -v[:, 2].min())
    apply_transform([body])
    return verts(body)


class Body:
    """Measurements of a body standing on the floor, facing -Y, arms out to the sides."""

    def __init__(self, v):
        self.v = v
        self.low, self.high = float(v[:, 2].min()), float(v[:, 2].max())
        self.span = float(np.abs(v[:, 0]).max())
        self.crotch = next(z for z in np.linspace(self.low, self.low + 0.6 * (self.high - self.low), 600)
                           if (np.abs(self.band(z, 0.005)[:, 0]) < 0.01).any())
        arms = v[(np.abs(v[:, 0]) > 0.5 * self.span) & (np.abs(v[:, 0]) < 0.7 * self.span)]
        self.arm = float(np.median(arms[:, 2]))
        # The neck: the narrowest the centre column gets between the arm line and the head.
        zs = np.linspace(self.arm, self.arm + 0.4 * (self.high - self.arm), 80)
        width = []
        for z in zs:
            ring = self.band(z, 0.006)
            ring = ring[np.abs(ring[:, 0]) < 0.25]
            width.append(float(np.abs(ring[:, 0]).max()) if len(ring) else 9.0)
        self.neck = float(zs[int(np.argmin(width))])
        self.knots = [self.low, self.crotch, self.arm, self.neck, self.high]

    def band(self, z, half):
        return self.v[np.abs(self.v[:, 2] - z) < half]

    def column_y(self, z):
        """Front-to-back middle of the trunk at this height."""
        ring = self.band(z, 0.01)
        ring = ring[np.abs(ring[:, 0]) < 0.12]
        return float((ring[:, 1].min() + ring[:, 1].max()) / 2) if len(ring) else 0.0

    def leg_centre(self, z, side):
        ring = self.band(z, 0.01)
        ring = ring[ring[:, 0] * side > 0.005]
        if z < self.crotch:  # one leg only: it's a ring of its own
            return Vector(((ring[:, 0].min() + ring[:, 0].max()) / 2, (ring[:, 1].min() + ring[:, 1].max()) / 2, z))
        return Vector((float(np.median(ring[:, 0])), (ring[:, 1].min() + ring[:, 1].max()) / 2, z))

    def shoe(self, side, ankle_z):
        s = self.v[(self.v[:, 2] < ankle_z) & (self.v[:, 0] * side > 0.0)]
        return s.min(0), s.max(0)

    def arm_axis(self, side):
        """Middle of the arm's cross-section along x, from where the arm leaves the torso to the fingertips."""
        xs = np.linspace(0.02, self.span - 0.005, 200)
        pts, thick = [], []
        for x in xs:
            ring = self.v[(np.abs(self.v[:, 0] - side * x) < 0.006) & (np.abs(self.v[:, 2] - self.arm) < 0.25)]
            if len(ring) < 6:
                pts.append(None)
                thick.append(9.0)
                continue
            # Only the part of the slice around the arm line (the torso slice also holds the shoulders and hips).
            near = ring[np.abs(ring[:, 2] - self.arm) < 0.12]
            near = near if len(near) >= 6 else ring
            pts.append(Vector((side * x, (near[:, 1].min() + near[:, 1].max()) / 2, (near[:, 2].min() + near[:, 2].max()) / 2)))
            thick.append(float(ring[:, 2].max() - ring[:, 2].min()))
        thick = np.array(thick)
        arm_thick = float(np.median(thick[(xs > 0.5 * self.span) & (xs < 0.7 * self.span)]))
        edge = next(i for i in range(len(xs)) if xs[i] > 0.08 and thick[i] < 1.6 * arm_thick)
        shoulder_x = xs[edge] - 0.5 * arm_thick
        line = [p for p, x in zip(pts, xs) if p is not None and x >= shoulder_x]
        line[0] = Vector((side * shoulder_x, line[0].y, line[0].z))
        return line, arm_thick


def zmap(z, a, b):
    """A height on body a to the matching height on body b, between their landmarks."""
    return float(np.interp(z, a.knots, b.knots, left=z - a.knots[0] + b.knots[0], right=z - a.knots[-1] + b.knots[-1]))


def along(line, dist):
    """The point this far along a polyline (extended straight past its end)."""
    for p, q in zip(line, line[1:]):
        step = (q - p).length
        if dist <= step:
            return p.lerp(q, dist / step) if step > 0 else p.copy()
        dist -= step
    return line[-1] + (line[-1] - line[-2]).normalized() * dist


def length(line):
    return sum((q - p).length for p, q in zip(line, line[1:]))


def fit_skeleton(arm, donor, body):
    """New head and tail for every bone, measured on the new body."""
    eb = {b.name: b for b in arm.data.edit_bones}
    head = {n: b.head.copy() for n, b in eb.items()}
    tail = {n: b.tail.copy() for n, b in eb.items()}
    new_head, new_tail = {}, {}

    # Spine, neck and head on the centre line.
    for n in ('Hips', 'Spine02', 'Spine01', 'Spine', 'neck', 'Head', 'head_end'):
        for src, dst in ((head, new_head), (tail, new_tail)):
            z = zmap(src[n].z, donor, body)
            dst[n] = Vector((0.0, body.column_y(min(z, body.neck)) + (src[n].y - donor.column_y(min(src[n].z, donor.neck))), z))
    offset = head['headfront'] - head['Head']
    new_head['headfront'] = new_head['Head'] + offset
    new_tail['headfront'] = new_head['headfront'] + (tail['headfront'] - head['headfront'])

    for side, pre in ((1.0, 'Left'), (-1.0, 'Right')):
        # Legs: hip joint, knee and ankle at the middle of the leg; heights as on the donor's leg.
        hip_z = zmap(head[pre + 'UpLeg'].z, donor, body)
        d_hip, d_knee, d_ankle = head[pre + 'UpLeg'].z, head[pre + 'Leg'].z, head[pre + 'Foot'].z
        ankle_z = body.low + (d_ankle - donor.low) * (hip_z - body.low) / (d_hip - donor.low)
        knee_z = ankle_z + (d_knee - d_ankle) / (d_hip - d_ankle) * (hip_z - ankle_z)
        new_head[pre + 'UpLeg'] = body.leg_centre(hip_z, side)
        new_head[pre + 'Leg'] = new_tail[pre + 'UpLeg'] = body.leg_centre(knee_z, side)
        new_head[pre + 'Foot'] = new_tail[pre + 'Leg'] = body.leg_centre(ankle_z, side)
        # Foot bones: placed in the shoe as they sit in the donor's shoe.
        d_lo, d_hi = donor.shoe(side, d_ankle)
        b_lo, b_hi = body.shoe(side, ankle_z)

        def in_shoe(p):
            u = (np.array(p) - d_lo) / np.maximum(d_hi - d_lo, 1e-6)
            return Vector(b_lo + u * (b_hi - b_lo))
        for n in ('Foot',):
            new_tail[pre + n] = in_shoe(tail[pre + n])
        for n in ('ToeBase', 'Toe_end'):
            new_head[pre + n], new_tail[pre + n] = in_shoe(head[pre + n]), in_shoe(tail[pre + n])

        # Arms: shoulder joint where the arm leaves the torso; elbow, wrist and fingertip along the arm's middle,
        # spaced as on the donor's arm.
        line, _ = body.arm_axis(side)
        reach = length(line)
        d_parts = [(tail[pre + n] - head[pre + n]).length for n in ('Arm', 'ForeArm', 'Hand')]
        scale = reach / sum(d_parts)
        at = 0.0
        for n, part in zip(('Arm', 'ForeArm', 'Hand'), d_parts):
            new_head[pre + n] = along(line, at)
            at += part * scale
            new_tail[pre + n] = along(line, at)
        end = (tail[pre + 'Hand_End'] - head[pre + 'Hand_End']).length * scale
        new_head[pre + 'Hand_End'] = new_tail[pre + 'Hand']
        new_tail[pre + 'Hand_End'] = along(line, at + end)
        shoulder = head[pre + 'Shoulder']
        new_head[pre + 'Shoulder'] = Vector((shoulder.x * new_head[pre + 'Arm'].x / head[pre + 'Arm'].x,
                                             new_head[pre + 'Arm'].y, new_head[pre + 'Arm'].z))
        new_tail[pre + 'Shoulder'] = new_head[pre + 'Arm'].copy()

    missing = set(eb) - set(new_head)
    assert not missing, f'no fit for {missing}'
    for n, b in eb.items():
        was = (tail[n] - head[n]).normalized()
        twist = b.z_axis.copy()
        b.head, b.tail = new_head[n], new_tail.get(n, new_head[n] + (tail[n] - head[n]))
        # Keep the donor's twist about the bone: turn its old z axis with the bone.
        b.align_roll(was.rotation_difference((b.tail - b.head).normalized()) @ twist)
    for n, b in eb.items():
        if b.use_connect and b.parent:
            b.parent.tail = b.head


def main():
    args = sys.argv[sys.argv.index('--') + 1:]
    target_path, donor_path, out_path = args[:3]
    bpy.ops.wm.read_factory_settings(use_empty=True)

    new = import_fbx(target_path)
    body = max((o for o in new if o.type == 'MESH'), key=lambda o: len(o.data.vertices))
    for o in new:
        if o is not body:
            bpy.data.objects.remove(o)
    shape = Body(standing(body))

    donor_objs = import_fbx(donor_path)
    arm = next(o for o in donor_objs if o.type == 'ARMATURE')
    skin = max((o for o in donor_objs if o.type == 'MESH'), key=lambda o: len(o.data.vertices))
    arm.animation_data_clear()
    skin.parent = None
    skin.modifiers.clear()
    apply_transform([skin])
    apply_transform([arm])
    donor = Body(verts(skin))
    for o in donor_objs:
        if o is not arm:
            bpy.data.objects.remove(o)
    print('DONOR', {k: round(getattr(donor, k), 3) for k in ('low', 'crotch', 'arm', 'neck', 'high', 'span')})
    print('TARGET', {k: round(getattr(shape, k), 3) for k in ('low', 'crotch', 'arm', 'neck', 'high', 'span')})

    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    fit_skeleton(arm, donor, shape)
    bpy.ops.object.mode_set(mode='OBJECT')
    for b in arm.data.bones:
        print(f'JOINT {b.name:16s} {tuple(round(x, 3) for x in b.head_local)} -> {tuple(round(x, 3) for x in b.tail_local)}')

    # Automatic (bone heat) weights.
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')

    # Whatever the heat weighting missed takes the weights of the nearest skinned vertex.
    groups = {g.index: g for g in body.vertex_groups}
    weighted = [v.index for v in body.data.vertices if any(g.weight > 1e-4 for g in v.groups)]
    bare = [v.index for v in body.data.vertices if not any(g.weight > 1e-4 for g in v.groups)]
    if bare and weighted:
        tree = KDTree(len(weighted))
        for i in weighted:
            tree.insert(body.data.vertices[i].co, i)
        tree.balance()
        for i in bare:
            _, near, _ = tree.find(body.data.vertices[i].co)
            for g in body.data.vertices[near].groups:
                groups[g.group].add([i], g.weight, 'REPLACE')
    print(f'WEIGHTS {len(weighted)} vertices skinned by bone heat, {len(bare)} filled from their neighbours')

    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    body.select_set(True)
    bpy.ops.export_scene.fbx(filepath=out_path, use_selection=True, object_types={'ARMATURE', 'MESH'},
                             add_leaf_bones=False, bake_anim=False, path_mode='COPY', embed_textures=True)
    print(f'RIGGED {out_path}: {len(arm.data.bones)} bones, {len(body.vertex_groups)} weight groups')


main()
