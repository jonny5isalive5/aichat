"""Import the owner's Mixamo golfer and golf animations into /Game/Characters/Golfer.

Run in the editor (Aura's execute_unreal_python, or Tools > Execute Python Script). No map changes.
AGolfCharacter loads these exact asset paths at runtime, so once this has run the golfer replaces the
placeholder cylinder, swings with the right animation for the club and reacts after shots.

Sources (Art/Golfer):
  Golfer.fbx                 Mixamo "With Skin" export of the Tripo golfer (33-bone mixamorig skeleton,
                             about 95 cm tall; the game scales it 1.9x)
  Animations/*.fbx           Mixamo "Without Skin" clips downloaded on that same character
Art/Exports/SM_Club_Iron.fbx, SM_Club_Putter.fbx   Blender clubs (Art/Blender/build_clubs.py)

Animations/Fixed/*.fbx      cleaned swing clips from Art/Blender/fix_swing_clips.py, used instead of the originals

Idle.fbx and Walking.fbx were downloaded on a different Mixamo character (65 bones, other proportions);
Art/Blender/retarget_walk_idle.py retargets them onto the golfer (Fixed/). Re-running replaces existing assets.
"""
from pathlib import Path
import unreal

SOURCE = Path(unreal.Paths.project_dir()) / 'Art' / 'Golfer'
DEST = '/Game/Characters/Golfer'
ANIM_DEST = DEST + '/Animations'

# Mixamo file name -> asset name the game looks for (A_Drive, A_Chip, ... are loaded by AGolfCharacter).
ANIMATIONS = {
    'Golf Drive': 'A_Drive',
    'Golf Drive alt1': 'A_DriveAlt',
    'Golf Drive Setup': 'A_DriveSetup',
    'Golf Tee Up': 'A_TeeUp',
    'Golf Chip': 'A_Chip',
    'Golf Chip (replay if long shit in)': 'A_ChipLong',
    'Golf Putt': 'A_Putt',
    'Golf Putt Victory': 'A_PuttVictory',
    'Golf Putt Victory on long putt': 'A_PuttVictoryLong',
    'Golf Putt Failure missed putt': 'A_PuttMiss',
    'Golf Bad Shot': 'A_BadShot',
    'Hokey Pokey hole in one': 'A_HoleInOne',
    'Silly Dancing celebrate': 'A_Celebrate',
    'Silly Dancing celebrate alt1': 'A_CelebrateAlt',
    'Entering Car': 'A_EnterBuggy',
    'Exiting Car': 'A_ExitBuggy',
    'Walking': 'A_Walk',   # Fixed/ copies retargeted onto the golfer by Art/Blender/retarget_walk_idle.py
    'Idle': 'A_Idle',
}
NEEDS_REDOWNLOAD = {}

tools = unreal.AssetToolsHelpers.get_asset_tools()


def run_task(filename, destination, name, options):
    task = unreal.AssetImportTask()
    for key, value in [('filename', str(filename)), ('destination_path', destination), ('destination_name', name),
                       ('automated', True), ('replace_existing', True), ('save', True), ('options', options)]:
        task.set_editor_property(key, value)
    tools.import_asset_tasks([task])
    return unreal.load_asset(f'{destination}/{name}')


def import_body():
    options = unreal.FbxImportUI()
    options.set_editor_property('import_mesh', True)
    options.set_editor_property('import_as_skeletal', True)
    options.set_editor_property('mesh_type_to_import', unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    options.set_editor_property('import_animations', False)
    options.set_editor_property('import_materials', True)
    options.set_editor_property('import_textures', True)
    options.set_editor_property('create_physics_asset', True)
    mesh = run_task(SOURCE / 'Golfer.fbx', DEST, 'SK_Golfer', options)
    assert isinstance(mesh, unreal.SkeletalMesh), 'Golfer.fbx did not import as a skeletal mesh'
    skeleton = mesh.get_editor_property('skeleton')
    assert skeleton, 'No skeleton created for SK_Golfer'
    height = mesh.get_bounds().box_extent.z * 2
    print(f'BODY SK_Golfer skeleton {skeleton.get_path_name()} height {height:.1f} cm (the game scales it 1.9x)')
    return skeleton


def import_animation(skeleton, source_name, asset_name):
    # Art/Blender/fix_swing_clips.py writes cleaned copies (feet planted) of glitchy clips to Animations/Fixed.
    fixed = SOURCE / 'Animations' / 'Fixed' / f'{source_name}.fbx'
    path = fixed if fixed.is_file() else SOURCE / 'Animations' / f'{source_name}.fbx'
    if not path.is_file():
        print(f'MISSING {path.name}')
        return None
    options = unreal.FbxImportUI()
    options.set_editor_property('import_mesh', False)
    options.set_editor_property('import_as_skeletal', True)
    options.set_editor_property('mesh_type_to_import', unreal.FBXImportType.FBXIT_ANIMATION)
    options.set_editor_property('skeleton', skeleton)
    options.set_editor_property('import_animations', True)
    options.set_editor_property('import_materials', False)
    options.set_editor_property('import_textures', False)
    anim = run_task(path, ANIM_DEST, asset_name, options)
    if not isinstance(anim, unreal.AnimSequence):
        print(f'FAILED {source_name} -> {asset_name}')
        return None
    print(f'ANIM {asset_name:18s} {anim.get_play_length():6.2f} s  <- {source_name}{" (fixed)" if path == fixed else ""}')
    return anim


def import_clubs():
    for name in ['SM_Club_Iron', 'SM_Club_Putter']:
        options = unreal.FbxImportUI()
        options.set_editor_property('import_mesh', True)
        options.set_editor_property('import_as_skeletal', False)
        options.set_editor_property('mesh_type_to_import', unreal.FBXImportType.FBXIT_STATIC_MESH)
        options.set_editor_property('import_materials', True)
        options.set_editor_property('import_textures', False)
        options.static_mesh_import_data.set_editor_property('combine_meshes', True)
        options.static_mesh_import_data.set_editor_property('auto_generate_collision', False)
        mesh = run_task(Path(unreal.Paths.project_dir()) / 'Art' / 'Exports' / f'{name}.fbx', DEST, name, options)
        assert isinstance(mesh, unreal.StaticMesh), f'{name} did not import'
        print(f'CLUB {name} length {mesh.get_bounds().box_extent.z * 2:.1f} cm')


def import_golfer(include_idle_walk=False):
    skeleton = import_body()
    import_clubs()
    wanted = dict(ANIMATIONS)
    if include_idle_walk:
        wanted.update(NEEDS_REDOWNLOAD)
    imported = [name for source, name in wanted.items() if import_animation(skeleton, source, name)]
    required = {'A_Drive', 'A_Chip', 'A_Putt'}
    missing = required - set(imported)
    print(f'GOLFER DONE: {len(imported)} animations; required swings missing: {sorted(missing) or "none"}')
    return imported


def reimport_animations(names):
    """Re-import only these clips, e.g. reimport_animations(['A_Chip', 'A_Putt']) after fixing them."""
    skeleton = unreal.load_asset(f'{DEST}/SK_Golfer').get_editor_property('skeleton')
    return [name for source, name in ANIMATIONS.items() if name in names and import_animation(skeleton, source, name)]


import_golfer()
