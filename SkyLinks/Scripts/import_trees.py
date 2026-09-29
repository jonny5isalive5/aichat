"""Import the stylised Sky Links trees (Art/Blender/build_trees.py) and make foliage brushes for them.

Run in the editor, Output Log in Python mode:

    import sys, unreal; sys.path.append(unreal.Paths.project_dir() + "Scripts")
    import import_trees; import_trees.import_trees()

- Imports Art/Exports/Trees/SM_*.fbx to /Game/Course/Trees (UCX_ trunk boxes become their collision)
- Builds M_Tree_Bark and M_Tree_Leaves: vertex colours for colour, a detail texture, and a cheap wind sway in
  the shader; trees stand still (no wind), each tree instance gets its own leaf shade
- Builds M_Tree_Vines (Art/Textures/T_Vines.png, masked and two-sided) for the islands' hanging ivy
- Adds two lower LODs to each tree
- Creates instanced-static-mesh foliage types in /Game/Course/Foliage (FT_Oak_A, FT_Oak_B, FT_Poplar, FT_Pine,
  FT_Birch, FT_Bush_Round, FT_Bush_Flowering). In Foliage Mode tick several at once to paint a mixed wood.

    import_trees.remove_megaplants()   deletes every Megaplant tree placed in the level (painted or scripted)
"""
from pathlib import Path

import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
SOURCE = ROOT / 'Art' / 'Exports' / 'Trees'
DEST = '/Game/Course/Trees'
FOLIAGE = '/Game/Course/Foliage'
DETAIL = '/Game/Course/Islands/Textures'  # detail textures made by apply_floating_islands.py

# name: (density per 10 x 10 m, spacing radius cm, scale min, scale max, max slope degrees)
BRUSHES = {
    'Oak_A': (0.25, 500.0, 0.8, 1.2, 25.0), 'Oak_B': (0.25, 500.0, 0.8, 1.2, 25.0),
    'Poplar': (0.2, 300.0, 0.85, 1.15, 20.0), 'Pine': (0.3, 350.0, 0.75, 1.25, 30.0),
    'Birch': (0.3, 300.0, 0.8, 1.2, 25.0),
    'Bush_Round': (1.5, 120.0, 0.7, 1.3, 35.0), 'Bush_Flowering': (1.0, 120.0, 0.7, 1.2, 35.0),
}

tools = unreal.AssetToolsHelpers.get_asset_tools()
lib = unreal.MaterialEditingLibrary
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _material(name):
    path = f'{DEST}/{name}'
    mat = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else \
        tools.create_asset(name, DEST, unreal.Material, unreal.MaterialFactoryNew())
    lib.delete_all_material_expressions(mat)
    return mat


def _expr(mat, cls, x, y, **props):
    node = lib.create_material_expression(mat, cls, x, y)
    for key, value in props.items():
        node.set_editor_property(key, value)
    return node


def _const(mat, value, x, y):
    return _expr(mat, unreal.MaterialExpressionConstant, x, y, r=value)


def _op(mat, cls, a, b, x, y, a_out='', b_out=''):
    node = _expr(mat, cls, x, y)
    lib.connect_material_expressions(a, a_out, node, 'A')
    lib.connect_material_expressions(b, b_out, node, 'B')
    return node


def _mask(mat, source, channel, x, y):
    node = _expr(mat, unreal.MaterialExpressionComponentMask, x, y,
                 r=channel == 'R', g=channel == 'G', b=channel == 'B', a=False)
    lib.connect_material_expressions(source, '', node, '')
    return node


def _sine(mat, source, x, y):
    node = _expr(mat, unreal.MaterialExpressionSine, x, y)
    lib.connect_material_expressions(source, '', node, '')
    return node


def _import_vine_texture():
    task = unreal.AssetImportTask()
    for key, value in [('filename', str(ROOT / 'Art' / 'Textures' / 'T_Vines.png')), ('destination_path', DEST),
                       ('automated', True), ('replace_existing', True), ('save', True)]:
        task.set_editor_property(key, value)
    tools.import_asset_tasks([task])
    texture = unreal.load_asset(f'{DEST}/T_Vines')
    assert texture, 'Art/Textures/T_Vines.png did not import'
    texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_DEFAULT)
    unreal.EditorAssetLibrary.save_loaded_asset(texture)
    return texture


def tree_material(name, detail, roughness, wind_cm, tint=False, card=None):
    """Vertex colour (sRGB bytes, squared) x detail texture; world position offset sway scaled by vertex alpha.

    tint: each instance gets its own shade (PerInstanceRandom), so a wood of one tree kind isn't all one green.
    card: a colour + alpha texture instead of the detail texture (masked, two-sided): the hanging ivy cards."""
    mat = _material(name)
    vc = _expr(mat, unreal.MaterialExpressionVertexColor, -1600, 0)
    if card:
        texture = _expr(mat, unreal.MaterialExpressionTextureSample, -1300, 150, texture=card)
        colour = _op(mat, unreal.MaterialExpressionMultiply, _op(mat, unreal.MaterialExpressionMultiply, vc, vc, -1300, 0),
                     texture, -1000, 50, b_out='RGB')
        lib.connect_material_property(texture, 'A', unreal.MaterialProperty.MP_OPACITY_MASK)
        mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
        mat.set_editor_property('two_sided', True)
    else:
        texture = _expr(mat, unreal.MaterialExpressionTextureSample, -1300, 150,
                        texture=unreal.load_asset(f'{DETAIL}/{detail}'),
                        sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)
        colour = _op(mat, unreal.MaterialExpressionMultiply, _op(mat, unreal.MaterialExpressionMultiply, vc, vc, -1300, 0),
                     texture, -1000, 50, b_out='R')
    if tint:
        # From a cool deep green to a warm yellow-green per instance.
        shade = _expr(mat, unreal.MaterialExpressionLinearInterpolate, -1000, -200)
        lib.connect_material_expressions(_expr(mat, unreal.MaterialExpressionConstant3Vector, -1300, -300,
                                               constant=unreal.LinearColor(0.72, 0.82, 0.78, 1)), '', shade, 'A')
        lib.connect_material_expressions(_expr(mat, unreal.MaterialExpressionConstant3Vector, -1300, -200,
                                               constant=unreal.LinearColor(1.3, 1.18, 0.7, 1)), '', shade, 'B')
        lib.connect_material_expressions(_expr(mat, unreal.MaterialExpressionPerInstanceRandom, -1300, -100), '', shade, 'Alpha')
        colour = _op(mat, unreal.MaterialExpressionMultiply, colour, shade, -800, 0)
    lib.connect_material_property(colour, '', unreal.MaterialProperty.MP_BASE_COLOR)
    lib.connect_material_property(_const(mat, roughness, -1000, 250), '', unreal.MaterialProperty.MP_ROUGHNESS)

    if wind_cm <= 0:
        # Still: no world position offset at all (moving trees read as bouncing).
        lib.recompile_material(mat)
        unreal.EditorAssetLibrary.save_loaded_asset(mat)
        return mat
    # Wind: a slow sway whose phase drifts across the island (neighbours don't move in lock-step) plus a flutter.
    world = _expr(mat, unreal.MaterialExpressionWorldPosition, -1600, 500)
    time = _expr(mat, unreal.MaterialExpressionTime, -1600, 650)
    spread = _op(mat, unreal.MaterialExpressionMultiply,
                 _op(mat, unreal.MaterialExpressionAdd, _mask(mat, world, 'R', -1450, 450), _mask(mat, world, 'G', -1450, 550), -1300, 500),
                 _const(mat, 0.003, -1300, 600), -1150, 500)
    phase = _op(mat, unreal.MaterialExpressionAdd, spread,
                _op(mat, unreal.MaterialExpressionMultiply, time, _const(mat, 0.35, -1450, 700), -1300, 700), -1000, 550)
    weight = _op(mat, unreal.MaterialExpressionMultiply, vc, _const(mat, wind_cm, -1450, 850), -1150, 850, a_out='A')
    sway_x = _op(mat, unreal.MaterialExpressionMultiply, _sine(mat, phase, -850, 500), weight, -700, 500)
    sway_y = _op(mat, unreal.MaterialExpressionMultiply,
                 _sine(mat, _op(mat, unreal.MaterialExpressionAdd, phase, _const(mat, 0.27, -1000, 700), -850, 650), -700, 650),
                 _op(mat, unreal.MaterialExpressionMultiply, weight, _const(mat, 0.6, -850, 800), -700, 800), -550, 650)
    flutter = _op(mat, unreal.MaterialExpressionMultiply,
                  _sine(mat, _op(mat, unreal.MaterialExpressionMultiply, time, _const(mat, 2.3, -1000, 950), -850, 950), -700, 950),
                  _op(mat, unreal.MaterialExpressionMultiply, weight, _const(mat, 0.0, -850, 1050), -700, 1050), -550, 950)
    xy = _op(mat, unreal.MaterialExpressionAppendVector, sway_x, sway_y, -400, 600)
    xyz = _op(mat, unreal.MaterialExpressionAppendVector, xy, flutter, -250, 700)
    lib.connect_material_property(xyz, '', unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


def _import_mesh(path):
    options = unreal.FbxImportUI()
    options.set_editor_property('import_mesh', True)
    options.set_editor_property('import_as_skeletal', False)
    options.set_editor_property('mesh_type_to_import', unreal.FBXImportType.FBXIT_STATIC_MESH)
    options.set_editor_property('import_materials', False)
    options.set_editor_property('import_textures', False)
    data = options.static_mesh_import_data
    data.set_editor_property('combine_meshes', True)
    data.set_editor_property('auto_generate_collision', False)
    data.set_editor_property('vertex_color_import_option', unreal.VertexColorImportOption.REPLACE)
    task = unreal.AssetImportTask()
    for key, value in [('filename', str(path)), ('destination_path', DEST), ('destination_name', path.stem),
                       ('automated', True), ('replace_existing', True), ('save', True), ('options', options)]:
        task.set_editor_property(key, value)
    tools.import_asset_tasks([task])
    mesh = unreal.load_asset(f'{DEST}/{path.stem}')
    assert isinstance(mesh, unreal.StaticMesh), f'{path.name} did not import'
    return mesh


def _add_lods(mesh):
    try:
        options = unreal.EditorScriptingMeshReductionOptions()
        options.set_editor_property('auto_compute_lod_screen_size', False)
        options.set_editor_property('reduction_settings', [
            unreal.EditorScriptingMeshReductionSettings(1.0, 1.0),
            unreal.EditorScriptingMeshReductionSettings(0.45, 0.3),
            unreal.EditorScriptingMeshReductionSettings(0.15, 0.1)])
        unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).set_lods(mesh, options)
    except Exception as error:
        print(f'TREES note: LODs not added to {mesh.get_name()}: {error}')


def _foliage(short, mesh):
    density, radius, smin, smax, slope = BRUSHES[short]
    name = f'FT_{short}'
    path = f'{FOLIAGE}/{name}'
    foliage = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else \
        tools.create_asset(name, FOLIAGE, unreal.FoliageType_InstancedStaticMesh, None)
    for key, value in [('mesh', mesh), ('density', density), ('radius', radius),
                       ('scaling', unreal.FoliageScaling.UNIFORM), ('scale_x', unreal.FloatInterval(smin, smax)),
                       ('random_yaw', True), ('align_to_normal', False),
                       ('ground_slope_angle', unreal.FloatInterval(0.0, slope)), ('z_offset', unreal.FloatInterval(-8.0, -3.0))]:
        try:
            foliage.set_editor_property(key, value)
        except Exception as error:
            print(f'TREES note: {name}.{key}: {error}')
    unreal.EditorAssetLibrary.save_loaded_asset(foliage)
    return path


def import_trees():
    bark = tree_material('M_Tree_Bark', 'T_RockDetail', 0.9, 0.0)
    leaves = tree_material('M_Tree_Leaves', 'T_GrassDetail', 0.75, 0.0, tint=True)
    tree_material('M_Tree_Vines', None, 0.8, 18.0, card=_import_vine_texture())  # the islands' hanging ivy, a gentle sway
    made = []
    for fbx in sorted(SOURCE.glob('SM_*.fbx')):
        mesh = _import_mesh(fbx)
        for index, slot in enumerate(mesh.get_editor_property('static_materials')):
            slot_name = str(slot.get_editor_property('material_slot_name'))
            mesh.set_material(index, leaves if slot_name.startswith('TreeLeaves') else bark)
        _add_lods(mesh)
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
        short = fbx.stem.replace('SM_Tree_', '').replace('SM_', '')
        made.append(_foliage(short, mesh))
    print(f'TREES imported {len(made)}: ' + ', '.join(p.split('/')[-1] for p in made))


def remove_megaplants():
    """Delete the heavy Megaplant trees: painted SkyLinksTree/Bush actors and ones placed by place_island_trees."""
    doomed = []
    for actor in actors.get_all_level_actors():
        cls = actor.get_class().get_name()
        if cls in ('SkyLinksTree', 'SkyLinksBush'):
            doomed.append(actor)
        elif isinstance(actor, unreal.SkeletalMeshActor) and actor.get_actor_label().startswith('IslandTree'):
            doomed.append(actor)
    for actor in doomed:
        actors.destroy_actor(actor)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print(f'TREES removed {len(doomed)} Megaplant trees; map saved')
