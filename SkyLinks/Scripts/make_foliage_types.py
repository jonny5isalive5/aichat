"""Create foliage types for painting Megaplant trees and bushes with the Foliage Mode brush.

Needs the C++ classes SkyLinksTree / SkyLinksBush (compile first). Run in the editor, Output Log in Python mode:

    import sys, unreal; sys.path.append(unreal.Paths.project_dir() + "Scripts")
    import make_foliage_types; make_foliage_types.make()

Creates /Game/Course/Foliage/FT_Trees and FT_Bushes (Actor Foliage: each painted instance is a SkyLinksTree
or SkyLinksBush actor that picks its own Megaplant variant). Then: Modes > Foliage, drag both into the
foliage panel if they are not listed, tick one, and paint on the islands with left click
(Shift + click erases). Spacing, density, size and slope limits below are the starting brush settings;
change them per type in the foliage panel.
"""
import unreal

DEST = '/Game/Course/Foliage'
TYPES = {
    # name: (actor class, density per 10 m x 10 m, min spacing cm, scale range, max slope degrees)
    'FT_Trees': ('SkyLinksTree', 0.35, 900.0, (0.85, 1.15), 25.0),
    'FT_Bushes': ('SkyLinksBush', 1.2, 250.0, (0.7, 1.2), 35.0),
}

tools = unreal.AssetToolsHelpers.get_asset_tools()


def _set(obj, name, value):
    try:
        obj.set_editor_property(name, value)
    except Exception as error:  # property names drift between engine versions; report and carry on
        print(f'FOLIAGE note: could not set {name}: {error}')


def make():
    for name, (class_name, density, spacing, (smin, smax), slope) in TYPES.items():
        actor_class = getattr(unreal, class_name, None)
        assert actor_class, f'{class_name} not found: rebuild the C++ first'
        path = f'{DEST}/{name}'
        if unreal.EditorAssetLibrary.does_asset_exist(path):
            foliage = unreal.load_asset(path)
        else:
            foliage = tools.create_asset(name, DEST, unreal.FoliageType_Actor, None)
        assert foliage, f'could not create {path}'
        _set(foliage, 'actor_class', actor_class.static_class())
        _set(foliage, 'density', density)
        _set(foliage, 'radius', spacing * 0.5)
        _set(foliage, 'scaling', unreal.FoliageScaling.UNIFORM)
        _set(foliage, 'scale_x', unreal.FloatInterval(smin, smax))
        _set(foliage, 'random_yaw', True)
        _set(foliage, 'align_to_normal', False)
        _set(foliage, 'ground_slope_angle', unreal.FloatInterval(0.0, slope))
        _set(foliage, 'z_offset', unreal.FloatInterval(-10.0, -5.0))
        unreal.EditorAssetLibrary.save_loaded_asset(foliage)
        print(f'FOLIAGE {path}: {class_name}, density {density}, spacing {spacing / 100:.1f} m, scale {smin}-{smax}')
