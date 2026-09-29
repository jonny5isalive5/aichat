"""Dress a floating-island hole with the stylised Sky Links trees (Scripts/import_trees.py imports them).

Run inside the editor with the Course map open, after apply_floating_islands.apply_islands(n) has run and
its collision has cooked (a separate call). From the Output Log in Python mode:

    import sys, unreal; sys.path.append(unreal.Paths.project_dir() + "Scripts")
    import place_island_trees; place_island_trees.place_trees(1)

- The hole's gameplay trees (the placeholder trunk + canopy balls) become stylised trees; the trunk
  placeholder stays as invisible collision so the ball still hits the tree.
- About 35 more trees are scattered by tracing onto the islands: only on rough or on the small floating
  islands, never on the line of play, the stone bridge, the tee or the clubhouse grounds, at least 9 m apart.
Re-running replaces the previous set (same random seed, so the same layout).

Uses the stylised, phone-friendly trees (Art/Blender/build_trees.py); their UCX_ trunk box is the collision.
"""
import json
import math
import random
from pathlib import Path

import unreal

M = 100.0
LIB = '/Game/Course/Trees'  # the stylised trees from Scripts/import_trees.py (run that first)
TREES = [f'{LIB}/SM_Tree_{n}' for n in ('Oak_A', 'Oak_B', 'Poplar', 'Pine', 'Birch')]
SMALL = [f'{LIB}/SM_Bush_{n}' for n in ('Round', 'Flowering')]

# Where trees must not go, per hole (Unreal metres). Hole 1 plays straight along +x.
KEEP_CLEAR = {
    1: dict(play=((-5, 0), (380, 0), 30.0),                  # tee to green corridor half-width
            circles=[((-110, -45), 46.0), ((0, 0), 18.0)],   # clubhouse grounds, tee and buggy parking
            paths=[[(2, -12), (18, -24), (40, -32)]],        # the stone bridge, 8 m either side
            bounds=(-200, 470, -150, 130), scatter=35),
}

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _dist_to_segment(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def _clear(number, x, y):
    k = KEEP_CLEAR[number]
    a, b, half = k['play']
    if _dist_to_segment((x, y), a, b) < half:
        return False
    if any(math.hypot(x - cx, y - cy) < r for (cx, cy), r in k['circles']):
        return False
    return all(_dist_to_segment((x, y), p, q) > 8.0 for path in k['paths'] for p, q in zip(path[:-1], path[1:]))


def _ground(world, x, y):
    """(z in cm, island part label, surface name) under x, y (metres), or None over the void."""
    hit = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x * M, y * M, 6000), unreal.Vector(x * M, y * M, -8000),
                                                 unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [], unreal.DrawDebugTrace.NONE, True)
    if not hit:
        return None
    t = hit.to_tuple()  # (blocking, overlap, time, distance, location, impact point, normal, impact normal, phys mat, actor, ...)
    actor = t[9]
    pm = t[8]
    surface = str(pm.get_editor_property('surface_type')) if pm else ''
    return t[5].z, actor.get_actor_label() if actor else '', surface, t[7].z


def _spawn(path, x, y, z, rng, folder, label, scale):
    mesh = unreal.load_asset(path)
    assert mesh, f'{path} not found: run import_trees.import_trees() first'
    tree = actors.spawn_actor_from_object(mesh, unreal.Vector(x * M, y * M, z - 15), unreal.Rotator(0, 0, rng.uniform(0, 360)))
    tree.set_actor_scale3d(unreal.Vector(scale, scale, scale))
    tree.set_actor_label(label)
    tree.set_folder_path(folder)
    return tree


def place_trees(number=1):
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    folder = f'Course/Hole{number:02d}/Trees'
    hole_folder = f'Course/Hole{number:02d}'
    rng = random.Random(number * 101)

    for actor in actors.get_all_level_actors():
        path = str(actor.get_folder_path())
        label = actor.get_actor_label()
        if path == folder:
            actors.destroy_actor(actor)  # previous run
        elif path == hole_folder and label.startswith('TreeCanopy'):
            actors.destroy_actor(actor)
        elif path == hole_folder and label.startswith('TreeTrunk'):
            actor.set_actor_hidden_in_game(True)  # stays as the tree's collision for the ball
            actor.set_is_temporarily_hidden_in_editor(True)

    spots = json.loads((Path(unreal.Paths.project_dir()) / 'Art' / 'Exports' / 'Islands' / f'Hole{number:02d}_spots.json').read_text())
    placed = []
    for i, (x, y, z) in enumerate(spots['trees']):
        _spawn(rng.choice(TREES), x, y, z * M, rng, folder, f'IslandTree{i:02d}', rng.uniform(0.9, 1.1))
        placed.append((x, y))

    k = KEEP_CLEAR[number]
    x0, x1, y0, y1 = k['bounds']
    tries, scattered, on_floaters = 0, 0, 0
    while scattered < k['scatter'] and tries < 4000:
        tries += 1
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        if not _clear(number, x, y) or any(math.hypot(x - px, y - py) < 9.0 for px, py in placed):
            continue
        found = _ground(world, x, y)
        if not found:
            continue
        z, part, surface, normal_z = found
        if normal_z < 0.9:
            continue  # cliff faces and steep banks
        if part.startswith('IslandTop'):
            if 'TYPE2' not in surface:  # SurfaceType2 = Rough
                continue
            small = rng.random() < 0.3
        elif part.startswith('Floaters'):
            if on_floaters >= 8:
                continue
            on_floaters += 1
            small = rng.random() < 0.6
        else:
            continue
        pool = SMALL if small else TREES
        _spawn(rng.choice(pool), x, y, z, rng, folder, f'IslandTree{len(placed):02d}', rng.uniform(0.8, 1.15))
        placed.append((x, y))
        scattered += 1

    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    print(f'TREES hole {number}: {len(spots["trees"])} gameplay trees, {scattered} scattered '
          f'({on_floaters} on floating islands) after {tries} tries; map saved')
