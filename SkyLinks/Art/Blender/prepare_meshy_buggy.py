"""Run in a fresh background Blender: --python this.py -- extracted-source-dir.
Preserves the supplied original. Produces a static review mesh, not a vehicle rig.
"""
import bpy, json, sys, hashlib, shutil, math
from pathlib import Path
from mathutils import Vector
src=Path(sys.argv[sys.argv.index('--')+1])
out=Path(__file__).resolve().parents[1]/'BuggyMeshy'
out.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
fbx=next(src.rglob('*.fbx'))
bpy.ops.import_scene.fbx(filepath=str(fbx))
obj=next(o for o in bpy.context.scene.objects if o.type=='MESH')
bpy.context.view_layer.objects.active=obj
bpy.ops.object.select_all(action='DESELECT');obj.select_set(True)
bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
obj.data.calc_loop_triangles();initial=len(obj.data.loop_triangles)
# Ground-centred origin; provisional 3.2m overall length for visual review.
verts=[v.co for v in obj.data.vertices]
mins=Vector(tuple(min(v[i] for v in verts) for i in range(3)))
maxs=Vector(tuple(max(v[i] for v in verts) for i in range(3)))
offset=Vector(((mins.x+maxs.x)/2,(mins.y+maxs.y)/2,mins.z))
scale=3.2/(maxs.x-mins.x)
for v in obj.data.vertices:v.co=(v.co-offset)*scale
obj.location=(0,0,0)
mat=bpy.data.materials.new('M_MeshyBuggy');mat.use_nodes=True
obj.data.materials.clear();obj.data.materials.append(mat)
nodes=mat.node_tree.nodes;links=mat.node_tree.links;bsdf=nodes.get('Principled BSDF')
maps={};hashes={}
for suffix,slot in [('_texture.png','Base Color'),('_texture_roughness.png','Roughness'),('_texture_metallic.png','Metallic'),('_texture_normal.png','Normal')]:
 p=next(src.rglob('*'+suffix));dest=out/('T_Buggy_'+slot.replace(' ','')+'.png');shutil.copy2(p,dest)
 im=bpy.data.images.load(str(dest));im.colorspace_settings.name='sRGB' if slot=='Base Color' else 'Non-Color'
 n=nodes.new('ShaderNodeTexImage');n.image=im
 if slot=='Normal':
  normal=nodes.new('ShaderNodeNormalMap');links.new(n.outputs['Color'],normal.inputs['Color']);links.new(normal.outputs['Normal'],bsdf.inputs['Normal'])
 else:links.new(n.outputs['Color'],bsdf.inputs[slot])
 maps[slot]=dest.name;hashes[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
hashes[fbx.name]=hashlib.sha256(fbx.read_bytes()).hexdigest()
mod=obj.modifiers.new('ReviewReduction','DECIMATE');mod.ratio=45000/initial;mod.use_collapse_triangulate=True
bpy.ops.object.modifier_apply(modifier=mod.name)
obj.data.calc_loop_triangles();obj.name='SM_MeshyBuggy_Review'
bpy.ops.export_scene.fbx(filepath=str(out/(obj.name+'.fbx')),use_selection=True,object_types={'MESH'},axis_forward='-Y',axis_up='Z',bake_anim=False,path_mode='STRIP')
for oldmat in list(bpy.data.materials):
 if oldmat!=mat:bpy.data.materials.remove(oldmat)
for im in list(bpy.data.images):
 if im.users==0:bpy.data.images.remove(im)
for im in bpy.data.images:
 if im.source=='FILE':im.filepath='//'+Path(im.filepath).name
bpy.ops.wm.save_as_mainfile(filepath=str(out/'Buggy_Review.blend'))
report={'source_triangles':initial,'review_triangles':len(obj.data.loop_triangles),'dimensions_m':list(obj.dimensions),'source_sha256':hashes,'textures':maps,'status':'Static visual review only. Wheels joined to body; orientation, pivots, collision, seats and Unreal import pending.','license':'User Meshy screenshot shows CC BY 4.0; credit Meshy.'}
(out/'mesh-report.json').write_text(json.dumps(report,indent=2))
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=12
scene.render.resolution_x=1100;scene.render.resolution_y=800;scene.render.resolution_percentage=100
scene.world=bpy.data.worlds.new('ReviewWorld');scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.35,.35,.35,1)
bpy.ops.object.light_add(type='AREA',location=(1,-3,6));bpy.context.object.data.energy=850;bpy.context.object.data.shape='DISK';bpy.context.object.data.size=5
bpy.ops.object.camera_add(location=(5,-6,3.4));cam=bpy.context.object;cam.rotation_euler=(Vector((0,0,1))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=4.7;scene.camera=cam
scene.render.filepath=str(out/'Buggy_review.png');bpy.ops.render.render(write_still=True)
print(json.dumps(report))
