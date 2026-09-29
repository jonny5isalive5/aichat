"""Import reviewed tree FBX + 10 textures into /Game/Course/Vegetation/SmallTree.
No material graph work here (main agent handles materials via create_edit_material).
Does not touch any course actors or maps."""
from pathlib import Path
import unreal

DEST = '/Game/Course/Vegetation/SmallTree'
SOURCE = Path(unreal.Paths.project_dir()) / 'Art' / 'Vegetation'
TEX_DIR = SOURCE / 'Textures'
FBX = SOURCE / 'SM_SmallTree.fbx'
PM_PATH = '/Game/Course/Materials/PM_Rough'

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
lib = unreal.EditorAssetLibrary

assert FBX.exists(), f'Missing FBX: {FBX}'
assert TEX_DIR.is_dir(), f'Missing texture dir: {TEX_DIR}'

pm = unreal.load_asset(PM_PATH)
assert pm, f'PM_Rough is required: {PM_PATH}'

lib.make_directory(DEST)

# --- Import textures --------------------------------------------------------
tex_files = sorted([p for p in TEX_DIR.iterdir()
                    if p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.tga', '.bmp', '.exr'}])
tex_tasks = []
for p in tex_files:
    t = unreal.AssetImportTask()
    t.set_editor_property('filename', str(p))
    t.set_editor_property('destination_path', DEST)
    t.set_editor_property('destination_name', p.stem)
    t.set_editor_property('automated', True)
    t.set_editor_property('replace_existing', True)
    t.set_editor_property('save', True)
    tex_tasks.append(t)
if tex_tasks:
    asset_tools.import_asset_tasks(tex_tasks)

# Apply texture settings (normal maps + masks sRGB off, true masks compression)
imported_textures = []
for p in tex_files:
    obj_path = f'{DEST}/{p.stem}'
    tex = lib.load_asset(obj_path)
    if not tex:
        raise RuntimeError(f'Texture failed to import: {obj_path}')
    stem = p.stem.lower()
    if '_normal' in stem:
        tex.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP)
        tex.set_editor_property('srgb', False)
    elif '_rough' in stem or '_alpha' in stem:
        tex.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_MASKS)
        tex.set_editor_property('srgb', False)
    else:  # base color
        tex.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_DEFAULT)
        tex.set_editor_property('srgb', True)
    lib.save_loaded_asset(tex)
    imported_textures.append(tex.get_path_name())

# --- Import FBX -------------------------------------------------------------
options = unreal.FbxImportUI()
options.set_editor_property('import_materials', False)
options.set_editor_property('import_textures', False)
options.set_editor_property('import_as_skeletal', False)
options.set_editor_property('mesh_type_to_import', unreal.FBXImportType.FBXIT_STATIC_MESH)
options.static_mesh_import_data.set_editor_property('combine_meshes', True)
options.static_mesh_import_data.set_editor_property('auto_generate_collision', False)

mesh_task = unreal.AssetImportTask()
mesh_task.set_editor_property('filename', str(FBX))
mesh_task.set_editor_property('destination_path', DEST)
mesh_task.set_editor_property('destination_name', 'SM_SmallTree')
mesh_task.set_editor_property('automated', True)
mesh_task.set_editor_property('replace_existing', True)
mesh_task.set_editor_property('save', True)
mesh_task.set_editor_property('options', options)
asset_tools.import_asset_tasks([mesh_task])

mesh = lib.load_asset(f'{DEST}/SM_SmallTree')
assert mesh, 'FBX failed to import'

# --- Three LODs (best effort) ----------------------------------------------
lod_result = 'not applied'
try:
    reductions = unreal.StaticMeshReductionOptions()
    reductions.set_editor_property('auto_compute_lod_screen_size', True)
    settings = []
    for pct in [1.0, 0.4, 0.12]:
        s = unreal.StaticMeshReductionSettings()
        s.set_editor_property('percent_triangles', pct)
        s.set_editor_property('screen_size', 0.0)
        settings.append(s)
    reductions.set_editor_property('reduction_settings', settings)
    mesh.modify()
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    edited = editor.set_lods(mesh, reductions)
    lod_result = f'set_lods returned {edited}, total_lods={mesh.get_num_lods()}'
except Exception as e:
    lod_result = f'LODs unsupported/failed: {e}'
    unreal.log_warning(lod_result)

# --- Physical material on mesh body ----------------------------------------
body = mesh.get_editor_property('body_setup')
if body:
    body.modify()
    body.set_editor_property('phys_material', pm)
    applied = body.get_editor_property('phys_material')
    assert applied == pm, 'Failed to set body physical material'
else:
    unreal.log_warning('StaticMesh has no BodySetup; skipped physical material')

lib.save_loaded_asset(mesh)

print('=== TREE IMPORT COMPLETE ===')
print('Mesh:', mesh.get_path_name(), '| total_lods:', mesh.get_num_lods(), '|', lod_result)
print('Textures imported:', len(imported_textures))
for t in imported_textures:
    print('  ', t)
print('BodyPhysMaterial:', pm.get_path_name(), '->', 'set' if body else 'no body setup')
print('Material slots on mesh:', mesh.get_num_sections(0))
