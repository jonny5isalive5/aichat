"""Raise the sun in /Game/Maps/Course without touching anything else.

A low sun reflects off turf and water straight into the golfer's camera. Run this inside the editor
(Aura's execute_unreal_python, or Tools > Execute Python Script), then call set_sun() to use the
default, or for example set_sun(-65) for a slightly lower sun. It only rotates DirectionalLight
actors and saves the level; terrain, water and holes are left alone.
"""
import unreal

# Degrees below the horizon the light points: -90 is straight down, -45 was the old default.
DEFAULT_PITCH = -70.0


def set_sun(pitch=DEFAULT_PITCH, yaw=None):
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    assert world.get_path_name() == '/Game/Maps/Course.Course', 'Open /Game/Maps/Course first'
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    suns = [a for a in actors if isinstance(a, unreal.DirectionalLight)]
    assert suns, 'No DirectionalLight in the level'
    for sun in suns:
        old = sun.get_actor_rotation()
        new = unreal.Rotator(roll=old.roll, pitch=pitch, yaw=old.yaw if yaw is None else yaw)
        sun.modify()
        sun.set_actor_rotation(new, False)
        print(f'SUN {sun.get_actor_label()}: pitch {old.pitch:.1f} -> {new.pitch:.1f}, yaw {new.yaw:.1f}')
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    return len(suns)
