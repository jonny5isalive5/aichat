"""Import the new clubhouse (Art/Blender/build_clubhouse.py) and place it on the tee island.

Run inside the editor with the Course map open, e.g. from the Output Log in Python mode:

    import sys, unreal; sys.path.append(unreal.Paths.project_dir() + "Scripts")
    import import_clubhouse; import_clubhouse.import_clubhouse()

Replaces /Game/Course/Buildings/SM_Clubhouse (brick, roof-tile, paving and asphalt textures come in with it,
UCX_ boxes become its collision) and moves the Clubhouse actor to its spot beside the first tee, turned so
the balcony and practice green face the course. Saves the map.
"""
from pathlib import Path

import unreal

SOURCE = Path(unreal.Paths.project_dir()).resolve() / 'Art' / 'Exports' / 'SM_Clubhouse.fbx'
DEST = '/Game/Course/Buildings'
# Same spot as Scripts/build_blockout_course.py: 110 m behind and 45 m left of the first tee, entrance to the course.
LOCATION = unreal.Vector(-110 * 100.0, -45 * 100.0, 0.0)
YAW = -90.0

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def import_clubhouse():
    options = unreal.FbxImportUI()
    options.set_editor_property('import_mesh', True)
    options.set_editor_property('import_as_skeletal', False)
    options.set_editor_property('mesh_type_to_import', unreal.FBXImportType.FBXIT_STATIC_MESH)
    options.set_editor_property('import_materials', True)
    options.set_editor_property('import_textures', True)
    data = options.static_mesh_import_data
    data.set_editor_property('combine_meshes', True)
    data.set_editor_property('auto_generate_collision', False)  # the UCX_ boxes in the FBX are the collision

    task = unreal.AssetImportTask()
    for key, value in [('filename', str(SOURCE)), ('destination_path', DEST), ('destination_name', 'SM_Clubhouse'),
                       ('automated', True), ('replace_existing', True), ('save', True), ('options', options)]:
        task.set_editor_property(key, value)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    mesh = unreal.load_asset(f'{DEST}/SM_Clubhouse')
    assert isinstance(mesh, unreal.StaticMesh), 'SM_Clubhouse.fbx did not import'
    size = mesh.get_bounds().box_extent
    print(f'CLUBHOUSE mesh {size.x * 2 / 100:.0f} x {size.y * 2 / 100:.0f} x {size.z * 2 / 100:.1f} m, '
          f'{len(mesh.get_editor_property("static_materials"))} materials')

    clubhouse = next((a for a in actors.get_all_level_actors() if a.get_actor_label() == 'Clubhouse'), None)
    if clubhouse is None:
        clubhouse = actors.spawn_actor_from_object(mesh, LOCATION, unreal.Rotator(0, 0, YAW))
        clubhouse.set_actor_label('Clubhouse')
        clubhouse.set_folder_path('Course/Clubhouse')
    else:
        clubhouse.static_mesh_component.set_static_mesh(mesh)
    clubhouse.set_actor_location_and_rotation(LOCATION, unreal.Rotator(0, 0, YAW), False, True)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print('CLUBHOUSE placed and map saved')
