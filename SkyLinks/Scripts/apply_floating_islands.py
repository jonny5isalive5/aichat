"""Put the floating-island course into the Course map (run inside the editor, Output Log in Python mode or Aura).

    import sys, unreal; sys.path.append(unreal.Paths.project_dir() + "Scripts")
    import apply_floating_islands as isl
    isl.apply_course()          holes 1-18: islands, water, vines, footbridges, trees, rope bridges, fog, sea
    isl.validate_course()       in a LATER call (collision cooks after the import): what the ball finds at each
                                tee and cup
    isl.apply_islands(n)        one hole only (no bridges or fog; its trees are added again, so clear by hand)
    isl.trees_to_foliage()      turn the scripted forests into foliage (Foliage mode > Select moves single trees)
    isl.fab_footbridges()       the Fab bridge on every brook crossing (deck_offset_cm=... to lift / sink it)
    isl.raise_fog(20)           lift every cloud patch 20 m (or lower it with a negative number)

Needs, from Scripts/import_trees.py, the stylised trees and their M_Tree_Bark / M_Tree_Leaves / M_Tree_Vines
materials (the vines and the rope bridges use them too), and the SkyLinksForest C++ class (rebuild first).

Sources (Art/Blender/build_course_islands.py), all in world coordinates, placed at the origin:
  Art/Exports/Islands/SM_Hnn_{IslandTop,IslandRock,Vines,Water,Props}.fbx, SM_Hnn_FloaterNN.fbx, Holenn_spots.json
  Art/Exports/Islands/SM_Bridge_nn_mm{,_Rails}.fbx (looks) + SM_Bridge_nn_mm_Guard.fbx (hidden drive slab and walls), Course_links.json (bridges and fog patches)
Each hole's GolfHole actor is moved to its island: tee, heading, height, aim point, cup, par and name.
Re-running replaces everything it made; it is safe to run twice.
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
TREES = '/Game/Course/Trees'
MAP_PATH = '/Game/Maps/Course'
M = 100.0
HOLES = range(1, 19)

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
PARTS = ('IslandTop', 'IslandRock', 'Vines', 'Water', 'Props')
NO_COLLISION = ('Vines',)  # hanging ivy: the ball and buggy pass through

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
    for name in ('T_GrassDetail', 'T_SandDetail', 'T_RockDetail'):
        texture = _import(TEXTURE_SOURCE / f'{name}.png', TEXTURE_DEST)
        assert texture, f'{name}.png did not import'
        texture.set_editor_property('srgb', False)  # a brightness multiplier, not a colour
        texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_GRAYSCALE)
        unreal.EditorAssetLibrary.save_loaded_asset(texture)


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


def plain_material(name, colour, roughness, physical=None, specular=None):
    mat = _material(name)
    base = _expr(mat, unreal.MaterialExpressionConstant3Vector, -500, 0, constant=unreal.LinearColor(*colour, 1))
    lib.connect_material_property(base, '', unreal.MaterialProperty.MP_BASE_COLOR)
    lib.connect_material_property(_const(mat, roughness, -500, 200), '', unreal.MaterialProperty.MP_ROUGHNESS)
    if specular is not None:
        lib.connect_material_property(_const(mat, specular, -500, 300), '', unreal.MaterialProperty.MP_SPECULAR)
    if physical:
        return _finish(mat, physical)
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


def build_materials():
    import_textures()
    materials = {slot: grass_material(*spec) for slot, spec in GRASS.items()}
    materials['IslandRock'] = rock_material(*ROCK)
    materials['Water'] = plain_material('M_Island_Water', (0.015, 0.06, 0.08), 0.06, 'PM_Water', specular=0.8)
    plain_material(SEA, (0.01, 0.05, 0.1), 0.15)
    for slot, name in (('TreeBark', 'M_Tree_Bark'), ('TreeLeaves', 'M_Tree_Leaves'), ('Vines', 'M_Tree_Vines')):
        mat = unreal.load_asset(f'{TREES}/{name}')
        assert mat, f'{TREES}/{name} missing: run import_trees.import_trees() first'
        materials[slot] = mat
    return materials


def import_mesh(name, materials, collide=True):
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
    for index, slot in enumerate(mesh.get_editor_property('static_materials')):
        slot_name = str(slot.get_editor_property('material_slot_name'))
        key = next((k for k in materials if slot_name == k or slot_name.startswith(k + '_') or slot_name.startswith(k + '.')), None)
        assert key, f'{name}: unexpected material slot {slot_name}'
        mesh.set_material(index, materials[key])
    if collide:
        # The ball and the buggy need the real surface (and its per-face physical material), not boxes.
        body = mesh.get_editor_property('body_setup')
        body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
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
        elif path == folder and isinstance(actor, unreal.StaticMeshActor) and (
                label in ('Rough', 'Green', 'TeeBox') or label.startswith(('Fairway', 'Bunker', 'Water', 'Tree'))):
            doomed.append(actor)  # blockout slabs and the placeholder ball trees (the forest replaces them)
        elif number == 1 and label == 'ClubhouseLawn':
            doomed.append(actor)
        elif path in (f'{folder}/Islands', f'{folder}/Trees', f'{folder}/Islands/Floaters', f'{folder}/Footbridges'):
            doomed.append(actor)  # a previous run
    for actor in doomed:
        actors.destroy_actor(actor)
    print(f'HOLE {number}: removed {len(doomed)} old actors')


def place(mesh, label, folder, collide=True, shadow=None, location=None):
    actor = actors.spawn_actor_from_object(mesh, location or unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    actor.set_actor_label(label)
    actor.set_folder_path(folder)
    if not collide:
        actor.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    if shadow is False or (shadow is None and not collide):
        actor.static_mesh_component.set_editor_property('cast_shadow', False)
    return actor


def _v(p, lift=0.0):
    return unreal.Vector(p[0] * M, p[1] * M, p[2] * M + lift)


def place_hole(number, spots):
    """Move the hole's GolfHole to its island (tee, heading, aim, cup) and seat its tee markers."""
    folder = f'Course/Hole{number:02d}'
    everything = _all()
    golf_hole = next((a for a in everything if a.get_actor_label() == f'GolfHole{number:02d}'), None)
    assert golf_hole, f'GolfHole{number:02d} not found in the map'
    golf_hole.modify()
    golf_hole.set_actor_location_and_rotation(_v(spots['tee'], 1.0), unreal.Rotator(0, 0, spots['yaw']), False, True)
    ax, ay = spots['aim_local']
    golf_hole.set_editor_property('aim_point', unreal.Vector(ax * M, ay * M, 0))
    golf_hole.set_editor_property('par', spots['par'])
    golf_hole.set_editor_property('hole_name', spots['name'])
    cup_root = golf_hole.cup_root
    cup_root.modify()
    cup_root.set_world_location(_v(spots['cup']), False, True)
    markers = [a for a in everything if str(a.get_folder_path()) == folder and a.get_actor_label().startswith('TeeMarker')]
    for actor, spot in zip(markers, spots['tee_markers']):
        actor.set_actor_location(_v(spot, 5.0), False, True)
    if number == 1:
        clubhouse = next((a for a in everything if a.get_actor_label() == 'Clubhouse'), None)
        if clubhouse:
            p = clubhouse.get_actor_location()
            clubhouse.set_actor_location(unreal.Vector(p.x, p.y, spots['clubhouse'][2] * M), False, True)
            setup_car_park(clubhouse, everything)
        else:
            for actor in everything:
                if isinstance(actor, unreal.PlayerStart):
                    actor.set_actor_location(_v(spots['player_start'], 120.0), False, True)


# Car park behind the clubhouse (Art/Blender/build_clubhouse.py, clubhouse-local metres, Blender axes): the row of
# bays nearest the building spans y 8.5..13.5, bays 2.5 m wide centred on x = -11.25 + 2.5 i; the aisle is y 13.5..20.5.
CAR_PARK_BAYS = [(-3.75, 11.5), (-1.25, 11.5), (1.25, 11.5), (3.75, 11.5)]
CAR_PARK_SPAWN = (0.0, 17.0)


def setup_car_park(clubhouse, everything):
    """Buggy bays (TargetPoints tagged BuggyBay: the game parks a free buggy on each) and the PlayerStart in the aisle."""
    folder = 'Course/Hole01/CarPark'
    for actor in everything:
        if str(actor.get_folder_path()) == folder:
            actors.destroy_actor(actor)
    frame = clubhouse.get_actor_transform()
    yaw = clubhouse.get_actor_rotation().yaw

    def world(x, y, lift):
        # Blender (x, y) -> Unreal clubhouse-local (x, -y), then the clubhouse's own placement.
        return unreal.MathLibrary.transform_location(frame, unreal.Vector(x * M, -y * M, lift))
    for i, (x, y) in enumerate(CAR_PARK_BAYS):
        bay = actors.spawn_actor_from_class(unreal.TargetPoint, world(x, y, 60.0), unreal.Rotator(0, 0, yaw - 90.0))
        bay.set_actor_label(f'BuggyBay{i + 1}')
        bay.set_folder_path(folder)
        bay.set_editor_property('tags', [unreal.Name('BuggyBay')])  # nose out, toward the aisle
    starts = [a for a in everything if isinstance(a, unreal.PlayerStart)]
    for start in starts:
        start.set_actor_location_and_rotation(world(*CAR_PARK_SPAWN, 120.0), unreal.Rotator(0, 0, yaw + 90.0), False, True)
    print(f'CAR PARK: {len(CAR_PARK_BAYS)} buggy bays, {len(starts)} player start(s) moved to the car park')


FOG_LIFT = 20.0  # m above the heights in Course_links.json: the cloud patches drift up among the islands


def _foliage_types():
    """FT_* foliage types from import_trees (one per tree / bush kind)."""
    types = [unreal.load_asset(f'/Game/Course/Foliage/{path.split("/")[-1].split(".")[0]}')
             for path in unreal.EditorAssetLibrary.list_assets('/Game/Course/Foliage', recursive=False)]
    types = [t for t in types if isinstance(t, unreal.FoliageType)]
    assert types, '/Game/Course/Foliage is empty: run import_trees.import_trees() first'
    return types


def trees_to_foliage():
    """Hand every SkyLinksForest's trees to the level's foliage: in Foliage mode (Select tool) each tree can
    be clicked and moved on its own, and the brush paints more. Instancing (and the fps) stays the same."""
    types = _foliage_types()
    moved = 0
    for forest in [a for a in _all() if isinstance(a, unreal.SkyLinksForest)]:
        moved += forest.convert_to_foliage(types)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print(f'TREES: {moved} trees and bushes are now foliage')


FAB_BRIDGE = '/Game/Course/Vegetation/Bridge1'   # Fab "Bridge" (TAKOYTO): 2 m wide, 8.6 m long along its Y axis
FOOTBRIDGE_WIDTH = 3.0                           # m, as Art/Blender/build_course_islands.py (so the buggy fits)


def place_footbridges(number, spots, deck_offset_cm=0.0):
    """The Fab bridge over each brook crossing (looks only), stretched to the span; the Props mesh underneath
    becomes the invisible flat deck the buggy and ball actually use."""
    folder = f'Course/Hole{number:02d}/Footbridges'
    for actor in _all():
        if str(actor.get_folder_path()) == folder:
            actors.destroy_actor(actor)
        elif actor.get_actor_label() == f'Props{number:02d}':
            actor.set_actor_hidden_in_game(True)
            actor.static_mesh_component.set_editor_property('visible', False)
            actor.static_mesh_component.set_editor_property('cast_shadow', False)
    mesh = unreal.load_asset(FAB_BRIDGE)
    if not mesh or not spots.get('footbridges'):
        return
    box = mesh.get_bounding_box()
    width_cm, length_cm = box.max.x - box.min.x, box.max.y - box.min.y
    for i, (x, y, z, yaw, length) in enumerate(spots['footbridges']):
        # The mesh runs along its Y axis: turn it a quarter so Y follows the crossing; overlap the banks a little.
        bridge = actors.spawn_actor_from_object(mesh, unreal.Vector(x * M, y * M, z * M + deck_offset_cm), unreal.Rotator(0, 0, yaw - 90.0))
        bridge.set_actor_scale3d(unreal.Vector(FOOTBRIDGE_WIDTH * M / width_cm, (length + 1.5) * M / length_cm, 1.0))
        bridge.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        bridge.set_actor_label(f'Footbridge{number:02d}_{i + 1}')
        bridge.set_folder_path(folder)


def fab_footbridges(deck_offset_cm=0.0, holes=HOLES):
    """Swap every footbridge for the Fab bridge: re-imports the decks (SM_Hnn_Props), hides them, places the
    bridges. deck_offset_cm lifts (+) or sinks (-) the Fab bridges if their deck doesn't meet the drive height."""
    materials = build_materials()
    for number in holes:
        spots_path = SOURCE / f'Hole{number:02d}_spots.json'
        if not spots_path.is_file():
            continue
        spots = json.loads(spots_path.read_text())
        if not spots.get('footbridges'):
            continue
        import_mesh(f'SM_H{number:02d}_Props', materials)
        place_footbridges(number, spots, deck_offset_cm)
        print(f"FOOTBRIDGES hole {number}: {len(spots['footbridges'])}")
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()


def reimport_props(holes=HOLES):
    """Re-import the footbridges (SM_Hnn_Props) in place: the placed actors pick up the new mesh, nothing moves."""
    materials = build_materials()
    done = [f'SM_H{n:02d}_Props' for n in holes if (SOURCE / f'SM_H{n:02d}_Props.fbx').is_file()]
    for name in done:
        import_mesh(name, materials)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print(f'PROPS re-imported: {", ".join(done)}')


def raise_fog(meters=20.0):
    """Move every cloud patch up (or down) without rebuilding anything else."""
    count = 0
    for actor in _all():
        if str(actor.get_folder_path()) == 'Course/Fog':
            p = actor.get_actor_location()
            actor.set_actor_location(unreal.Vector(p.x, p.y, p.z + meters * M), False, True)
            count += 1
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print(f'FOG: {count} patches moved {meters:+.0f} m')


def _tree_mesh(kind):
    path = f'{TREES}/SM_Tree_{kind}' if not kind.startswith('Bush') else f'{TREES}/SM_{kind}'
    mesh = unreal.load_asset(path)
    assert mesh, f'{path} missing: run import_trees.import_trees() first'
    return mesh


def plant_forest(number, spots):
    """All the hole's trees as instances on one SkyLinksForest actor (the gameplay trees included)."""
    assert hasattr(unreal, 'SkyLinksForest'), 'SkyLinksForest not found: rebuild the C++ first'
    folder = f'Course/Hole{number:02d}/Trees'
    forest = actors.spawn_actor_from_class(unreal.SkyLinksForest, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    forest.set_actor_label(f'Forest{number:02d}')
    forest.set_folder_path(folder)
    by_kind = {}
    for x, y, z, yaw, scale, kind in spots['forest']:
        by_kind.setdefault(kind, []).append(unreal.Transform(unreal.Vector(x * M, y * M, z * M), unreal.Rotator(0, 0, yaw),
                                                             unreal.Vector(scale, scale, scale)))
    for i, (x, y, z) in enumerate(spots.get('gameplay_trees', [])):
        by_kind.setdefault('Oak_A' if i % 2 == 0 else 'Oak_B', []).append(
            unreal.Transform(unreal.Vector(x * M, y * M, z * M - 10), unreal.Rotator(0, 0, i * 97.0), unreal.Vector(1, 1, 1)))
    total = 0
    for kind, transforms in by_kind.items():
        total += forest.add_trees(_tree_mesh(kind), transforms)
    # Into the level's foliage, so single trees can be moved in Foliage mode (the forest actor goes away).
    forest.convert_to_foliage(_foliage_types())
    print(f'HOLE {number}: planted {total} trees and bushes (foliage)')


def apply_islands(number, materials=None):
    materials = materials or build_materials()
    spots = json.loads((SOURCE / f'Hole{number:02d}_spots.json').read_text())
    remove_flat_ground(number)
    folder = f'Course/Hole{number:02d}/Islands'
    for part in PARTS:
        name = f'SM_H{number:02d}_{part}'
        if not (SOURCE / f'{name}.fbx').is_file():
            continue
        collide = part not in NO_COLLISION
        place(import_mesh(name, materials, collide), f'{part}{number:02d}', folder, collide)
    # Background mini islands, high above the hole: one actor each (pivot in its middle), free to move by hand.
    for name, x, y, z in spots.get('floaters', []):
        place(import_mesh(name, materials, collide=False), name.replace(f'SM_H{number:02d}_', ''), f'{folder}/Floaters',
              collide=False, shadow=True, location=unreal.Vector(x * M, y * M, z * M))
    place_hole(number, spots)
    place_footbridges(number, spots)
    plant_forest(number, spots)
    print(f'HOLE {number} {spots["name"]} (par {spots["par"]}) placed at z {spots["tee"][2]:+.0f} m')


def apply_bridges(materials, links):
    folder = 'Course/Bridges'
    for actor in _all():
        if str(actor.get_folder_path()) == folder:
            actors.destroy_actor(actor)
    for bridge in links['bridges']:
        # Planks are looks only (driving over separate planks snags the buggy): no collision.
        mesh = import_mesh(bridge['name'], materials, collide=False)
        place(mesh, bridge['name'].replace('SM_', ''), folder, collide=False, shadow=True)
        if bridge.get('rails'):
            # Ropes, posts and gates: no collision, so the buggy can't snag on them.
            rails = import_mesh(bridge['rails'], materials, collide=False)
            place(rails, bridge['rails'].replace('SM_', ''), folder, collide=False, shadow=True)
        if bridge.get('guard'):
            # Invisible: the smooth slab the buggy drives on and low walls along the deck edges.
            guard = place(import_mesh(bridge['guard'], materials), bridge['guard'].replace('SM_', ''), folder)
            guard.set_actor_hidden_in_game(True)
            guard.static_mesh_component.set_editor_property('cast_shadow', False)
            guard.static_mesh_component.set_editor_property('visible', False)
        print(f"BRIDGE {bridge['name']}: {bridge['span']} m")


def add_fog(links):
    """Cloud-like local fog patches under the bridges and between the islands."""
    folder = 'Course/Fog'
    for actor in _all():
        if str(actor.get_folder_path()) == folder:
            actors.destroy_actor(actor)
    if not hasattr(unreal, 'LocalFogVolume'):
        print('FOG skipped: LocalFogVolume not available in this engine build')
        return
    for i, (x, y, z, radius) in enumerate(links['fog']):
        fog = actors.spawn_actor_from_class(unreal.LocalFogVolume, unreal.Vector(x * M, y * M, (z + FOG_LIFT) * M),
                                            unreal.Rotator(0, 0, 0))
        fog.set_actor_scale3d(unreal.Vector(radius / 5.0, radius / 5.0, radius / 10.0))  # flattened like a cloud bank
        fog.set_actor_label(f'CloudFog{i:02d}')
        fog.set_folder_path(folder)
        component = fog.get_component_by_class(unreal.LocalFogVolumeComponent)
        for key, value in (('radial_fog_extinction', 0.35), ('height_fog_extinction', 0.0),
                           ('fog_albedo', unreal.LinearColor(1, 1, 1, 1)), ('fog_phase_g', 0.3)):
            try:
                component.set_editor_property(key, value)
            except Exception as error:
                print(f'FOG note: {key}: {error}')
    print(f"FOG {len(links['fog'])} cloud patches")


def ensure_sea():
    if any(a.get_actor_label() == 'IslandSea' for a in _all()):
        return
    plane = unreal.load_asset('/Engine/BasicShapes/Plane')
    sea = actors.spawn_actor_from_object(plane, unreal.Vector(0, 0, -25000), unreal.Rotator(0, 0, 0))
    sea.set_actor_scale3d(unreal.Vector(20000, 20000, 1))  # the 1 m engine plane -> 20 km of sea, 250 m down
    sea.static_mesh_component.set_material(0, unreal.load_asset(f'{MAT_DIR}/{SEA}'))
    sea.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    sea.set_actor_label('IslandSea')
    sea.set_folder_path('Course/Environment')


def apply_course(holes=HOLES):
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    assert world.get_path_name() == f'{MAP_PATH}.Course', f'Open {MAP_PATH} first'
    materials = build_materials()
    # Replanting every hole: clear the old foliage trees first (they'd double up otherwise).
    unreal.SkyLinksForest.clear_foliage(world, _foliage_types())
    for number in holes:
        apply_islands(number, materials)
    links = json.loads((SOURCE / 'Course_links.json').read_text())
    apply_bridges(materials, links)
    add_fog(links)
    ensure_sea()
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print('COURSE APPLIED. Run validate_course() in a separate call.')


def validate_course(holes=HOLES):
    """Trace each hole's tee and cup from above: the ball should find fairway (tee box) and green."""
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    names = {unreal.PhysicalSurface.SURFACE_TYPE1: 'Fairway', unreal.PhysicalSurface.SURFACE_TYPE2: 'Rough',
             unreal.PhysicalSurface.SURFACE_TYPE3: 'Bunker', unreal.PhysicalSurface.SURFACE_TYPE4: 'Green',
             unreal.PhysicalSurface.SURFACE_TYPE5: 'Water'}
    bad = 0
    for number in holes:
        spots = json.loads((SOURCE / f'Hole{number:02d}_spots.json').read_text())
        for label, spot, expected in (('tee', spots['tee'], 'Fairway'), ('cup', spots['cup'], 'Green')):
            x, y, z = spot
            hit = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x * M, y * M, z * M + 3000),
                                                         unreal.Vector(x * M, y * M, z * M - 3000),
                                                         unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [], unreal.DrawDebugTrace.NONE, True)
            found = None
            if hit:
                t = hit.to_tuple()  # (blocking, overlap, time, distance, location, impact point, ..., phys material at 8)
                found = names.get(t[8].get_editor_property('surface_type'), 'other') if t[8] else 'no material'
            ok = found == expected
            bad += not ok
            print(f"{'OK ' if ok else 'BAD'} hole {number} {label}: expected {expected}, found {found}")
    print(f'VALIDATE course: {bad} problems')
    return bad
