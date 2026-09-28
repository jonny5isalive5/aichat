"""Put a hole's floating islands into the Course map (run inside the editor, e.g. through Aura).

    apply_islands(1)      import the Blender islands for hole 1, build their materials, remove the flat
                          landscape and slabs of that hole, place the islands and re-seat the cup,
                          trees, tee markers, clubhouse and player start on the new ground
    validate_islands(1)   run in a LATER tool call (collision cooks after the import): traces the
                          tee, fairway, green, bunkers and the gaps and prints what the ball would find

Sources come from Art/Blender/build_floating_islands.py:
  Art/Exports/Islands/SM_H01_IslandTop.fbx, SM_H01_IslandRock.fbx, SM_H01_Floaters.fbx, Hole01_spots.json
  Art/Textures/T_GrassDetail.png, T_SandDetail.png, T_RockDetail.png

Re-running replaces the meshes and materials and re-places everything; it is safe to run twice.
"""
import json
from pathlib import Path

import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
SOURCE = ROOT / 'Art' / 'Exports' / 'Islands'
TEXTURE_SOURCE = ROOT / 'Art' / 'Textures'
DEST = '/Game/Course/Islands'
TEXTURE_DEST = DEST + '/Textures'
MAT_DIR = '/Game/Course/Materials'
MAP_PATH = '/Game/Maps/Course'
M = 100.0

# Slot name in the FBX -> (Unreal material, base colour (linear), roughness, colour variation, mowing stripes,
# detail texture, physical material). Colour variation and stripes come from the vertex colours (R, G).
GRASS = {
    'Rough':   ('M_Island_Rough',   (0.045, 0.12, 0.02),  0.95, 0.5,  0.0,  'T_GrassDetail', 'PM_Rough'),
    'Fairway': ('M_Island_Fairway', (0.07, 0.2, 0.03),    0.9,  0.25, 0.14, 'T_GrassDetail', 'PM_Fairway'),
    'Green':   ('M_Island_Green',   (0.08, 0.25, 0.035),  0.85, 0.12, 0.0,  'T_GrassDetail', 'PM_Green'),
    'TeeBox':  ('M_Island_TeeBox',  (0.075, 0.21, 0.032), 0.9,  0.1,  0.0,  'T_GrassDetail', 'PM_Fairway'),
    'Bunker':  ('M_Island_Bunker',  (0.42, 0.33, 0.2),    1.0,  0.15, 0.0,  'T_SandDetail',  'PM_Bunker'),
}
ROCK = ('M_Island_Rock', 'T_RockDetail', 'PM_Rough')
SEA = 'M_Island_Sea'

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
lib = unreal.MaterialEditingLibrary


def _import(filename, destination, options=None):
    task = unreal.AssetImportTask()
    for key, value in [('filename', str(filename)), ('destination_path', destination), ('automated', True),
                       ('replace_existing', True), ('save', True)]:
        task.set_editor_property(key, value)
    if options:
        task.set_editor_property('options', options)
    tools.import_asset_tasks([task])
    return unreal.load_asset(f'{destination}/{Path(filename).stem}')


def import_textures():
    textures = {}
    for name in ('T_GrassDetail', 'T_SandDetail', 'T_RockDetail'):
        texture = _import(TEXTURE_SOURCE / f'{name}.png', TEXTURE_DEST)
        assert texture, f'{name}.png did not import'
        texture.set_editor_property('srgb', False)  # a brightness multiplier, not a colour
        texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_GRAYSCALE)
        unreal.EditorAssetLibrary.save_loaded_asset(texture)
        textures[name] = texture
    return textures


def _material(name):
    path = f'{MAT_DIR}/{name}'
    mat = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else \
        tools.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    lib.delete_all_material_expressions(mat)
    return mat


def _expr(mat, cls, x, y, **props):
    node = lib.create_material_expression(mat, cls, x, y)
    for key, value in props.items():
        node.set_editor_property(key, value)
    return node


def _const(mat, value, x, y):
    return _expr(mat, unreal.MaterialExpressionConstant, x, y, r=value)


def _mul(mat, a, a_out, b, b_out, x, y):
    node = _expr(mat, unreal.MaterialExpressionMultiply, x, y)
    lib.connect_material_expressions(a, a_out, node, 'A')
    lib.connect_material_expressions(b, b_out, node, 'B')
    return node


def _add(mat, a, b, x, y):
    node = _expr(mat, unreal.MaterialExpressionAdd, x, y)
    lib.connect_material_expressions(a, '', node, 'A')
    lib.connect_material_expressions(b, '', node, 'B')
    return node


def _finish(mat, physical):
    mat.set_editor_property('phys_material', unreal.load_asset(f'{MAT_DIR}/{physical}'))
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


def grass_material(name, colour, roughness, variation, stripes, detail, physical):
    """colour * (R * variation + 1 - variation / 2) * (1 - G * stripes) * detail texture."""
    mat = _material(name)
    vc = _expr(mat, unreal.MaterialExpressionVertexColor, -1200, 0)
    shade = _add(mat, _mul(mat, vc, 'R', _const(mat, variation, -1200, 200), '', -1000, 100),
                 _const(mat, 1 - variation * 0.5, -1000, 250), -800, 150)
    stripe = _add(mat, _mul(mat, vc, 'G', _const(mat, -stripes, -1200, 400), '', -1000, 350),
                  _const(mat, 1.0, -1000, 450), -800, 400)
    base = _expr(mat, unreal.MaterialExpressionConstant3Vector, -800, -150,
                 constant=unreal.LinearColor(colour[0], colour[1], colour[2], 1.0))
    texture = _expr(mat, unreal.MaterialExpressionTextureSample, -800, 600,
                    texture=unreal.load_asset(f'{TEXTURE_DEST}/{detail}'),
                    sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)
    result = _mul(mat, _mul(mat, base, '', shade, '', -600, 0), '', _mul(mat, stripe, '', texture, 'R', -600, 400), '', -400, 200)
    lib.connect_material_property(result, '', unreal.MaterialProperty.MP_BASE_COLOR)
    lib.connect_material_property(_const(mat, roughness, -400, 400), '', unreal.MaterialProperty.MP_ROUGHNESS)
    return _finish(mat, physical)


def rock_material(name, detail, physical):
    """Vertex colours (sRGB bytes, so squared as a cheap sRGB-to-linear) * detail texture."""
    mat = _material(name)
    vc = _expr(mat, unreal.MaterialExpressionVertexColor, -1000, 0)
    power = _mul(mat, vc, '', vc, '', -800, 0)
    texture = _expr(mat, unreal.MaterialExpressionTextureSample, -800, 300,
                    texture=unreal.load_asset(f'{TEXTURE_DEST}/{detail}'),
                    sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)
    result = _mul(mat, power, '', texture, 'R', -500, 100)
    lib.connect_material_property(result, '', unreal.MaterialProperty.MP_BASE_COLOR)
    lib.connect_material_property(_const(mat, 0.95, -500, 300), '', unreal.MaterialProperty.MP_ROUGHNESS)
    return _finish(mat, physical)


def sea_material():
    mat = _material(SEA)
    base = _expr(mat, unreal.MaterialExpressionConstant3Vector, -500, 0, constant=unreal.LinearColor(0.01, 0.05, 0.1, 1))
    lib.connect_material_property(base, '', unreal.MaterialProperty.MP_BASE_COLOR)
    lib.connect_material_property(_const(mat, 0.15, -500, 200), '', unreal.MaterialProperty.MP_ROUGHNESS)
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


def build_materials():
    import_textures()
    materials = {slot: grass_material(*spec) for slot, spec in GRASS.items()}
    materials['IslandRock'] = rock_material(*ROCK)
    return materials


def import_mesh(name, materials):
    options = unreal.FbxImportUI()
    options.set_editor_property('import_mesh', True)
    options.set_editor_property('import_as_skeletal', False)
    options.set_editor_property('mesh_type_to_import', unreal.FBXImportType.FBXIT_STATIC_MESH)
    options.set_editor_property('import_materials', False)
    options.set_editor_property('import_textures', False)
    data = options.static_mesh_import_data
    data.set_editor_property('combine_meshes', True)
    data.set_editor_property('auto_generate_collision', False)
    data.set_editor_property('generate_lightmap_u_vs', False)
    data.set_editor_property('vertex_color_import_option', unreal.VertexColorImportOption.REPLACE)
    mesh = _import(SOURCE / f'{name}.fbx', DEST, options)
    assert isinstance(mesh, unreal.StaticMesh), f'{name}.fbx did not import'

    # Materials by slot name (the Blender material names).
    for index, slot in enumerate(mesh.get_editor_property('static_materials')):
        slot_name = str(slot.get_editor_property('material_slot_name'))
        key = next((k for k in materials if slot_name == k or slot_name.startswith(k + '_')), None)
        assert key, f'{name}: unexpected material slot {slot_name}'
        mesh.set_material(index, materials[key])

    # The ball and the buggy need the real surface (and its per-face physical material), not boxes.
    body = mesh.get_editor_property('body_setup')
    body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    size = mesh.get_bounds().box_extent
    print(f'MESH {name}: {size.x * 2 / M:.0f} x {size.y * 2 / M:.0f} x {size.z * 2 / M:.0f} m')
    return mesh


def _all():
    return actors.get_all_level_actors()


def remove_flat_ground(number):
    folder = f'Course/Hole{number:02d}'
    doomed = []
    for actor in _all():
        label = actor.get_actor_label()
        path = str(actor.get_folder_path())
        if label == f'Terrain_Hole{number:02d}' and isinstance(actor, unreal.Landscape):
            doomed.append(actor)
        elif isinstance(actor, unreal.StaticMeshActor) and path == folder and (
                label in ('Rough', 'Green', 'TeeBox') or label.startswith('Fairway') or label.startswith('Bunker')):
            doomed.append(actor)
        elif number == 1 and label == 'ClubhouseLawn':
            doomed.append(actor)
        elif path == f'{folder}/Islands' or (number == 1 and label == 'IslandSea'):
            doomed.append(actor)  # a previous run
    for actor in doomed:
        print('REMOVE', actor.get_actor_label())
        actors.destroy_actor(actor)


def place(mesh, label, folder, location=(0, 0, 0)):
    actor = actors.spawn_actor_from_object(mesh, unreal.Vector(*location), unreal.Rotator(0, 0, 0))
    actor.set_actor_label(label)
    actor.set_folder_path(folder)
    return actor


def seat(number, spots):
    """Move the hole's props onto the island surface using the heights the generator computed."""
    folder = f'Course/Hole{number:02d}'
    everything = _all()
    trees = spots['trees']
    for actor in everything:
        label = actor.get_actor_label()
        if str(actor.get_folder_path()) != folder:
            continue
        p = actor.get_actor_location()
        if label.startswith('TreeTrunk') or label.startswith('TreeCanopy') or label.startswith('Tree'):
            nearest = min(trees, key=lambda t: (t[0] * M - p.x) ** 2 + (t[1] * M - p.y) ** 2)
            lift = 450 if label.startswith('TreeTrunk') else 1050 if label.startswith('TreeCanopy') else 0
            actor.set_actor_location(unreal.Vector(p.x, p.y, nearest[2] * M + lift), False, True)
        elif label.startswith('TeeMarker'):
            nearest = min(spots['tee_markers'], key=lambda t: (t[1] * M - p.y) ** 2)
            actor.set_actor_location(unreal.Vector(p.x, p.y, nearest[2] * M + 5), False, True)
        elif label == f'GolfHole{number:02d}':
            cup_root = actor.cup_root
            cup_root.modify()
            cx, cy, cz = spots['cup']
            cup_root.set_world_location(unreal.Vector(cx * M, cy * M, cz * M), False, True)
    if number == 1:
        for actor in everything:
            label = actor.get_actor_label()
            if label == 'Clubhouse':
                p = actor.get_actor_location()
                actor.set_actor_location(unreal.Vector(p.x, p.y, spots['clubhouse'][2] * M), False, True)
            elif isinstance(actor, unreal.PlayerStart):
                x, y, z = spots['player_start']
                actor.set_actor_location(unreal.Vector(x * M, y * M, z * M + 120), False, True)


def add_sea(folder):
    plane = unreal.load_asset('/Engine/BasicShapes/Plane')
    sea = actors.spawn_actor_from_object(plane, unreal.Vector(0, 0, -25000), unreal.Rotator(0, 0, 0))
    sea.set_actor_scale3d(unreal.Vector(20000, 20000, 1))  # the 1 m engine plane -> 20 km of sea, 250 m down
    sea.static_mesh_component.set_material(0, unreal.load_asset(f'{MAT_DIR}/{SEA}'))
    sea.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    sea.set_actor_label('IslandSea')
    sea.set_folder_path(folder)


def apply_islands(number=1):
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    assert world.get_path_name() == f'{MAP_PATH}.Course', f'Open {MAP_PATH} first'
    spots = json.loads((SOURCE / f'Hole{number:02d}_spots.json').read_text())
    materials = build_materials()
    sea_material()
    meshes = {part: import_mesh(f'SM_H{number:02d}_{part}', materials) for part in ('IslandTop', 'IslandRock', 'Floaters')}

    remove_flat_ground(number)
    folder = f'Course/Hole{number:02d}/Islands'
    for part, mesh in meshes.items():
        place(mesh, f'{part}{number:02d}', folder)
    seat(number, spots)
    if number == 1:
        add_sea('Course/Environment')
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print(f'ISLANDS APPLIED hole {number}. Run validate_islands({number}) in a separate call.')


def validate_islands(number=1):
    """Trace the ball's view of the islands: expected surface at key spots, nothing in the gaps."""
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    spots = json.loads((SOURCE / f'Hole{number:02d}_spots.json').read_text())
    cx, cy, _ = spots['cup']
    probes = [('tee', 0, 0, 'Fairway'), ('fairway 120 m', 120, 0, 'Fairway'), ('fairway 250 m', 250, 0, 'Fairway'),
              ('green', cx, cy, 'Green'), ('behind tee', -30, 0, 'Rough'), ('gap after tee', 22, 0, None),
              ('far left of fairway', 150, -130, None)]
    names = {unreal.PhysicalSurface.SURFACE_TYPE1: 'Fairway', unreal.PhysicalSurface.SURFACE_TYPE2: 'Rough',
             unreal.PhysicalSurface.SURFACE_TYPE3: 'Bunker', unreal.PhysicalSurface.SURFACE_TYPE4: 'Green'}
    bad = 0
    for label, x, y, expected in probes:
        hit = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x * M, y * M, 3000), unreal.Vector(x * M, y * M, -5000),
                                                     unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [], unreal.DrawDebugTrace.NONE, True)
        found = None
        if hit:
            t = hit.to_tuple()  # (blocking, overlap, time, distance, location, impact point, ..., phys material at 8)
            pm = t[8]
            found = names.get(pm.get_editor_property('surface_type'), str(pm)) if pm else 'no material'
            z = t[5].z
        ok = found == expected if expected else (not hit or z < -2000)
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} {label:22s} expected {expected or 'gap'}, found {found}"
              + (f' at z {z / M:.1f} m' if hit else ''))
    print(f'VALIDATE hole {number}: {bad} problems')
    return bad
