"""The Meshy buggy's driver door (SM_Buggy_Door): a low cream half-door with a black top rail and a handle.

Run: blender --background --python Art/Blender/build_buggy_door.py
Writes Art/BuggyMeshy/GameParts/SM_Buggy_Door.fbx, same axes and units as SM_Buggy_Body.fbx.
The origin is the hinge, at the front edge of the driver's opening; the panel runs back (-X) from it. AGolfBuggy puts
that origin at DoorHinge on the body (Meshy body: front edge x = +0.50 m, side y = 0.50 m, sill z = 0.40 m) and turns
it about Z to open. Materials: slot 0 'M_BuggyDoorPaint' (cream), slot 1 'M_BuggyDoorTrim' (black); Scripts/import_buggy_door.py
makes them in Unreal."""
from pathlib import Path

import bpy
import bmesh

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'BuggyMeshy' / 'GameParts' / 'SM_Buggy_Door.fbx'

LENGTH, HEIGHT, THICK = 0.78, 0.42, 0.03  # m


def box(bm, x0, x1, y0, y1, z0, z1, material):
    verts = [bm.verts.new((x, y, z)) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    faces = bmesh.ops.convex_hull(bm, input=verts)['geom']
    for f in [g for g in faces if isinstance(g, bmesh.types.BMFace)]:
        f.material_index = material
    edges = [e for e in bm.edges if e.verts[0] in verts and e.verts[1] in verts]
    bmesh.ops.bevel(bm, geom=edges, offset=0.006, segments=2, affect='EDGES')


bpy.ops.wm.read_factory_settings(use_empty=True)
mesh = bpy.data.meshes.new('SM_Buggy_Door')
obj = bpy.data.objects.new('SM_Buggy_Door', mesh)
bpy.context.scene.collection.objects.link(obj)
bm = bmesh.new()
box(bm, -LENGTH, 0.0, -THICK / 2, THICK / 2, 0.0, HEIGHT, 0)                       # the cream panel
box(bm, -LENGTH, 0.0, -THICK / 2 - 0.006, THICK / 2 + 0.006, HEIGHT - 0.035, HEIGHT + 0.012, 1)  # black top rail
box(bm, -LENGTH + 0.05, -LENGTH + 0.17, THICK / 2, THICK / 2 + 0.025, HEIGHT - 0.12, HEIGHT - 0.07, 1)  # handle
bm.to_mesh(mesh)
bm.free()
for name, colour in (('M_BuggyDoorPaint', (0.86, 0.82, 0.72, 1)), ('M_BuggyDoorTrim', (0.03, 0.03, 0.03, 1))):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = colour
    mesh.materials.append(mat)
mesh.update()
bpy.ops.object.select_all(action='DESELECT')
obj.select_set(True)
bpy.context.view_layer.objects.active = obj
bpy.ops.export_scene.fbx(filepath=str(OUT), use_selection=True, object_types={'MESH'}, apply_scale_options='FBX_SCALE_UNITS',
                         axis_forward='-Y', axis_up='Z', bake_anim=False, path_mode='STRIP')
print('DOOR', OUT, len(mesh.polygons), 'faces')
