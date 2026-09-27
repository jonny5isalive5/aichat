import unreal
pm=unreal.load_asset('/Game/Course/Materials/PM_Rough')
mesh=unreal.load_asset('/Game/Course/Vegetation/SmallTree/SM_SmallTree')
assert pm and mesh
mesh.modify()
for i,part in enumerate(['Branch','Leaf','Trunk']):
    mat=unreal.load_asset('/Game/Generated_Materials/M_SkyLinksTree'+part)
    assert mat
    mat.modify()
    mat.set_editor_property('PhysMaterial',pm)
    if part=='Leaf':mat.set_editor_property('OpacityMaskClipValue',.4)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    mesh.set_material(i,mat)
body=mesh.get_editor_property('BodySetup')
body.modify()
body.set_editor_property('PhysMaterial',pm)
body.set_editor_property('CollisionTraceFlag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
opts=unreal.StaticMeshReductionOptions()
opts.set_editor_property('auto_compute_lod_screen_size',True)
settings=[]
for pct in [1.0,.4,.12]:
    entry=unreal.StaticMeshReductionSettings()
    entry.set_editor_property('percent_triangles',pct)
    settings.append(entry)
opts.set_editor_property('reduction_settings',settings)
unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).set_lods(mesh,opts)
unreal.EditorAssetLibrary.save_loaded_asset(mesh)
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
assert world.get_path_name()=='/Game/Maps/Course.Course'
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assert not any(a.get_actor_label()=='ArtReview_SmallTree' for a in actors.get_all_level_actors())
hit=unreal.SystemLibrary.line_trace_single_for_objects(world,unreal.Vector(2500,-2500,2000),unreal.Vector(2500,-2500,-2000),[unreal.ObjectTypeQuery.ECC_WORLD_STATIC],True,[],unreal.DrawDebugTrace.NONE)
assert hit
z=hit.to_tuple()[5].z
tree=actors.spawn_actor_from_object(mesh,unreal.Vector(2500,-2500,z),unreal.Rotator(0,35,0))
tree.modify()
tree.set_actor_label('ArtReview_SmallTree')
tree.set_folder_path('Course/ArtReview')
tree.set_actor_scale3d(unreal.Vector(2.4,2.4,2.4))
tree.static_mesh_component.modify()
tree.static_mesh_component.set_collision_profile_name('BlockAll')
tree.static_mesh_component.set_phys_material_override(pm)
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
print('Tree review actor',tree.get_path_name(),'ground',z,'bounds',tree.get_actor_bounds(False),'LODs',mesh.get_num_lods())

