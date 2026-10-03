"""Import the buggy's driver door (Art/BuggyMeshy/GameParts/SM_Buggy_Door.fbx, from Art/Blender/build_buggy_door.py) to
/Game/Vehicles/Buggy/SM_Buggy_Door with a cream paint and a black trim material. AGolfBuggy loads it by that path.
Run in the editor: import import_buggy_door as door; door.import_buggy_door() (importlib.reload first after changes)."""
import unreal
from pathlib import Path

DEST = '/Game/Vehicles/Buggy'
SOURCE = Path(unreal.Paths.project_dir()) / 'Art' / 'BuggyMeshy' / 'GameParts' / 'SM_Buggy_Door.fbx'
MATERIALS = (('M_BuggyDoorPaint', (0.62, 0.58, 0.46)), ('M_BuggyDoorTrim', (0.012, 0.012, 0.012)))


def _material(name, colour, roughness):
    path = f'{DEST}/{name}'
    mat = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else \
        unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, DEST, unreal.Material, unreal.MaterialFactoryNew())
    lib = unreal.MaterialEditingLibrary
    lib.delete_all_material_expressions(mat)
    base = lib.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -400, 0)
    base.set_editor_property('constant', unreal.LinearColor(*colour, 1.0))
    rough = lib.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 200)
    rough.set_editor_property('r', roughness)
    lib.connect_material_property(base, '', unreal.MaterialProperty.MP_BASE_COLOR)
    lib.connect_material_property(rough, '', unreal.MaterialProperty.MP_ROUGHNESS)
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


def import_buggy_door():
    assert SOURCE.is_file(), f'{SOURCE} missing: run Art/Blender/build_buggy_door.py'
    paint, trim = (_material(name, colour, 0.45) for name, colour in MATERIALS)
    options = unreal.FbxImportUI()
    options.set_editor_property('import_mesh', True)
    options.set_editor_property('import_as_skeletal', False)
    options.set_editor_property('import_materials', False)
    options.set_editor_property('import_textures', False)
    data = options.static_mesh_import_data
    data.set_editor_property('combine_meshes', True)
    data.set_editor_property('auto_generate_collision', False)
    task = unreal.AssetImportTask()
    for key, value in (('filename', str(SOURCE)), ('destination_path', DEST), ('destination_name', 'SM_Buggy_Door'),
                       ('automated', True), ('replace_existing', True), ('save', True), ('options', options)):
        task.set_editor_property(key, value)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    mesh = unreal.load_asset(f'{DEST}/SM_Buggy_Door')
    assert isinstance(mesh, unreal.StaticMesh), 'SM_Buggy_Door did not import'
    for index, _ in enumerate(mesh.get_editor_property('static_materials')):
        mesh.set_material(index, paint if index == 0 else trim)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    print('BUGGY DOOR: SM_Buggy_Door imported with paint and trim materials')
