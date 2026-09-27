"""Adapt the Meshy review mesh to the existing GolfBuggy component dimensions.
Fresh background Blender only. UVs survive bmesh face extraction.
"""
import bpy,bmesh,math,json
from pathlib import Path
from mathutils import Vector
root=Path(__file__).resolve().parents[1]/'BuggyMeshy'
bpy.ops.wm.open_mainfile(filepath=str(root/'Buggy_Review.blend'))
source=next(o for o in bpy.context.scene.objects if o.type=='MESH')
out=root/'GameParts';out.mkdir(exist_ok=True)
# Source faces -X. Wheel centres measured against the source geometry in metres.
centres=[Vector((x,y,.366)) for x in [-1.03,1.21] for y in [-.66,.66]]
def wheel_region(p):
 for i,c in enumerate(centres):
  if p.y*c.y>0 and abs(p.y)>.46 and (p.x-c.x)**2+(p.z-c.z)**2<.38**2:return i
 return -1
def part(name,region):
 obj=source.copy();obj.data=source.data.copy();bpy.context.collection.objects.link(obj);obj.name=name
 bm=bmesh.new();bm.from_mesh(obj.data)
 bmesh.ops.delete(bm,geom=[f for f in bm.faces if (wheel_region(f.calc_center_median())!=region if region>=0 else wheel_region(f.calc_center_median())>=0)],context='FACES')
 bmesh.ops.delete(bm,geom=[v for v in bm.verts if not v.link_faces],context='VERTS')
 bm.to_mesh(obj.data);bm.free()
 for v in obj.data.vertices:
  if region<0:
   z=v.co.z*(.23/.366) if v.co.z<.73 else .73*(.23/.366)+(v.co.z-.73)*.85
   v.co=Vector((-(v.co.x-.09)*(.825/1.12),-v.co.y*(.46/.66),z))
  else:
   p=v.co-centres[region]
   v.co=Vector((-p.x*(.23/.366),-p.y*(.23/.366),p.z*(.23/.366)))
 obj.data.update();obj.data.calc_loop_triangles()
 if region<0:
  glass=bpy.data.materials.new('M_MeshyBuggyGlass');glass.use_nodes=True
  shader=glass.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(.7,.88,.92,1);shader.inputs['Roughness'].default_value=.08;shader.inputs['Transmission Weight'].default_value=1;shader.inputs['IOR'].default_value=1.1
  obj.data.materials.append(glass)
  glass_faces=0
  for face in obj.data.polygons:
   c=face.center
   if c.x>.50 and .74<c.z<1.49 and abs(c.y)<.46 and abs(face.normal.x)>.65:
    face.material_index=1;glass_faces+=1
  assert glass_faces>20,glass_faces
  print('WINDSHIELD_FACES',glass_faces)
 bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
 bpy.ops.export_scene.fbx(filepath=str(out/(name+'.fbx')),use_selection=True,object_types={'MESH'},apply_scale_options='FBX_SCALE_UNITS',axis_forward='-Y',axis_up='Z',bake_anim=False,path_mode='STRIP')
 return obj
body=part('SM_Buggy_Body',-1)
# Choose source +Y wheel so its outward hub points -Y after conversion.
wheel=part('SM_Buggy_Wheel',3)
source.hide_render=True;source.hide_viewport=True
wheel.hide_render=True
for x in [-.825,.825]:
 for y in [-.46,.46]:
  w=wheel.copy();w.data=wheel.data;bpy.context.collection.objects.link(w);w.hide_render=False;w.location=(x,y,.23)
  if y>0:w.rotation_euler.z=math.pi
body.data.calc_loop_triangles();wheel.data.calc_loop_triangles()
assert len(wheel.data.loop_triangles)>500
report={'body_triangles':len(body.data.loop_triangles),'wheel_triangles':len(wheel.data.loop_triangles),'assembled_triangles':len(body.data.loop_triangles)+4*len(wheel.data.loop_triangles),'wheelbase_cm':165,'track_cm':92,'wheel_radius_cm':23,'method':'UV-preserving spatial extraction from fused source; repeated rear wheel, source art unchanged.'}
(out/'parts-report.json').write_text(json.dumps(report,indent=2))
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=12;scene.render.resolution_x=1000;scene.render.resolution_y=800;scene.render.resolution_percentage=100
scene.world=bpy.data.worlds.new('World');scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.35,.35,.35,1)
bpy.ops.object.light_add(type='AREA',location=(2,-3,5));bpy.context.object.data.energy=700;bpy.context.object.data.size=5
bpy.ops.object.camera_add(location=(5,-6,3));cam=bpy.context.object;cam.rotation_euler=(Vector((0,0,.8))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=3.7;scene.camera=cam
scene.render.filepath=str(out/'assembled.png');bpy.ops.render.render(write_still=True)
print(report)
