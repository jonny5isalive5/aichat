"""Replace the two runtime meshes after importing textures and building M_MeshyBuggy.
No map changes. Previous meshes are recoverable from Git commit 8164e62.
"""
import unreal
from pathlib import Path
src=Path(unreal.Paths.project_dir())/'Art/BuggyMeshy/GameParts'
lib=unreal.EditorAssetLibrary
pm=unreal.load_asset('/Game/Course/Materials/PM_Rough')
mat=unreal.load_asset('/Game/Generated_Materials/M_MeshyBuggy')
glass=unreal.load_asset('/Game/Generated_Materials/M_MeshyBuggyGlass')
assert pm and mat and glass
mat.modify();mat.set_editor_property('PhysMaterial',pm);lib.save_loaded_asset(mat)
glass.modify();glass.set_editor_property('PhysMaterial',pm);lib.save_loaded_asset(glass)
editor=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
for name in ['SM_Buggy_Body','SM_Buggy_Wheel']:
 options=unreal.FbxImportUI()
 options.set_editor_property('import_materials',False)
 options.set_editor_property('import_textures',False)
 options.set_editor_property('import_as_skeletal',False)
 options.set_editor_property('mesh_type_to_import',unreal.FBXImportType.FBXIT_STATIC_MESH)
 options.static_mesh_import_data.set_editor_property('combine_meshes',True)
 options.static_mesh_import_data.set_editor_property('auto_generate_collision',False)
 task=unreal.AssetImportTask()
 for k,v in [('filename',str(src/(name+'.fbx'))),('destination_path','/Game/Vehicles/Buggy'),('destination_name',name),('automated',True),('replace_existing',True),('save',True),('options',options)]:task.set_editor_property(k,v)
 unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
 mesh=unreal.load_asset('/Game/Vehicles/Buggy/'+name);assert mesh
 mesh.modify()
 glass_slots=0
 for index,slot in enumerate(mesh.static_materials):
  is_glass='Glass' in str(slot.material_slot_name)
  mesh.set_material(index,glass if is_glass else mat)
  if is_glass:glass_slots+=1
 if name=='SM_Buggy_Body':assert glass_slots==1,[(str(s.material_slot_name)) for s in mesh.static_materials]
 body=mesh.get_editor_property('BodySetup');body.modify();body.set_editor_property('PhysMaterial',pm)
 # Driving actor retains its existing box collision; add simple collision for static uses.
 editor.remove_collisions(mesh)
 editor.add_simple_collisions(mesh,unreal.ScriptCollisionShapeType.BOX)
 opts=unreal.StaticMeshReductionOptions();opts.set_editor_property('auto_compute_lod_screen_size',True)
 settings=[]
 for pct in [1.0,.5,.2]:
  setting=unreal.StaticMeshReductionSettings();setting.set_editor_property('percent_triangles',pct);settings.append(setting)
 opts.set_editor_property('reduction_settings',settings);editor.set_lods(mesh,opts)
 lib.save_loaded_asset(mesh)
 bounds=mesh.get_bounds()
 assert bounds.box_extent.x>10 and bounds.box_extent.x<200,(name,bounds)
 print('INSTALLED',name,'bounds',bounds,'LODs',mesh.get_num_lods(),'material',mesh.get_material(0).get_path_name(),'physical',body.get_editor_property('PhysMaterial').get_path_name())
print('Runtime buggy meshes replaced; Course not modified or saved.')
