"""Read-only editor validation; use validate_holes([1]) after an apply pass."""
import json
from pathlib import Path
import unreal


def validate_holes(numbers):
    root=Path(unreal.Paths.project_dir()).resolve()
    samples=[]
    for batch in ['Holes01-06','Holes07-18']:
        samples+=json.loads((root/'Art/Terrain'/batch/'validation_samples.json').read_text())
    world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    assert world.get_path_name()=='/Game/Maps/Course.Course'
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    rows=[]; errors=[]
    for p in samples:
        if p['hole'] not in numbers:
            continue
        for complex_collision in [False,True]:
            hit=unreal.SystemLibrary.line_trace_single_for_objects(world,unreal.Vector(p['x'],p['y'],2000),unreal.Vector(p['x'],p['y'],-2000),[unreal.ObjectTypeQuery.ECC_WORLD_STATIC],complex_collision,[],unreal.DrawDebugTrace.NONE)
            if not hit:
                errors.append([p['hole'],p['kind'],'no collision']);continue
            t=hit.to_tuple(); z=t[5].z; pm=t[8].get_name() if t[8] else None
            row={'hole':p['hole'],'kind':p['kind'],'complex':complex_collision,'x':p['x'],'y':p['y'],'z':round(z,4),'expected_z':round(p['expected_z'],4),'pm':pm,'actor':t[9].get_actor_label()}
            rows.append(row)
            if abs(z-p['expected_z'])>2 or pm!=p['pm']:
                errors.append(row)
    for number in numbers:
        hole=next(a for a in actors if a.get_actor_label()==f'GolfHole{number:02d}')
        cup=hole.cup_root.get_world_location()
        hit=unreal.SystemLibrary.line_trace_single_for_objects(world,unreal.Vector(cup.x,cup.y,2000),unreal.Vector(cup.x,cup.y,-2000),[unreal.ObjectTypeQuery.ECC_WORLD_STATIC],False,[],unreal.DrawDebugTrace.NONE)
        if not hit or abs(hit.to_tuple()[5].z-cup.z)>1:
            errors.append({'hole':number,'kind':'cup alignment','cup_z':cup.z,'ground_z':hit.to_tuple()[5].z if hit else None})
    report={'holes':list(numbers),'probe_count':len(rows),'errors':errors,'samples':rows}
    print(json.dumps(report))
    return report
