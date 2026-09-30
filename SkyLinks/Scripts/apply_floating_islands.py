"""Put the floating-island course into the Course map (run inside the editor, Output Log in Python mode or Aura).

    import sys, unreal; sys.path.append(unreal.Paths.project_dir() + "Scripts")
    import apply_floating_islands as isl
    isl.apply_course()          holes 1-18: islands, water, vines, footbridges, trees, rope bridges, fog, sea
    isl.validate_course()       in a LATER call (collision cooks after the import): what the ball finds at each
                                tee and cup
    isl.apply_islands(n)        one hole only (no bridges or fog; its trees are added again, so clear by hand)
    isl.trees_to_foliage()      turn the scripted forests into foliage (Foliage mode > Select moves single trees)
    isl.fab_footbridges()       the Fab bridge on every brook crossing (deck_offset_cm=... to lift / sink it)
    isl.make_path_decal()       M_PathDecal: drag Decal Actors onto the grass for footpaths (the easy way)
    isl.export_paths()          save footpaths drawn as splines (actors named Path...) for baking into the islands
    isl.refresh_islands()       after an island rebuild: new meshes in place, trees replanted; your floaters stay
    isl.refresh_remaining()     the same, a few holes per run, crash-proof: run it until it says ALL DONE
    isl.reimport_tops([4])      re-import island surfaces only (after paths are baked); nothing else moves
    isl.lift_floaters()         lift floating islands that hang too low over a hole (lift_floaters(60) for higher)
    isl.update_materials()      rebuild the island materials only (grass paths: Mesh Paint, Blue channel)
    isl.update_surfaces()       new island surfaces + materials only (nothing in the level moves)
    isl.tune_look()             tame the bright exposure, richer colours (tune_look(-1.5) darker, (-0.5) brighter)
    isl.import_grass()          the 3D grass clumps + M_GrassBlades (grown around the camera in game)
    isl.raise_fog(20)           lift every cloud patch 20 m (or lower it with a negative number)
    isl.portals()               rope bridges out, portals in (drive through to the next hole); needs Build.bat first
    isl.portal_views()          bake a picture of the next hole into each portal's swirl (re-run after changing holes)
    isl.fog_floaters()          soft mist clouds under every floating island you've kept (run again after changing them)
    isl.reimport_paths()        after the buggy paths' ground changed: surfaces, rock and vines re-imported in place

Needs, from Scripts/import_trees.py, the stylised trees and their M_Tree_Bark / M_Tree_Leaves / M_Tree_Vines
materials (the vines and the rope bridges use them too), and the SkyLinksForest C++ class (rebuild first).

Sources (Art/Blender/build_course_islands.py), all in world coordinates, placed at the origin:
  Art/Exports/Islands/SM_Hnn_{IslandTop,IslandRock,Vines,Water,Props}.fbx, SM_Hnn_FloaterNN.fbx, Holenn_spots.json
  Art/Exports/Islands/SM_Bridge_nn_mm{,_Rails}.fbx (looks) + SM_Bridge_nn_mm_Guard.fbx (hidden drive slab and walls), Course_links.json (bridges and fog patches)
Each hole's GolfHole actor is moved to its island: tee, heading, height, aim point, cup, par and name.
Re-running replaces everything it made; it is safe to run twice.
"""
import json
import math
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

# Slot name in the FBX -> (Unreal material, surface kind, roughness, physical material). Each kind is shaded by
# SURFACE_CODE below: several shades of green in patches, crisp mowing stripes, green collars, a first cut of
# rough round the fairways, and grainy raked sand with turf walls under the bunker lips.
GRASS = {
    'Rough':   ('M_Island_Rough',   'rough',   0.95, 'PM_Rough'),
    'Fairway': ('M_Island_Fairway', 'fairway', 0.88, 'PM_Fairway'),
    'Green':   ('M_Island_Green',   'green',   0.8,  'PM_Green'),
    'TeeBox':  ('M_Island_TeeBox',  'tee',     0.88, 'PM_Fairway'),
    'Bunker':  ('M_Island_Bunker',  'bunker',  0.92, 'PM_Bunker'),
}
ROCK = ('M_Island_Rock', 'T_RockDetail', 'PM_Rough')
PATH_COLOUR = (0.23, 0.16, 0.09)  # painted footpaths (vertex colour B) on the grass: packed earth
SEA = 'M_Island_Sea'
PARTS = ('IslandTop', 'IslandRock', 'Vines', 'Water', 'Props', 'Stadium')
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


SURFACE_TEXTURES = {  # Art/Blender/surface_textures.py: name -> (compression, sRGB)
    'T_Sand_Color': ('TC_DEFAULT', True), 'T_Sand_Normal': ('TC_MASKS', False),
    'T_BallDimples': ('TC_MASKS', False),
    'T_Turf': ('TC_GRAYSCALE', False), 'T_RoughTurf': ('TC_GRAYSCALE', False), 'T_Macro': ('TC_GRAYSCALE', False),
}


def import_textures():
    for name, (compression, srgb) in SURFACE_TEXTURES.items():
        texture = _import(TEXTURE_SOURCE / f'{name}.png', TEXTURE_DEST)
        assert texture, f'{name}.png did not import (run Art/Blender/surface_textures.py)'
        texture.set_editor_property('srgb', srgb)
        texture.set_editor_property('compression_settings', getattr(unreal.TextureCompressionSettings, compression))
        unreal.EditorAssetLibrary.save_loaded_asset(texture)
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


# HLSL for each surface kind: returns the base colour (linear). Inputs, all plain floats:
#   M1 M2 M3  patchy large-scale noise at 37 m / 11 m / 4 m      D  mown-grass detail    R  long-grass detail
#   VC  vertex colour (B = footpath)   H  hole-local metres (x down the hole)   E  metres to (x) bunker edge, (y) fairway/green edge
#   SC  sand colour   L8  world metres within an 8 m tile   ZL  0..1 up every 12 cm of height   N  world normal   Tint, Stripes
SURFACE_CODE = {
    'rough': """
float3 c = lerp(float3(0.020, 0.058, 0.009), float3(0.050, 0.080, 0.013), saturate(M1 * 2.2 - 0.6));
c = lerp(c, float3(0.016, 0.052, 0.022), saturate(M2 * 2.0 - 0.9) * 0.7);
c *= (0.78 + 0.44 * M3) * (0.55 + 0.6 * R);
float cut = 1 - smoothstep(1.0, 2.2, E.y);
c = lerp(c, float3(0.050, 0.140, 0.022) * (0.8 + 0.3 * D), cut * 0.75);
c *= 1 - 0.3 * (1 - smoothstep(0.0, 0.7, E.x));
c *= Tint.rgb;
return lerp(c, float3(0.23, 0.16, 0.09) * (0.75 + 0.3 * D), smoothstep(0.1, -0.06, P.x + (D - 0.8) * 0.25) * saturate(VC.b * 3.0));
""",
    'fairway': """
float3 c = float3(0.058, 0.165, 0.026);
c = lerp(c, float3(0.078, 0.172, 0.020), saturate(M1 * 2.2 - 0.6) * 0.6);
c = lerp(c, float3(0.045, 0.150, 0.036), saturate(M2 * 2.0 - 0.9) * 0.5);
c *= (0.88 + 0.24 * M3) * (0.72 + 0.36 * D);
float s = smoothstep(0.4, 0.6, abs(frac(H.y / 10.0) - 0.5) * 2);
c *= lerp(1 - Stripes, 1 + Stripes, s);
c *= 1 - 0.08 * (1 - smoothstep(0.3, 0.9, E.y));
c = lerp(c, float3(0.035, 0.095, 0.015) * (0.6 + 0.6 * R), (1 - smoothstep(0.0, 0.6, E.x)) * 0.7);
c *= Tint.rgb;
return lerp(c, float3(0.23, 0.16, 0.09) * (0.75 + 0.3 * D), smoothstep(0.1, -0.06, P.x + (D - 0.8) * 0.25) * saturate(VC.b * 3.0));
""",
    'green': """
float3 c = float3(0.070, 0.215, 0.034);
c = lerp(c, float3(0.085, 0.215, 0.030), saturate(M2 * 2.0 - 0.8) * 0.4);
c *= (0.93 + 0.14 * M3) * (0.86 + 0.18 * D);
float a = smoothstep(0.4, 0.6, abs(frac((H.x + H.y) / 6.0) - 0.5) * 2);
float b = smoothstep(0.4, 0.6, abs(frac((H.x - H.y) / 6.0) - 0.5) * 2);
c *= 1 + Stripes * 0.6 * ((a - 0.5) + (b - 0.5));
float collar = 1 - smoothstep(0.7, 1.0, E.y);
float3 fringe = float3(0.055, 0.170, 0.028) * (0.8 + 0.3 * D);
c = lerp(c, fringe * lerp(1 - Stripes, 1 + Stripes, a), collar);
c = lerp(c, float3(0.035, 0.095, 0.015) * (0.6 + 0.6 * R), (1 - smoothstep(0.0, 0.5, E.x)) * 0.6);
return c * Tint.rgb;
""",
    'tee': """
float3 c = float3(0.062, 0.180, 0.028);
c *= (0.9 + 0.2 * M3) * (0.8 + 0.3 * D);
float s = smoothstep(0.4, 0.6, abs(frac(H.x / 4.0) - 0.5) * 2);
c *= lerp(1 - Stripes, 1 + Stripes, s);
c *= Tint.rgb;
return lerp(c, float3(0.23, 0.16, 0.09) * (0.75 + 0.3 * D), smoothstep(0.1, -0.06, P.x + (D - 0.8) * 0.25) * saturate(VC.b * 3.0));
""",
    'bunker': """
float3 c = SC * (0.9 + 0.2 * M3);
float2 dir = float2(0.8, 0.6);
float wob = (M3 - 0.5) * 1.2;
float rake = sin((dot(L8, dir) + wob) * 39.27);
c *= 1 + 0.07 * rake * saturate(M2 * 3.0 - 1.2);
float slope = 1 - saturate(N.z);
float lip = 1 - smoothstep(0.0, 0.6, E.x);
c *= 1 - 0.2 * lip;
float wall = saturate((slope - 0.25) * 3.0) * (1 - smoothstep(0.0, 0.5, E.x));
float3 sod = lerp(float3(0.06, 0.045, 0.028), float3(0.10, 0.08, 0.045), step(0.5, ZL));
c = lerp(c, sod, wall * 0.85);
c = lerp(c, float3(0.045, 0.11, 0.02), (1 - smoothstep(0.0, 0.12, E.x)) * 0.7);
return c * Tint.rgb;
""",
}
SAND_NORMAL_CODE = """
float3 n = SN * 2 - 1;
float2 dir = float2(0.8, 0.6);
float wob = (M3 - 0.5) * 1.2;
float ridge = cos((dot(L8, dir) + wob) * 39.27) * saturate(M2 * 3.0 - 1.2) * 0.25;
return normalize(N + float3(n.x * 0.6 + dir.x * ridge, n.y * 0.6 + dir.y * ridge, 0));
"""
SURFACE_TINT = {'rough': (1, 1, 1), 'fairway': (1, 1, 1), 'green': (1, 1, 1), 'tee': (1, 1, 1),
                'bunker': (0.72, 0.64, 0.52)}  # sand: a touch warmer / darker than the raw texture


def _tex(mat, name, uv, x, y, sampler=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE):
    node = _expr(mat, unreal.MaterialExpressionTextureSample, x, y, texture=unreal.load_asset(f'{TEXTURE_DEST}/{name}'),
                 sampler_type=sampler)
    lib.connect_material_expressions(uv, '', node, 'UVs')
    return node


def _world_uv(mat, metres, x, y, offset=0.0):
    """World XY / (metres per tile), for textures laid over every island alike."""
    position = _expr(mat, unreal.MaterialExpressionWorldPosition, x - 450, y)
    mask = _expr(mat, unreal.MaterialExpressionComponentMask, x - 300, y, r=True, g=True, b=False, a=False)
    lib.connect_material_expressions(position, '', mask, '')
    scaled = _mul(mat, mask, '', _const(mat, 1.0 / (100.0 * metres), x - 300, y + 60), '', x - 150, y)
    return _add(mat, scaled, _const(mat, offset, x - 150, y + 60), x, y) if offset else scaled


def _custom(mat, code, inputs, x, y, output=unreal.CustomMaterialOutputType.CMOT_FLOAT3):
    node = _expr(mat, unreal.MaterialExpressionCustom, x, y)
    node.set_editor_property('code', code)
    node.set_editor_property('output_type', output)
    pins = []
    for name in inputs:
        pin = unreal.CustomInput()
        pin.set_editor_property('input_name', name)
        pins.append(pin)
    node.set_editor_property('inputs', pins)
    for name, (source, out) in inputs.items():
        lib.connect_material_expressions(source, out, node, name)
    return node


def _surface_inputs(mat, kind):
    """The plain-float feeds every surface kind reads (see SURFACE_CODE)."""
    gray = unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE
    feeds = {
        'M1': (_tex(mat, 'T_Macro', _world_uv(mat, 37, -1600, -600), -1350, -600), 'R'),
        'M2': (_tex(mat, 'T_Macro', _world_uv(mat, 11, -1600, -400, 0.37), -1350, -400), 'R'),
        'M3': (_tex(mat, 'T_Macro', _world_uv(mat, 4.3, -1600, -200, 0.71), -1350, -200), 'R'),
        'D': (_tex(mat, 'T_Turf', _world_uv(mat, 1.1, -1600, 0), -1350, 0, gray), 'R'),
        'R': (_tex(mat, 'T_RoughTurf', _world_uv(mat, 0.8, -1600, 200), -1350, 200, gray), 'R'),
        'VC': (_expr(mat, unreal.MaterialExpressionVertexColor, -1350, 400), ''),
        'H': (_expr(mat, unreal.MaterialExpressionTextureCoordinate, -1350, 550, coordinate_index=1), ''),
        'E': (_expr(mat, unreal.MaterialExpressionTextureCoordinate, -1350, 650, coordinate_index=2), ''),
        'P': (_expr(mat, unreal.MaterialExpressionTextureCoordinate, -1350, 700, coordinate_index=3), ''),
        'N': (_expr(mat, unreal.MaterialExpressionVertexNormalWS, -1350, 750), ''),
        'Tint': (_expr(mat, unreal.MaterialExpressionVectorParameter, -1350, 850, parameter_name='Tint',
                       default_value=unreal.LinearColor(*SURFACE_TINT[kind], 1.0)), ''),
        'Stripes': (_expr(mat, unreal.MaterialExpressionScalarParameter, -1350, 1000, parameter_name='StripeStrength',
                          default_value=0.12 if kind in ('fairway', 'tee') else 0.08), ''),
    }
    if kind == 'bunker':
        feeds['SC'] = (_tex(mat, 'T_Sand_Color', _world_uv(mat, 0.9, -1600, 1150), -1350, 1150,
                            unreal.MaterialSamplerType.SAMPLERTYPE_COLOR), 'RGB')
        feeds['SN'] = (_tex(mat, 'T_Sand_Normal', _world_uv(mat, 0.9, -1600, 1350), -1350, 1350,
                            unreal.MaterialSamplerType.SAMPLERTYPE_MASKS), 'RGB')
        local = _expr(mat, unreal.MaterialExpressionFrac, -1450, 1550)
        lib.connect_material_expressions(_world_uv(mat, 8, -1600, 1550), '', local, '')
        feeds['L8'] = (_mul(mat, local, '', _const(mat, 8.0, -1450, 1610), '', -1350, 1550), '')
        position = _expr(mat, unreal.MaterialExpressionWorldPosition, -1900, 1750)
        height = _expr(mat, unreal.MaterialExpressionComponentMask, -1750, 1750, r=False, g=False, b=True, a=False)
        lib.connect_material_expressions(position, '', height, '')
        layers = _expr(mat, unreal.MaterialExpressionFrac, -1450, 1750)
        lib.connect_material_expressions(_mul(mat, height, '', _const(mat, 1.0 / 12.0, -1750, 1810), '', -1600, 1750), '', layers, '')
        feeds['ZL'] = (layers, '')
    return feeds


def surface_material(name, kind, roughness, physical):
    """Island surface: base colour from SURFACE_CODE[kind]; sand also gets a world-space normal (grains, rake lines)."""
    mat = _material(name)
    feeds = _surface_inputs(mat, kind)
    used = {k: v for k, v in feeds.items() if k in SURFACE_CODE[kind] or k in ('VC',)}
    colour = _custom(mat, SURFACE_CODE[kind], used, -700, 0)
    lib.connect_material_property(colour, '', unreal.MaterialProperty.MP_BASE_COLOR)
    lib.connect_material_property(_const(mat, roughness, -400, 400), '', unreal.MaterialProperty.MP_ROUGHNESS)
    if kind == 'bunker':
        mat.set_editor_property('tangent_space_normal', False)
        normal = _custom(mat, SAND_NORMAL_CODE, {k: feeds[k] for k in ('SN', 'N', 'L8', 'M2', 'M3')}, -700, 400)
        lib.connect_material_property(normal, '', unreal.MaterialProperty.MP_NORMAL)
    return _finish(mat, physical)


GRASS_BLADES_CODE = """
float3 c = lerp(float3(0.034, 0.092, 0.014), float3(0.080, 0.120, 0.020), saturate(M1 * 2.2 - 0.6));
c = lerp(c, float3(0.025, 0.080, 0.035), saturate(M2 * 2.0 - 0.9) * 0.7);
c *= 0.75 + 0.5 * VC.g;
c = lerp(c, c * float3(1.3, 1.12, 0.75), PIR * 0.55);
c *= lerp(0.4, 1.2, VC.r);
return c * Tint.rgb;
"""


def grass_blades_material():
    """M_GrassBlades: two-sided, dark at the root, lighter toward the tip, every clump its own shade, and the same
    patchy large-scale colour as the rough under it."""
    mat = _material('M_GrassBlades')
    mat.set_editor_property('two_sided', True)
    # The grass is instanced at runtime: without this flag the game can't compile it and shows grey blades.
    mat.set_editor_property('used_with_instanced_static_meshes', True)
    feeds = {
        'M1': (_tex(mat, 'T_Macro', _world_uv(mat, 37, -1600, -600), -1350, -600), 'R'),
        'M2': (_tex(mat, 'T_Macro', _world_uv(mat, 11, -1600, -400, 0.37), -1350, -400), 'R'),
        'VC': (_expr(mat, unreal.MaterialExpressionVertexColor, -1350, -200), ''),
        'PIR': (_expr(mat, unreal.MaterialExpressionPerInstanceRandom, -1350, 0), ''),
        'Tint': (_expr(mat, unreal.MaterialExpressionVectorParameter, -1350, 200, parameter_name='Tint',
                       default_value=unreal.LinearColor(1, 1, 1, 1)), ''),
    }
    colour = _custom(mat, GRASS_BLADES_CODE, feeds, -700, 0)
    lib.connect_material_property(colour, '', unreal.MaterialProperty.MP_BASE_COLOR)
    lib.connect_material_property(_const(mat, 0.85, -400, 300), '', unreal.MaterialProperty.MP_ROUGHNESS)
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


DEBRIS_CODE = """
float3 green = float3(0.06, 0.16, 0.02);
float3 yellow = float3(0.42, 0.32, 0.05);
float3 brown = float3(0.20, 0.10, 0.035);
float3 c = PIR < 0.4 ? lerp(green, yellow, PIR / 0.4) : lerp(yellow, brown, (PIR - 0.4) / 0.6);
return c * lerp(0.7, 1.1, VC.r);
"""


def debris_material():
    """M_WindDebris: two-sided; each leaf or straw its own shade from green through yellow to brown."""
    mat = _material('M_WindDebris')
    mat.set_editor_property('two_sided', True)
    mat.set_editor_property('used_with_instanced_static_meshes', True)
    feeds = {'VC': (_expr(mat, unreal.MaterialExpressionVertexColor, -1000, 0), ''),
             'PIR': (_expr(mat, unreal.MaterialExpressionPerInstanceRandom, -1000, 200), '')}
    colour = _custom(mat, DEBRIS_CODE, feeds, -600, 0)
    lib.connect_material_property(colour, '', unreal.MaterialProperty.MP_BASE_COLOR)
    lib.connect_material_property(_const(mat, 0.8, -400, 300), '', unreal.MaterialProperty.MP_ROUGHNESS)
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


BALL_NORMAL_CODE = """
float3 n = SN * 2 - 1;
n.xy *= 0.8;
return normalize(n);
"""


def make_golf_ball():
    """M_GolfBall in /Game/Course/Ball: glossy white with hex-packed dimples (the ball loads it by path)."""
    path = '/Game/Course/Ball'
    name = 'M_GolfBall'
    mat = unreal.load_asset(f'{path}/{name}') if unreal.EditorAssetLibrary.does_asset_exist(f'{path}/{name}') else \
        tools.create_asset(name, path, unreal.Material, unreal.MaterialFactoryNew())
    lib.delete_all_material_expressions(mat)
    white = _expr(mat, unreal.MaterialExpressionConstant3Vector, -500, 0, constant=unreal.LinearColor(0.86, 0.86, 0.84, 1))
    lib.connect_material_property(white, '', unreal.MaterialProperty.MP_BASE_COLOR)
    lib.connect_material_property(_const(mat, 0.3, -500, 150), '', unreal.MaterialProperty.MP_ROUGHNESS)
    lib.connect_material_property(_const(mat, 0.6, -500, 250), '', unreal.MaterialProperty.MP_SPECULAR)
    uv = _expr(mat, unreal.MaterialExpressionTextureCoordinate, -1200, 400, u_tiling=8.0, v_tiling=4.6)
    dimples = _tex(mat, 'T_BallDimples', uv, -1000, 400, unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    normal = _custom(mat, BALL_NORMAL_CODE, {'SN': (dimples, 'RGB')}, -600, 400)
    lib.connect_material_property(normal, '', unreal.MaterialProperty.MP_NORMAL)
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


GRASS_SOURCE = ROOT / 'Art' / 'Exports' / 'Grass'
GRASS_DEST = '/Game/Course/Grass'


def import_grass():
    """The 3D grass clumps (Art/Blender/build_grass.py) and their material. ASkyLinksGrass grows them in game."""
    import_textures()
    make_golf_ball()
    blades = grass_blades_material()
    debris = debris_material()
    for name in ('SM_GrassClump', 'SM_GrassTuft', 'SM_WindLeaf', 'SM_WindStraw'):
        mat = debris if name.startswith('SM_Wind') else blades
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
        data.set_editor_property('normal_import_method', unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        mesh = _import(GRASS_SOURCE / f'{name}.fbx', GRASS_DEST, options)
        assert isinstance(mesh, unreal.StaticMesh), f'{name}.fbx did not import'
        mesh.set_material(0, mat)
        body = mesh.get_editor_property('body_setup')
        if body:
            body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    print(f'GRASS ready in {GRASS_DEST}: press Play to see it grow on the rough and along the bunker lips, and leaves blow in the wind')


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
    materials = {slot: surface_material(*spec) for slot, spec in GRASS.items()}
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
    if name.endswith('_IslandTop') or '_Floater' in name:
        # UV1 holds hole-local metres (hundreds): half-float UVs would make the mowing stripes jagged.
        meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        build = meshes.get_lod_build_settings(mesh, 0)
        build.set_editor_property('use_full_precision_u_vs', True)
        meshes.set_lod_build_settings(mesh, 0, build)
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


def place_leaderboard(number, spot, everything):
    """The live leaderboard (SkyLinksLeaderboard C++ actor) on the stadium's screen beside the 18th green."""
    if not hasattr(unreal, 'SkyLinksLeaderboard'):
        print('LEADERBOARD skipped: rebuild the C++ first (Build.bat)')
        return
    for actor in everything:
        if actor.get_actor_label() == 'Leaderboard':
            actors.destroy_actor(actor)
    x, y, z, yaw = spot
    board = actors.spawn_actor_from_class(unreal.SkyLinksLeaderboard, unreal.Vector(x * M, y * M, z * M), unreal.Rotator(0, 0, yaw))
    board.set_actor_label('Leaderboard')
    board.set_folder_path(f'Course/Hole{number:02d}')


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
    if spots.get('leaderboard'):
        place_leaderboard(number, spots['leaderboard'], everything)
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


# Fab "Bridge" (TAKOYTO): 2 m wide, 8.6 m long along its Y axis. Exported to /Game/Fab/Bridge (with its textures);
# an earlier export without textures landed in /Game/Course/Vegetation.
FAB_FOLDERS = ('/Game/Fab/Bridge', '/Game/Course/Vegetation')


def _fab(name):
    for folder in FAB_FOLDERS:
        asset = unreal.load_asset(f'{folder}/{name}') if unreal.EditorAssetLibrary.does_asset_exist(f'{folder}/{name}') else None
        if asset:
            return asset
    return None
FOOTBRIDGE_WIDTH = 3.0                           # m, as Art/Blender/build_course_islands.py (so the buggy fits)


def footbridge_wood():
    """Warm painted-wood material for the Fab bridge when its own textures didn't come through (it shows white)."""
    path = f'{MAT_DIR}/M_Footbridge_Wood'
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.load_asset(path)
    mat = _material('M_Footbridge_Wood')
    base = _expr(mat, unreal.MaterialExpressionConstant3Vector, -800, -100, constant=unreal.LinearColor(0.34, 0.2, 0.1, 1))
    texture = _expr(mat, unreal.MaterialExpressionTextureSample, -800, 150,
                    texture=unreal.load_asset(f'{TEXTURE_DEST}/T_RockDetail'),
                    sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)
    result = _mul(mat, base, '', texture, 'R', -500, 0)
    lib.connect_material_property(result, '', unreal.MaterialProperty.MP_BASE_COLOR)
    lib.connect_material_property(_const(mat, 0.85, -500, 250), '', unreal.MaterialProperty.MP_ROUGHNESS)
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat




def footbridge_fab_material():
    """M_Footbridge_Fab from the Fab textures (Bridge_BaseColor, Bridge_Normal), or None until they're imported."""
    colour = _fab('Bridge_BaseColor')
    normal = _fab('Bridge_Normal')
    if not isinstance(colour, unreal.Texture2D):
        return None
    for texture in (colour, normal):
        if isinstance(texture, unreal.Texture2D):
            texture.set_editor_property('max_texture_size', 2048)  # 4K is more than a footbridge needs (phones)
    if isinstance(normal, unreal.Texture2D):
        normal.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP)
        normal.set_editor_property('srgb', False)
    for texture in (colour, normal):
        if isinstance(texture, unreal.Texture2D):
            unreal.EditorAssetLibrary.save_loaded_asset(texture)
    mat = _material('M_Footbridge_Fab')
    base = _expr(mat, unreal.MaterialExpressionTextureSample, -600, 0, texture=colour)
    lib.connect_material_property(base, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR)
    if isinstance(normal, unreal.Texture2D):
        bump = _expr(mat, unreal.MaterialExpressionTextureSample, -600, 300, texture=normal,
                     sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        lib.connect_material_property(bump, 'RGB', unreal.MaterialProperty.MP_NORMAL)
    lib.connect_material_property(_const(mat, 0.8, -600, 550), '', unreal.MaterialProperty.MP_ROUGHNESS)
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


def place_footbridges(number, spots, deck_offset_cm=0.0, wood=True):
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
    mesh = _fab('Bridge1')
    if not mesh or not spots.get('footbridges'):
        return
    # The Fab bridge's own textures when they've been imported, otherwise the painted-wood stand-in.
    look = footbridge_fab_material() or (footbridge_wood() if wood else None)
    box = mesh.get_bounding_box()
    width_cm, length_cm = box.max.x - box.min.x, box.max.y - box.min.y
    for i, (x, y, z, yaw, length) in enumerate(spots['footbridges']):
        # The mesh runs along its Y axis: turn it a quarter so Y follows the crossing; overlap the banks a little.
        bridge = actors.spawn_actor_from_object(mesh, unreal.Vector(x * M, y * M, z * M + deck_offset_cm), unreal.Rotator(0, 0, yaw - 90.0))
        bridge.set_actor_scale3d(unreal.Vector(FOOTBRIDGE_WIDTH * M / width_cm, (length + 1.5) * M / length_cm, 1.0))
        bridge.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        if look:
            for slot in range(bridge.static_mesh_component.get_num_materials()):
                bridge.static_mesh_component.set_material(slot, look)
        bridge.set_actor_label(f'Footbridge{number:02d}_{i + 1}')
        bridge.set_folder_path(folder)


def fab_footbridges(deck_offset_cm=0.0, wood=True, holes=HOLES):
    """Swap every footbridge for the Fab bridge: re-imports the decks (SM_Hnn_Props), hides them, places the
    bridges. deck_offset_cm lifts (+) or sinks (-) the Fab bridges if their deck doesn't meet the drive height.
    wood=True paints them with M_Footbridge_Wood; wood=False keeps the Fab material (once its textures import)."""
    materials = build_materials()
    for number in holes:
        spots_path = SOURCE / f'Hole{number:02d}_spots.json'
        if not spots_path.is_file():
            continue
        spots = json.loads(spots_path.read_text())
        if not spots.get('footbridges'):
            continue
        import_mesh(f'SM_H{number:02d}_Props', materials)
        place_footbridges(number, spots, deck_offset_cm, wood)
        print(f"FOOTBRIDGES hole {number}: {len(spots['footbridges'])}")
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()


def export_paths(default_width_m=3.0):
    """Save every footpath drawn in the level to Art/Exports/Islands/Paths.json for the island builder.

    Draw a path: Place Actors > Empty Actor, name it Path... (e.g. Path_H04_a), Details > + Add > Spline, then drag
    the spline's points over the grass (Alt+drag a point adds the next one). Optional width: add the actor tag
    'width=4' (metres). Push the json; build_course_islands.py bakes the paths into the island tops (crisp edges)."""
    paths = []
    for actor in _all():
        if not actor.get_actor_label().lower().startswith('path'):
            continue
        spline = actor.get_component_by_class(unreal.SplineComponent)
        if not spline:
            print(f'PATHS: {actor.get_actor_label()} has no Spline component, skipped')
            continue
        width = default_width_m
        for tag in actor.tags:
            if str(tag).lower().startswith('width='):
                width = float(str(tag).split('=')[1])
        # Sample the curve every metre so bends stay round.
        length = spline.get_spline_length()
        steps = max(2, int(length / 100.0) + 1)
        points = []
        for i in range(steps + 1):
            p = spline.get_location_at_distance_along_spline(length * i / steps, unreal.SplineCoordinateSpace.WORLD)
            points.append([round(p.x / M, 3), round(p.y / M, 3), round(p.z / M, 3)])
        paths.append({'name': actor.get_actor_label(), 'width': width, 'points': points})
    out = SOURCE / 'Paths.json'
    out.write_text(json.dumps({'paths': paths}, indent=1) + '\n')
    print(f'PATHS: {len(paths)} saved to {out} (commit and push it)')


def make_path_decal():
    """M_PathDecal: a dirt footpath for Decal Actors. Soft sides and ends, so pieces laid end to end or overlapped
    blend into one path. Place Actors > Decal Actor, set its Decal Material to this, then scale / rotate it."""
    mat = _material('M_PathDecal')
    mat.set_editor_property('material_domain', unreal.MaterialDomain.MD_DEFERRED_DECAL)
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_TRANSLUCENT)
    uv = _expr(mat, unreal.MaterialExpressionTextureCoordinate, -1400, 300)

    def fade(channel, x, y, sharp):
        # 1 in the middle, 0 at the edge: 1 - |2 * uv - 1| ^ sharp
        mask = _expr(mat, unreal.MaterialExpressionComponentMask, x, y, r=channel == 'R', g=channel == 'G', b=False, a=False)
        lib.connect_material_expressions(uv, '', mask, '')
        centred = _add(mat, _mul(mat, mask, '', _const(mat, 2.0, x, y + 60), '', x + 150, y), _const(mat, -1.0, x + 150, y + 60), x + 300, y)
        dist = _expr(mat, unreal.MaterialExpressionAbs, x + 450, y)
        lib.connect_material_expressions(centred, '', dist, '')
        power = _expr(mat, unreal.MaterialExpressionPower, x + 600, y)
        lib.connect_material_expressions(dist, '', power, 'Base')
        lib.connect_material_expressions(_const(mat, sharp, x + 450, y + 60), '', power, 'Exp')
        return _add(mat, _mul(mat, power, '', _const(mat, -1.0, x + 600, y + 60), '', x + 750, y), _const(mat, 1.0, x + 750, y + 60), x + 900, y)
    across = fade('G', -1400, 450, 4.0)   # soft sides
    along = fade('R', -1400, 650, 8.0)    # softer only right at the ends
    opacity = _mul(mat, across, '', along, '', -300, 550)
    grit = _expr(mat, unreal.MaterialExpressionTextureSample, -800, 0, texture=unreal.load_asset(f'{TEXTURE_DEST}/T_SandDetail'),
                 sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE)
    dirt = _expr(mat, unreal.MaterialExpressionConstant3Vector, -800, -150, constant=unreal.LinearColor(*PATH_COLOUR, 1.0))
    lib.connect_material_property(_mul(mat, dirt, '', grit, 'R', -500, 0), '', unreal.MaterialProperty.MP_BASE_COLOR)
    lib.connect_material_property(_const(mat, 0.95, -500, 200), '', unreal.MaterialProperty.MP_ROUGHNESS)
    lib.connect_material_property(opacity, '', unreal.MaterialProperty.MP_OPACITY)
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    print(f'PATH DECAL ready: {MAT_DIR}/M_PathDecal')
    return mat


KEEP_TREES = set()  # holes whose trees the owner arranged by hand: refresh_islands leaves their foliage alone


def refresh_islands(holes=HOLES, bridges=True):
    """After a rebuild of the island meshes (new bunkers, buggy paths...): re-import every hole's surface, rock,
    ivy, water and footbridge deck in place, re-seat the holes, footbridges and rope bridges, and replant the
    trees island by island (clear of the new paths and bunkers). Holes in KEEP_TREES (hole 1, arranged by hand)
    keep their trees. Your moved floating islands, the fog and the sea stay as they are."""
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    materials = build_materials()
    types = _foliage_types()
    for number in holes:
        spots_path = SOURCE / f'Hole{number:02d}_spots.json'
        if not spots_path.is_file():
            continue
        spots = json.loads(spots_path.read_text())
        for part in PARTS:
            name = f'SM_H{number:02d}_{part}'
            if not (SOURCE / f'{name}.fbx').is_file():
                continue
            is_new = not unreal.EditorAssetLibrary.does_asset_exist(f'{DEST}/{name}')
            mesh = import_mesh(name, materials, part not in NO_COLLISION)
            if is_new:  # a part this island didn't have before (the 18th's stadium): put it in the level too
                place(mesh, f'{part}{number:02d}', f'Course/Hole{number:02d}/Islands', part not in NO_COLLISION)
        place_hole(number, spots)
        place_footbridges(number, spots)
        if number in KEEP_TREES or not spots.get('land_outline'):
            print(f'HOLE {number} refreshed (trees kept)')
            continue
        # Only this island's trees go (inside its outline); every other island keeps its own.
        outline = [unreal.Vector2D(x * M, y * M) for x, y in spots['land_outline']]
        removed = unreal.SkyLinksForest.clear_foliage_inside(world, types, outline)
        plant_forest(number, spots)
        print(f'HOLE {number} refreshed: {removed} old trees out, new ones planted')
        unreal.SystemLibrary.collect_garbage()  # free each hole's imports before the next (big batches ran out of memory)
    if bridges:
        apply_bridges(materials, json.loads((SOURCE / 'Course_links.json').read_text()))
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print('ISLANDS REFRESHED. Run validate_course() in a separate call.')


def _surface_tag(number):
    import hashlib
    text = (SOURCE / f'Hole{number:02d}_spots.json').read_text()
    return 'Surface:' + hashlib.md5(text.encode()).hexdigest()[:10]


def refresh_remaining(per_run=3):
    """Crash-proof refresh: does the next few holes that aren't up to date yet (each is saved as soon as it is
    done and marked on its GolfHole), then stops. Run it again, and again, until it says ALL DONE; after a crash just
    reopen the editor and run it again - it carries on where it got to. The rope bridges go in on the last run."""
    everything = _all()
    pending = []
    for number in HOLES:
        golf_hole = next((a for a in everything if a.get_actor_label() == f'GolfHole{number:02d}'), None)
        if golf_hole and _surface_tag(number) not in [str(t) for t in golf_hole.tags]:
            pending.append((number, golf_hole))
    if not pending:
        apply_bridges(build_materials(), json.loads((SOURCE / 'Course_links.json').read_text()))
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
        print('ALL DONE: every hole is up to date and the rope bridges are in. Run validate_course() next.')
        return
    for number, golf_hole in pending[:per_run]:
        refresh_islands([number], bridges=False)
        golf_hole.modify()
        golf_hole.set_editor_property('tags', [t for t in golf_hole.tags if not str(t).startswith('Surface:')] + [unreal.Name(_surface_tag(number))])
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
        unreal.SystemLibrary.collect_garbage()
    left = len(pending) - min(per_run, len(pending))
    print(f'REFRESHED holes {[n for n, _ in pending[:per_run]]}. {left} still to do: run isl.refresh_remaining() again.')


def reimport_tops(holes=HOLES):
    """Re-import only the island surfaces (SM_Hnn_IslandTop), e.g. after footpaths are baked in. The placed
    actors pick up the new meshes; floaters, trees, bridges and everything you've moved stay as they are."""
    materials = build_materials()
    for number in holes:
        if (SOURCE / f'SM_H{number:02d}_IslandTop.fbx').is_file():
            import_mesh(f'SM_H{number:02d}_IslandTop', materials)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print(f'TOPS re-imported: holes {list(holes)}')


def update_surfaces(holes=HOLES):
    """New island surfaces + materials, and nothing in the level moves: re-imports each hole's IslandTop and
    floating island meshes (the actors pick them up where they are) and rebuilds the materials. Trees, paths,
    decals, bridges and everything placed by hand stay exactly as they are. Run it in batches if memory is short:
    update_surfaces(range(1, 7)), then range(7, 13), then range(13, 19)."""
    materials = build_materials()
    count = 0
    for number in holes:
        paths = [SOURCE / f'SM_H{number:02d}_IslandTop.fbx'] + sorted(SOURCE.glob(f'SM_H{number:02d}_Floater*.fbx'))
        for path in paths:
            if path.is_file() and unreal.EditorAssetLibrary.does_asset_exist(f'{DEST}/{path.stem}'):
                import_mesh(path.stem, materials)
                count += 1
                unreal.SystemLibrary.collect_garbage()  # free each import before the next (large batches ran out of memory)
        print(f'SURFACES hole {number} done')
    print(f'SURFACES updated: {count} meshes re-imported (holes {list(holes)}), materials rebuilt. Nothing in the level was moved.')


def tune_look(exposure=-1.0, saturation=1.15, contrast=1.05):
    """One unbound post-process volume (Course/Environment/CourseLook) that tames the automatic exposure (the sun
    on pale grass and sand washed everything out) and gives the colours a little more punch. Run again with other
    numbers to adjust, e.g. tune_look(-1.5) for darker, tune_look(-0.5) for brighter."""
    volume = next((a for a in _all() if a.get_actor_label() == 'CourseLook'), None)
    if not volume:
        volume = actors.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        volume.set_actor_label('CourseLook')
        volume.set_folder_path('Course/Environment')
    volume.set_editor_property('unbound', True)
    volume.set_editor_property('priority', 10.0)
    settings = volume.get_editor_property('settings')
    for key, value in (('override_auto_exposure_bias', True), ('auto_exposure_bias', float(exposure)),
                       ('override_color_saturation', True), ('color_saturation', unreal.Vector4(saturation, saturation, saturation, 1.0)),
                       ('override_color_contrast', True), ('color_contrast', unreal.Vector4(contrast, contrast, contrast, 1.0))):
        settings.set_editor_property(key, value)
    volume.set_editor_property('settings', settings)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print(f'LOOK set: exposure {exposure}, saturation {saturation}, contrast {contrast}')


def lift_floaters(clearance=45.0):
    """After the holes changed height, lift any floating island that now hangs too close over a course: each one's
    underside ends up at least `clearance` metres above the ground below it. Ones already high enough don't move
    (nor sideways, so your hand placement stays)."""
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    lifted = 0
    for actor in _all():
        if not str(actor.get_folder_path()).endswith('/Floaters'):
            continue
        origin, extent = actor.get_actor_bounds(False)
        bottom = unreal.Vector(origin.x, origin.y, origin.z - extent.z - 10)
        hit = unreal.SystemLibrary.line_trace_single(world, bottom, bottom - unreal.Vector(0, 0, 200000),
                                                     unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [actor],
                                                     unreal.DrawDebugTrace.NONE, True)
        if not hit:
            continue
        parts = hit.to_tuple()
        if not parts[0]:
            continue
        gap = parts[3] / M
        if gap < clearance:
            p = actor.get_actor_location()
            actor.set_actor_location(unreal.Vector(p.x, p.y, p.z + (clearance - gap) * M), False, True)
            lifted += 1
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print(f'FLOATERS: {lifted} lifted to at least {clearance:.0f} m above the course')


def finish_course():
    """Everything after an island rebuild, in one go: new materials, every island refreshed (each saved as it is
    done, so after a crash just run this again and it carries on), floating islands lifted clear, bridges in,
    course checked and saved."""
    update_materials()
    for _ in range(len(HOLES) + 2):
        pending = [n for n in HOLES if (lambda g: g and _surface_tag(n) not in [str(t) for t in g.tags])(
            next((a for a in _all() if a.get_actor_label() == f'GolfHole{n:02d}'), None))]
        refresh_remaining(per_run=2)
        if not pending:
            break
    lift_floaters()
    validate_course()
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print('COURSE FINISHED: all islands refreshed, floaters lifted, course checked and saved.')


def update_materials():
    """Rebuild the island materials only (nothing in the level moves), e.g. after a material change."""
    build_materials()
    print('MATERIALS rebuilt')


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
    apply_portals(materials, links)  # the islands are linked by portals now (no bridges in Course_links.json)


SWIRL_CODE = """
float2 p = UV - 0.5;
float r = length(p) * 2.0;
float a = atan2(p.y, p.x);
float s1 = sin(a * 3.0 + r * 10.0 - T * 2.2) * 0.5 + 0.5;
float s2 = sin(a * 5.0 - r * 7.0 + T * 1.3) * 0.5 + 0.5;
float glow = pow(saturate(1.0 - r), 0.6);
float3 deep = float3(0.04, 0.12, 0.55);
float3 bright = float3(0.3, 0.95, 1.4);
float3 swirl = lerp(deep, bright, s1 * 0.7 + s2 * 0.3) * (0.6 + 1.6 * glow);
// With a picture of the next hole: clear in the middle, the whirlpool closing in towards the rim.
float veil = saturate(pow(r, 1.8) * 1.1 + (s1 * 0.7 + s2 * 0.3) * 0.22 - 0.08);
float3 through = View * 1.15 * (1.0 + 0.08 * sin(r * 30.0 - T * 4.0));
float3 c = lerp(swirl, lerp(through, swirl, veil), ShowView);
return c + float3(1.2, 1.4, 1.6) * pow(saturate(1.0 - r), 6.0) * (1.0 - 0.8 * ShowView);
"""

VIEW_UV_CODE = """
return float2(UV.x, 1.0 - UV.y);
"""


def swirl_material():
    """M_PortalSwirl: the glowing, slowly turning whirlpool inside each portal ring (unlit, both sides). With the
    View texture (a picture of the next hole, from isl.portal_views()) and ShowView 1 you see the next tee through
    the middle of it."""
    mat = _material('M_PortalSwirl')
    mat.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property('two_sided', True)
    uv = _expr(mat, unreal.MaterialExpressionTextureCoordinate, -1100, 0)
    flipped = _custom(mat, VIEW_UV_CODE, {'UV': (uv, '')}, -900, 250, output=unreal.CustomMaterialOutputType.CMOT_FLOAT2)
    view = _expr(mat, unreal.MaterialExpressionTextureSampleParameter2D, -700, 250, parameter_name='View',
                 texture=unreal.load_asset(f'{TEXTURE_DEST}/T_Macro'),
                 sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    lib.connect_material_expressions(flipped, '', view, 'UVs')
    show = _expr(mat, unreal.MaterialExpressionScalarParameter, -700, 450, parameter_name='ShowView', default_value=0.0)
    colour = _custom(mat, SWIRL_CODE, {
        'UV': (uv, ''),
        'T': (_expr(mat, unreal.MaterialExpressionTime, -800, 150), ''),
        'View': (view, 'RGB'),
        'ShowView': (show, ''),
    }, -450, 0)
    lib.connect_material_property(colour, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


def apply_portals(materials, links):
    """The portal pairs from Course_links.json: at the end of each hole where the buggy path leaves the island,
    and on the next hole's tee island, with a hologram sign over the one you drive into."""
    folder = 'Course/Portals'
    for actor in _all():
        if str(actor.get_folder_path()) == folder:
            actors.destroy_actor(actor)
    portals = links.get('portals', [])
    if not portals:
        print('PORTALS: none in Course_links.json')
        return
    if not hasattr(unreal, 'SkyLinksPortal'):
        print('PORTALS skipped: rebuild the C++ first (Build.bat)')
        return
    mats = dict(materials, PortalSwirl=swirl_material())
    ring = import_mesh('SM_Portal', mats, collide=False)
    for link in portals:
        placed = {}
        for end in ('in', 'out'):
            x, y, z, yaw = link[end]
            portal = actors.spawn_actor_from_class(unreal.SkyLinksPortal, unreal.Vector(x * M, y * M, z * M),
                                                   unreal.Rotator(0, 0, yaw))
            portal.set_actor_label(f"Portal_{link['from']:02d}_{link['to']:02d}_{end.capitalize()}")
            portal.set_folder_path(folder)
            portal.get_editor_property('ring').set_static_mesh(ring)
            placed[end] = portal
        placed['out'].set_editor_property('target', placed['in'])
        placed['out'].set_editor_property('sign', f"HOLE {link['to']}  THIS WAY")
        print(f"PORTAL {link['from']} -> {link['to']}")


def portals():
    """Swap the rope bridges for portals: removes every rope bridge (and its hidden drive slab) and places a pair
    of portals for each hole-to-hole link. Needs the C++ built (Build.bat) first."""
    for actor in _all():
        if str(actor.get_folder_path()) == 'Course/Bridges':
            actors.destroy_actor(actor)
    apply_portals(build_materials(), json.loads((SOURCE / 'Course_links.json').read_text()))
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print('PORTALS DONE: rope bridges removed, portals in place')


PORTAL_VIEW_DIR = '/Game/Course/Portals'


def _swirl_slot(mesh):
    for index, slot in enumerate(mesh.get_editor_property('static_materials')):
        if str(slot.get_editor_property('material_slot_name')).startswith('PortalSwirl'):
            return index
    return 1


def portal_views(size=512):
    """Bake a picture of the next hole into every entry portal, so you see its tee through the swirl. A camera
    stands just in front of each arrival portal looking the way you'll drive out, takes one shot, and the shot is
    saved as T_PortalView_nn and shown in the portal leading there (no cost while playing). Run again after
    changing a hole (trees, floaters) to re-shoot them all."""
    swirl = swirl_material()
    everything = _all()
    portals = {a.get_actor_label(): a for a in everything if str(a.get_folder_path()) == 'Course/Portals'}
    arrivals = {label: a for label, a in portals.items() if label.endswith('_In')}
    if not arrivals:
        print('PORTAL VIEWS: no portals in the level yet - run isl.portals() first')
        return
    target_path = f'{PORTAL_VIEW_DIR}/RT_PortalView'
    target = unreal.load_asset(target_path) if unreal.EditorAssetLibrary.does_asset_exist(target_path) else \
        tools.create_asset('RT_PortalView', PORTAL_VIEW_DIR, unreal.TextureRenderTarget2D, unreal.TextureRenderTargetFactoryNew())
    target.set_editor_property('size_x', size)
    target.set_editor_property('size_y', size)
    target.set_editor_property('render_target_format', unreal.TextureRenderTargetFormat.RTF_RGBA8_SRGB)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    camera = actors.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    capture = camera.capture_component2d
    capture.set_editor_property('texture_target', target)
    capture.set_editor_property('capture_source', unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    capture.set_editor_property('fov_angle', 80.0)
    capture.set_editor_property('capture_every_frame', False)
    capture.set_editor_property('capture_on_movement', False)
    done = 0
    for label, arrival in sorted(arrivals.items()):
        number = label.split('_')[2]  # Portal_01_02_In -> 02
        entry = portals.get(label[:-3] + '_Out')
        if not entry:
            continue
        yaw = arrival.get_actor_rotation().yaw
        forward = arrival.get_actor_forward_vector()
        base = arrival.get_actor_location()
        eye = unreal.Vector(base.x + forward.x * 150, base.y + forward.y * 150, base.z + 230)
        camera.set_actor_location_and_rotation(eye, unreal.Rotator(0, -4, yaw), False, True)
        capture.set_editor_property('hidden_actors', [arrival])
        capture.capture_scene()
        name = f'T_PortalView_{number}'
        instance_name = f'MI_PortalView_{number}'
        instance_path = f'{PORTAL_VIEW_DIR}/{instance_name}'
        instance = unreal.load_asset(instance_path) if unreal.EditorAssetLibrary.does_asset_exist(instance_path) else \
            tools.create_asset(instance_name, PORTAL_VIEW_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        instance.set_editor_property('parent', swirl)
        # Re-shooting: let go of the old picture, then replace it (same name, so nothing else changes).
        lib.set_material_instance_texture_parameter_value(instance, 'View', unreal.load_asset(f'{TEXTURE_DEST}/T_Macro'))
        if unreal.EditorAssetLibrary.does_asset_exist(f'{PORTAL_VIEW_DIR}/{name}'):
            unreal.EditorAssetLibrary.delete_asset(f'{PORTAL_VIEW_DIR}/{name}')
        texture = unreal.RenderingLibrary.render_target_create_static_texture2d_editor_only(target, name)
        unreal.EditorAssetLibrary.save_loaded_asset(texture)
        lib.set_material_instance_texture_parameter_value(instance, 'View', texture)
        lib.set_material_instance_scalar_parameter_value(instance, 'ShowView', 1.0)
        unreal.EditorAssetLibrary.save_loaded_asset(instance)
        ring = entry.get_editor_property('ring')
        ring.set_material(_swirl_slot(ring.get_editor_property('static_mesh')), instance)
        done += 1
        print(f'PORTAL VIEW hole {int(number)}: {texture.get_name()}')
    actors.destroy_actor(camera)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print(f'PORTAL VIEWS DONE: {done} portals show the hole they lead to')


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


MIST_CODE = """
float edge = pow(saturate(dot(normalize(N), normalize(V))), 1.6);
return saturate(edge * Density * (0.45 + 1.1 * Noise));
"""


def mist_material():
    """M_FloaterMist: soft see-through cloud for the mist blobs under the floating islands. Unlit, fades out
    towards the blob's rim (so a squashed sphere reads as a puff, not a ball), patchy with slowly drifting noise,
    and melts into the rock where it touches it."""
    mat = _material('M_FloaterMist')
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_TRANSLUCENT)
    mat.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    drift = _expr(mat, unreal.MaterialExpressionPanner, -1100, 300, speed_x=0.004, speed_y=0.002)
    lib.connect_material_expressions(_world_uv(mat, 60, -1300, 300), '', drift, 'Coordinate')
    noise = _tex(mat, 'T_Macro', drift, -900, 300)
    density = _expr(mat, unreal.MaterialExpressionScalarParameter, -900, 500, parameter_name='Density', default_value=0.8)
    opacity = _custom(mat, MIST_CODE, {
        'N': (_expr(mat, unreal.MaterialExpressionVertexNormalWS, -900, 100), ''),
        'V': (_expr(mat, unreal.MaterialExpressionCameraVectorWS, -900, 200), ''),
        'Noise': (noise, 'R'),
        'Density': (density, ''),
    }, -600, 300, output=unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    soft = _expr(mat, unreal.MaterialExpressionDepthFade, -350, 300, fade_distance_default=800.0)
    lib.connect_material_expressions(opacity, '', soft, 'Opacity')
    colour = _expr(mat, unreal.MaterialExpressionVectorParameter, -600, 0, parameter_name='Colour',
                   default_value=unreal.LinearColor(0.82, 0.85, 0.9, 1.0))
    lib.connect_material_property(colour, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    lib.connect_material_property(soft, '', unreal.MaterialProperty.MP_OPACITY)
    lib.recompile_material(mat)
    unreal.EditorAssetLibrary.save_loaded_asset(mat)
    return mat


def fog_floaters(density=0.8):
    """Soft mist clouds under every floating island in the level (the ones you've kept): a wide flat puff under
    each with two smaller ones beside it. They're see-through cloud shapes, not fog volumes, so they always
    show (on phones too). Run again after moving, adding or deleting floaters: it clears its old ones first.
    density: 0.5 wispier, 1.2 thicker."""
    folder = 'Course/FloaterFog'
    for actor in _all():
        if str(actor.get_folder_path()) == folder:
            actors.destroy_actor(actor)
    mat = mist_material()
    instance_path = f'{MAT_DIR}/MI_FloaterMist'
    instance = unreal.load_asset(instance_path) if unreal.EditorAssetLibrary.does_asset_exist(instance_path) else \
        tools.create_asset('MI_FloaterMist', MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    instance.set_editor_property('parent', mat)
    unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(instance, 'Density', density)
    unreal.EditorAssetLibrary.save_loaded_asset(instance)
    sphere = unreal.load_asset('/Engine/BasicShapes/Sphere.Sphere')  # 1 m across
    count = 0
    for actor in _all():
        if not str(actor.get_folder_path()).endswith('/Floaters'):
            continue
        origin, extent = actor.get_actor_bounds(False)
        r = max(extent.x, extent.y) / M * 1.2  # m: a little wider than the island
        if r < 1:
            continue
        label = actor.get_actor_label()
        turn = (sum(map(ord, label)) % 360) * 3.14159 / 180
        bottom = origin.z - extent.z
        puffs = [((0.0, 0.0), r, 0.0),
                 ((0.5 * r * math.cos(turn), 0.5 * r * math.sin(turn)), 0.65 * r, -0.12 * r),
                 ((-0.45 * r * math.cos(turn + 0.7), -0.45 * r * math.sin(turn + 0.7)), 0.55 * r, -0.2 * r)]
        for i, ((dx, dy), size, dz) in enumerate(puffs):
            where = unreal.Vector(origin.x + dx * M, origin.y + dy * M, bottom + (dz - 0.05 * size) * M)
            blob = place(sphere, f'FloaterMist_{label}_{i}', folder, collide=False, shadow=False, location=where)
            blob.set_actor_scale3d(unreal.Vector(2 * size, 2 * size, 0.7 * size))
            blob.static_mesh_component.set_material(0, instance)
        count += 1
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print(f'FLOATER MIST: clouds under {count} floating islands (density {density})')


def reimport_paths(holes=HOLES):
    """After the buggy paths' ground was reshaped: re-import each hole's surface, rock and vines, then the rope
    bridges, in place (freeing memory after each). Trees, floaters and everything you've placed stay exactly as
    they are. Saved after every hole: after a crash, run it again (or reimport_paths(range(n, 19)) to carry on)."""
    materials = build_materials()
    for number in holes:
        for part in ('IslandTop', 'IslandRock', 'Vines'):
            name = f'SM_H{number:02d}_{part}'
            if (SOURCE / f'{name}.fbx').is_file() and unreal.EditorAssetLibrary.does_asset_exist(f'{DEST}/{name}'):
                import_mesh(name, materials, collide=part not in NO_COLLISION)
                unreal.SystemLibrary.collect_garbage()
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
        print(f'PATHS hole {number} done')
    # The rope bridges' drive slabs run off onto the grass: re-import them too (they stay where they are).
    links = json.loads((SOURCE / 'Course_links.json').read_text())
    for bridge in links.get('bridges', []):
        for key, collide in (('name', False), ('rails', False), ('guard', True)):
            name = bridge.get(key)
            if name and (SOURCE / f'{name}.fbx').is_file() and unreal.EditorAssetLibrary.does_asset_exist(f'{DEST}/{name}'):
                import_mesh(name, materials, collide=collide)
                unreal.SystemLibrary.collect_garbage()
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print('PATHS ALL DONE (islands and rope bridges)')


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


def apply_course(holes=HOLES, wipe_hand_work=False):
    """First-time build of the whole course. It clears EVERY tree and replants, so hand-arranged holes (KEEP_TREES)
    would be lost: once the course exists, use refresh_islands() instead."""
    assert wipe_hand_work or not KEEP_TREES, ('apply_course() replants every island and would wipe your hand-placed '
                                              'trees on hole(s) %s. Use refresh_islands() instead.' % sorted(KEEP_TREES))
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
