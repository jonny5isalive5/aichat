"""Apply generated terrain through Aura inside the SkyLinks Unreal editor.

Run this file, then:
  apply_holes([1])              any subset of 1..18 whose landscape already exists
  describe_create([7, 8])       holes 7-18: the exact landscape Aura must create first
  remove_blockout_surfaces(7)   holes 7-18: delete the flat Rough/Fairway/Green/Bunker slabs
                                once the landscape is applied (water, trees, tee box stay)

Requires the Aura plugin. Preserves landscape transforms, layer bindings and water.
Back up/save existing work before running; Aura transactions auto-save changed assets.
"""
import hashlib
import json
from pathlib import Path
import unreal


def _batch(number):
    assert 1<=number<=18
    root=Path(unreal.Paths.project_dir()).resolve()
    folder=root/'Art/Terrain'/('Holes01-06' if number<=6 else 'Holes07-18')
    manifest=json.loads((folder/'manifest.json').read_text())
    entry=next(h for h in manifest['holes'] if h['label']==f'Terrain_Hole{number:02d}')
    return folder,manifest,entry


def describe_create(numbers):
    """Print the landscape Aura must create for each new hole (location, scale, resolution, layers)."""
    for number in numbers:
        _,_,h=_batch(number)
        assert 'create' in h, f'Hole {number} uses an existing Aura landscape'
        print(json.dumps(h['create']))


def remove_blockout_surfaces(number):
    """Delete the flat blockout slabs that the landscape replaces on this hole."""
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    labels=[a.get_actor_label() for a in actors]
    assert f'Terrain_Hole{number:02d}' in labels, 'Apply the landscape before removing the slabs'
    doomed=[a for a in actors if str(a.get_folder_path())==f'Course/Hole{number:02d}'
            and isinstance(a,unreal.StaticMeshActor)
            and (a.get_actor_label()=='Rough' or a.get_actor_label()=='Green'
                 or a.get_actor_label().startswith('Fairway') or a.get_actor_label().startswith('Bunker'))]
    for actor in doomed:
        print('REMOVE',number,actor.get_actor_label())
        unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(actor)
    return len(doomed)


def apply_holes(numbers):
    world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    assert world.get_path_name()=='/Game/Maps/Course.Course', 'Wrong map'
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    landscapes={a.get_actor_label():a for a in actors if isinstance(a,unreal.Landscape)}
    for number in numbers:
        folder,manifest,h=_batch(number)
        assert h['label'] in landscapes, f"{h['label']} does not exist yet: create it first (describe_create([{number}]))"
        land=landscapes[h['label']]
        for entry in h['files'].values():
            assert hashlib.sha256((folder/entry['file']).read_bytes()).hexdigest()==entry['sha256'], 'Generated file hash mismatch'
        g=h['grid']; location=land.get_actor_location(); scale=land.get_actor_scale3d()
        assert abs(location.x-g['x0'])<.01 and abs(location.y-g['y0'])<.01
        assert abs(scale.z-manifest['scale_z'])<.00001 and abs(location.z-manifest['actor_z_cm'])<.00001
        assert abs(scale.x-g['sx'])<.00001 and abs(scale.y-g['sy'])<.00001
        assert len(land.get_edit_layers_bp())==1, 'Review edit layers before overwriting'
        assert set(str(n) for n in land.get_target_layer_names())=={'Rough','Fairway','Green','Bunker'}
        params={'landscape_label':h['label'],'heightmap_path':str(folder/h['files']['height']['file']),'blur_radius':0}
        result=json.loads(unreal.UnrealMCPTerrainCommands.handle_command('update_landscape_heightmap',json.dumps(params)))
        assert result.get('success'),result
        assert result['data']['resolution_x']==g['W'] and result['data']['resolution_y']==g['H']
        for layer in ['Rough','Fairway','Green','Bunker']:
            texture=unreal.RenderingLibrary.import_file_as_texture2d(world,str(folder/h['files'][layer]['file']))
            assert texture
            target=unreal.RenderingLibrary.create_render_target2d(world,g['W'],g['H'],unreal.TextureRenderTargetFormat.RTF_RGBA8)
            canvas,size,context=unreal.RenderingLibrary.begin_draw_canvas_to_render_target(world,target)
            canvas.draw_texture(texture,unreal.Vector2D(0,0),unreal.Vector2D(g['W'],g['H']),unreal.Vector2D(0,0),unreal.Vector2D(1,1),unreal.LinearColor(1,1,1,1),unreal.BlendMode.BLEND_OPAQUE)
            unreal.RenderingLibrary.end_draw_canvas_to_render_target(world,context)
            assert land.landscape_import_weightmap_from_render_target(target,layer),layer
        golf_hole=next(a for a in actors if a.get_actor_label()==f'GolfHole{number:02d}')
        cup_root=golf_hole.cup_root
        cup_root.modify()
        cup_root.set_world_location(unreal.Vector(*h['cup_cm']),False,True)
        ignore=[a for a in actors if a!=land]
        for actor in actors:
            if str(actor.get_folder_path())!=f'Course/Hole{number:02d}':
                continue
            label=actor.get_actor_label()
            if not (label.startswith('TreeTrunk') or label.startswith('TreeCanopy')):
                continue
            p=actor.get_actor_location()
            hit=unreal.SystemLibrary.line_trace_single_for_objects(world,unreal.Vector(p.x,p.y,2000),unreal.Vector(p.x,p.y,-2000),[unreal.ObjectTypeQuery.ECC_WORLD_STATIC],True,ignore,unreal.DrawDebugTrace.NONE)
            assert hit
            z=hit.to_tuple()[5].z
            actor.modify()
            actor.set_actor_location(unreal.Vector(p.x,p.y,z+(450 if label.startswith('TreeTrunk') else 1050)),False,True)
        print('APPLIED',number,result['data']['resolution_x'],result['data']['resolution_y'])
