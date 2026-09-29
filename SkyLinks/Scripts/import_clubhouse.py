"""Import the new clubhouse (Art/Blender/build_clubhouse.py) and place it on the tee island.

Run inside the editor with the Course map open, e.g. from the Output Log in Python mode:

    import sys, unreal; sys.path.append(unreal.Paths.project_dir() + "Scripts")
    import import_clubhouse; import_clubhouse.import_clubhouse()

Replaces /Game/Course/Buildings/SM_Clubhouse (UCX_ boxes become its collision), imports its brick,
roof-tile, paving and asphalt textures and builds its materials here: the 5.8 FBX importer leaves
them as the default checkerboard. Then moves the Clubhouse actor to its spot beside the first tee,
turned so the terrace and practice green face the course, hoists the two club flags (a wind-wave
shader bends them like cloth, cheap enough for phones) and saves the map.
"""
from pathlib import Path

import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
SOURCE = ROOT / 'Art' / 'Exports' / 'SM_Clubhouse.fbx'
TEXTURE_SOURCE = ROOT / 'Art' / 'Exports' / 'ClubhouseTextures'
DEST = '/Game/Course/Buildings'
MAT_DIR = DEST + '/Materials'
TEX_DIR = DEST + '/Textures'
# Same spot as Scripts/build_blockout_course.py: 110 m behind and 45 m left of the first tee, facing the course.
LOCATION = unreal.Vector(-110 * 100.0, -45 * 100.0, 0.0)
YAW = -90.0
# Flagpoles in the clubhouse's Blender frame (metres) and the hoist height: see build_clubhouse.py.
FLAGPOLES = ((17.5, -9.5), (-18.0, -10.0))
FLAG_HOIST = 7.8

# Material slot (Blender material name) -> texture or linear colour, roughness, metallic.
TEXTURED = {'M_CH_Brick': ('T_CH_Brick', 0.9), 'M_CH_RoofTile': ('T_CH_RoofTile', 0.75),
            'M_CH_Paving': ('T_CH_Paving', 0.9), 'M_CH_Asphalt': ('T_CH_Asphalt', 0.95)}
PLAIN = {
    'M_CH_Fascia': ((0.12, 0.06, 0.035), 0.6, 0.0), 'M_CH_WhitePaint': ((0.85, 0.85, 0.83), 0.45, 0.0),
    'M_CH_Glass': ((0.04, 0.06, 0.08), 0.05, 0.5), 'M_CH_Concrete': ((0.45, 0.43, 0.4), 0.9, 0.0),
    'M_CH_PuttingGreen': ((0.06, 0.22, 0.04), 0.7, 0.0), 'M_CH_Fringe': ((0.05, 0.16, 0.03), 0.85, 0.0),
    'M_CH_Cup': ((0.01, 0.01, 0.01), 0.9, 0.0), 'M_CH_FlagRed': ((0.7, 0.03, 0.03), 0.6, 0.0),
    'M_CH_FlagGreen': ((0.02, 0.3, 0.08), 0.6, 0.0), 'M_CH_Hedge': ((0.02, 0.09, 0.02), 0.95, 0.0),
    'M_CH_Soil': ((0.08, 0.05, 0.03), 1.0, 0.0), 'M_CH_Wood': ((0.3, 0.18, 0.09), 0.8, 0.0),
    'M_CH_SignBoard': ((0.02, 0.12, 0.06), 0.5, 0.0), 'M_CH_SignText': ((0.8, 0.62, 0.25), 0.3, 1.0),
    'M_CH_Rope': ((0.8, 0.8, 0.78), 0.8, 0.0), 'M_CH_LinePaint': ((0.9, 0.9, 0.88), 0.6, 0.0),
}

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
lib = unreal.MaterialEditingLibrary


def _task(filename, destination, name, options=None):
    task = unreal.AssetImportTask()
    for key, value in [('filename', str(filename)), ('destination_path', destination), ('destination_name', name),
                       ('automated', True), ('replace_existing', True), ('save', True)]:
        task.set_editor_property(key, value)
    if options:
        task.set_editor_property('options', options)
    tools.import_asset_tasks([task])
    return unreal.load_asset(f'{destination}/{name}')


def _material(name):
    path = f'{MAT_DIR}/{name}'
    mat = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else \
        tools.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    lib.delete_all_material_expressions(mat)
    return mat


def _scalar(mat, value, prop, y):
    node = lib.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, y)
    node.set_editor_property('r', value)
    lib.connect_material_property(node, '', prop)


def build_material(name):
    mat = _material(name)
    if name in TEXTURED:
        texture_name, roughness = TEXTURED[name]
        texture = _task(TEXTURE_SOURCE / f'{texture_name}.png', TEX_DIR, texture_name)
        assert texture, f'{texture_name}.png did not import'
        node = lib.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -500, 0)
        node.set_editor_property('texture', texture)
        lib.connect_material_property(node, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR)
        metallic = 0.0
    else:
        colour, roughness, metallic = PLAIN.get(name, ((0.5, 0.5, 0.5), 0.8, 0.0))
        node = lib.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -500, 0)
        node.set_editor_property('constant', unreal.LinearColor(colour[0], colour[1], colour[2], 1.0))
        lib.connect_material_property(node, '', unreal.MaterialProperty.MP_BASE_COLOR)
    _scalar(mat, roughness, unreal.MaterialProperty.MP_ROUGHNESS, 200)
    if metallic:
        _scalar(mat, metallic, unreal.MaterialProperty.MP_METALLIC, 300)
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


def _expr(mat, cls, x, y, **props):
    node = lib.create_material_expression(mat, cls, x, y)
    for key, value in props.items():
        node.set_editor_property(key, value)
    return node


def _op(mat, cls, a, b, x, y, a_out='', b_out=''):
    node = _expr(mat, cls, x, y)
    lib.connect_material_expressions(a, a_out, node, 'A')
    lib.connect_material_expressions(b, b_out, node, 'B')
    return node


def _wave(mat, time, u, cycles_per_second, cycles_along, amplitude_cm, y):
    """sin(time * cps + u * cycles_along) * u * amplitude: pinned at the pole (u = 0), biggest at the free end."""
    c = lambda v, yy: _expr(mat, unreal.MaterialExpressionConstant, -1500, yy, r=v)  # noqa: E731
    phase = _op(mat, unreal.MaterialExpressionAdd,
                _op(mat, unreal.MaterialExpressionMultiply, time, c(cycles_per_second, y), -1300, y),
                _op(mat, unreal.MaterialExpressionMultiply, u, c(cycles_along, y + 60), -1300, y + 60), -1100, y)
    sine = _expr(mat, unreal.MaterialExpressionSine, -950, y)
    lib.connect_material_expressions(phase, '', sine, '')
    return _op(mat, unreal.MaterialExpressionMultiply, _op(mat, unreal.MaterialExpressionMultiply, sine, u, -800, y),
               c(amplitude_cm, y + 120), -650, y)


def flag_material():
    """Waving cloth for mobile: the flag bends in a travelling wave in the shader (world position offset)."""
    mat = _material('M_CH_ClubFlag')
    mat.set_editor_property('two_sided', True)
    texture = _task(TEXTURE_SOURCE / 'T_CH_ClubFlag.png', TEX_DIR, 'T_CH_ClubFlag')
    sample = _expr(mat, unreal.MaterialExpressionTextureSample, -500, -300, texture=texture)
    lib.connect_material_property(sample, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR)
    _scalar(mat, 0.7, unreal.MaterialProperty.MP_ROUGHNESS, -100)

    coords = _expr(mat, unreal.MaterialExpressionTextureCoordinate, -1700, 200)
    u = _expr(mat, unreal.MaterialExpressionComponentMask, -1550, 200, r=True, g=False, b=False, a=False)
    lib.connect_material_expressions(coords, '', u, '')
    time = _expr(mat, unreal.MaterialExpressionTime, -1700, 350)
    swing = _op(mat, unreal.MaterialExpressionAdd, _wave(mat, time, u, 1.3, 1.4, 26.0, 200),
                _wave(mat, time, u, 2.7, 3.1, 7.0, 500), -500, 300)
    zero = _expr(mat, unreal.MaterialExpressionConstant, -500, 450, r=0.0)
    xy = _op(mat, unreal.MaterialExpressionAppendVector, zero, swing, -350, 350)
    xyz = _op(mat, unreal.MaterialExpressionAppendVector, xy, zero, -200, 350)
    world = _expr(mat, unreal.MaterialExpressionTransform, -50, 350,
                  transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL,
                  transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    lib.connect_material_expressions(xyz, '', world, '')
    lib.connect_material_property(world, '', unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


def hoist_flags(clubhouse):
    options = unreal.FbxImportUI()
    options.set_editor_property('import_mesh', True)
    options.set_editor_property('mesh_type_to_import', unreal.FBXImportType.FBXIT_STATIC_MESH)
    options.set_editor_property('import_materials', False)
    options.set_editor_property('import_textures', False)
    options.static_mesh_import_data.set_editor_property('auto_generate_collision', False)
    flag_mesh = _task(ROOT / 'Art' / 'Exports' / 'SM_ClubFlag.fbx', DEST, 'SM_ClubFlag', options)
    assert isinstance(flag_mesh, unreal.StaticMesh), 'SM_ClubFlag.fbx did not import'
    flag_mesh.set_material(0, flag_material())
    unreal.EditorAssetLibrary.save_loaded_asset(flag_mesh)

    for actor in actors.get_all_level_actors():
        if actor.get_actor_label().startswith('ClubFlag'):
            actors.destroy_actor(actor)
    for index, (px, py) in enumerate(FLAGPOLES, start=1):
        flag = actors.spawn_actor_from_object(flag_mesh, LOCATION, unreal.Rotator(0, 0, YAW))
        flag.set_actor_label(f'ClubFlag{index}')
        flag.set_folder_path('Course/Clubhouse')
        flag.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        flag.attach_to_actor(clubhouse, '', unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD,
                             unreal.AttachmentRule.KEEP_WORLD, False)
        # Blender (x, y, z) m -> the clubhouse's Unreal frame (x, -y, z) cm; hoisted on the pole's +X side.
        flag.set_actor_relative_location(unreal.Vector((px + 0.06) * 100, -py * 100, FLAG_HOIST * 100), False, True)
        flag.set_actor_relative_rotation(unreal.Rotator(0, 0, 0), False, True)
    print(f'CLUBHOUSE flags hoisted: {len(FLAGPOLES)}')


def import_clubhouse():
    options = unreal.FbxImportUI()
    options.set_editor_property('import_mesh', True)
    options.set_editor_property('import_as_skeletal', False)
    options.set_editor_property('mesh_type_to_import', unreal.FBXImportType.FBXIT_STATIC_MESH)
    options.set_editor_property('import_materials', False)
    options.set_editor_property('import_textures', False)
    data = options.static_mesh_import_data
    data.set_editor_property('combine_meshes', True)
    data.set_editor_property('auto_generate_collision', False)  # the UCX_ boxes in the FBX are the collision
    mesh = _task(SOURCE, DEST, 'SM_Clubhouse', options)
    assert isinstance(mesh, unreal.StaticMesh), 'SM_Clubhouse.fbx did not import'

    missing = []
    for index, slot in enumerate(mesh.get_editor_property('static_materials')):
        name = str(slot.get_editor_property('material_slot_name'))
        base = next((k for k in list(TEXTURED) + list(PLAIN) if name == k or name.startswith(k + '_')), None)
        if base is None:
            missing.append(name)
            continue
        mesh.set_material(index, build_material(base))
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    size = mesh.get_bounds().box_extent
    print(f'CLUBHOUSE mesh {size.x * 2 / 100:.0f} x {size.y * 2 / 100:.0f} x {size.z * 2 / 100:.1f} m; '
          f'unmatched material slots: {missing or "none"}')

    clubhouse = next((a for a in actors.get_all_level_actors() if a.get_actor_label() == 'Clubhouse'), None)
    if clubhouse is None:
        clubhouse = actors.spawn_actor_from_object(mesh, LOCATION, unreal.Rotator(0, 0, YAW))
        clubhouse.set_actor_label('Clubhouse')
        clubhouse.set_folder_path('Course/Clubhouse')
    else:
        clubhouse.static_mesh_component.set_static_mesh(mesh)
    clubhouse.set_actor_location_and_rotation(LOCATION, unreal.Rotator(0, 0, YAW), False, True)
    hoist_flags(clubhouse)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print('CLUBHOUSE placed and map saved')
