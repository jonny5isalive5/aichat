"""Reduce the downloaded CC0 tree_small_02_1k.blend in a fresh background Blender process.
See Art/Vegetation/README.md for source and invocation. Never run in an unsaved user scene.
"""
import bpy,json,math
from pathlib import Path
from mathutils import Vector
out=Path(__file__).resolve().parents[1] / 'Vegetation'
out.mkdir(parents=True, exist_ok=True)
source=bpy.data.objects['tree_small_02_LOD1']
# Work in this newly launched background Blender process only.
for collection in bpy.data.collections:
 collection.hide_viewport=False;collection.hide_render=False
for obj in bpy.data.objects:
 obj.hide_set(False);obj.hide_viewport=False;obj.hide_render=(obj!=source)
bpy.ops.object.select_all(action='DESELECT')
source.hide_render=False;source.select_set(True);bpy.context.view_layer.objects.active=source
source.name='SM_SmallTree_LOD0'
# Collapse reduces the existing UV-mapped mesh; preserve its material boundaries.
source.data.calc_loop_triangles()
initial=len(source.data.loop_triangles)
mod=source.modifiers.new('CourseBudget','DECIMATE');mod.ratio=min(1.0,60000/initial)
mod.use_collapse_triangulate=True
bpy.ops.object.modifier_apply(modifier=mod.name)
source.data.calc_loop_triangles()
report={'source_triangles':initial,'lod0_triangles':len(source.data.loop_triangles),'dimensions_m':list(source.dimensions),'materials':[m.name for m in source.data.materials]}
bpy.ops.export_scene.fbx(filepath=str(out/'SM_SmallTree.fbx'),use_selection=True,object_types={'MESH'},apply_unit_scale=True,axis_forward='-Y',axis_up='Z',use_mesh_modifiers=True,bake_anim=False,path_mode='STRIP')
# Preview with original source textures and simple outdoor lighting.
for img in bpy.data.images:
 candidate=(Path(bpy.data.filepath).parent / 'textures')/img.filepath.replace(chr(92), '/').split('/')[-1]
 if candidate.exists():img.filepath=str(candidate);img.reload()
scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.samples=24
scene.render.resolution_x=900;scene.render.resolution_y=900;scene.render.resolution_percentage=100
scene.world.color=(.25,.25,.25)
bpy.ops.object.light_add(type='SUN',rotation=(math.radians(25),math.radians(-25),math.radians(-40)))
bpy.context.object.data.energy=3
bpy.ops.object.camera_add(location=(8,-10,6))
cam=bpy.context.object;target=Vector((0,0,2.3));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=6.2;scene.camera=cam
scene.render.film_transparent=False
scene.render.filepath=str(out/'SmallTree_preview.png')
(out/'mesh-report.json').write_text(json.dumps(report,indent=2))
bpy.ops.render.render(write_still=True)
print(report)
