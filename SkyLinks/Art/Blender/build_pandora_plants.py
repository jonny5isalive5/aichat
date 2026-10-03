"""Pandora-style plants for the golf course itself (the floating islands' look, on the ground): glowing ferns,
glowing mushrooms, big-leaved plants, glowing flower bushes and little red flowers.

    python Art/Blender/build_pandora_plants.py

Writes Art/Exports/Plants/SM_Pandora_*.fbx, each standing on its pivot (0, 0, 0), with the floater dressing's two
materials (FloaterLeaf, FloaterGlow) and its atlas. In Unreal, apply_floating_islands.pandora_plants() scatters
them over the rough round the trees (never on paths, fairways, greens, tees or bunkers).
"""
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sl_common as sl  # noqa: E402
from build_floater_dressing import FERN, GLOW_COLOURS, LEAF, PETAL, Kit, leaf_green, make_atlas  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'Art' / 'Exports' / 'Plants'
UP = Vector((0, 0, 1))


def around(rng, count, jitter=0.35):
    for k in range(count):
        a = 2 * math.pi * k / count + rng.uniform(-jitter, jitter)
        out = Vector((math.cos(a), math.sin(a), 0))
        yield out, Vector((-out.y, out.x, 0))


def glow_fern(kit, rng, colour, size):
    for out, side in around(rng, rng.randint(6, 9)):
        length = rng.uniform(0.8, 1.2) * size
        kit.bent_card(Vector((0, 0, 0)), (UP + out * 0.3).normalized(), side, out, length, length * 0.38,
                      0.55, FERN, colour, 1, rows=4)


def mushrooms(kit, rng, colour, size):
    for _ in range(rng.randint(3, 6)):
        q = Vector((rng.uniform(-0.45, 0.45), rng.uniform(-0.45, 0.45), 0)) * size
        height = rng.uniform(0.3, 0.8) * size
        cap = rng.uniform(0.12, 0.3) * size
        kit.cone(q + Vector((0, 0, height)), q, 0.035 * size, (0.75, 0.78, 0.8), 0, sides=4)
        kit.cone(q + Vector((0, 0, height + cap * 0.55)), q + Vector((0, 0, height - cap * 0.1)), cap, colour, 1)
        kit.blob(q + Vector((0, 0, height + cap * 0.1)), cap * 0.35, tuple(min(1, c * 0.6 + 0.4) for c in colour), 1, sides=5)


def big_leaf(kit, rng, size, bud=None):
    green = leaf_green(rng)
    for out, side in around(rng, rng.randint(6, 9)):
        length = rng.uniform(0.75, 1.25) * size
        kit.bent_card(Vector((0, 0, 0)), (UP * 0.75 + out * 0.65).normalized(), side, out, length, length * 0.8,
                      0.85, LEAF, green, 0, rows=3)
    if bud:  # a glowing bud standing up out of the middle
        stalk = rng.uniform(0.7, 1.1) * size
        kit.cone(Vector((0, 0, stalk)), Vector((0, 0, 0)), 0.03 * size, (0.2, 0.45, 0.15), 0, sides=4)
        kit.blob(Vector((0, 0, stalk)), 0.12 * size, bud, 1, squash=1.4, sides=6)


def glow_flowers(kit, rng, colour, size):
    """A low bush of glowing anemones on short stalks among a few leaves."""
    big_leaf(kit, rng, size * 0.55)
    for _ in range(rng.randint(3, 5)):
        base = Vector((rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), 0)) * size
        top = base + Vector((rng.uniform(-0.1, 0.1) * size, rng.uniform(-0.1, 0.1) * size, rng.uniform(0.35, 0.7) * size))
        kit.cone(top, base, 0.025 * size, (0.2, 0.45, 0.15), 0, sides=4)
        radius = rng.uniform(0.18, 0.32) * size
        face = (top - base).normalized()
        t1 = face.cross(UP)
        t1 = t1.normalized() if t1.length > 1e-3 else Vector((1, 0, 0))
        t2 = face.cross(t1)
        petals = rng.choice((7, 8, 9))
        spin = rng.uniform(0, 6.28)
        for k in range(petals):
            a = spin + 2 * math.pi * k / petals
            along = t1 * math.cos(a) + t2 * math.sin(a)
            kit.card(top, (along + face * 0.45).normalized(), face.cross(along), radius, radius * 0.4, PETAL, colour, 1)
        kit.blob(top + face * 0.03 * size, radius * 0.25, tuple(min(1, c * 0.6 + 0.4) for c in colour), 1, sides=5)


def red_flowers(kit, rng, size):
    big_leaf(kit, rng, size * 0.45)
    for _ in range(rng.randint(5, 9)):
        p = Vector((rng.uniform(-0.4, 0.4) * size, rng.uniform(-0.4, 0.4) * size, rng.uniform(0.25, 0.45) * size))
        kit.cone(p, Vector((p.x, p.y, 0)), 0.015 * size, (0.2, 0.45, 0.15), 0, sides=3)
        for k in range(5):
            a = 2 * math.pi * k / 5
            along = Vector((math.cos(a), math.sin(a), 0.35)).normalized()
            kit.card(p, along, UP.cross(along).normalized(), 0.11 * size, 0.07 * size, PETAL, (0.9, 0.1, 0.07), 0)


PLANTS = {  # name: (builder, size in metres)
    'GlowFern_A': (lambda k, r: glow_fern(k, r, GLOW_COLOURS[0], 1.5)),
    'GlowFern_B': (lambda k, r: glow_fern(k, r, GLOW_COLOURS[3], 1.3)),
    'GlowFern_C': (lambda k, r: glow_fern(k, r, GLOW_COLOURS[1], 1.7)),
    'Mushrooms_A': (lambda k, r: mushrooms(k, r, GLOW_COLOURS[2], 1.2)),
    'Mushrooms_B': (lambda k, r: mushrooms(k, r, GLOW_COLOURS[0], 1.0)),
    'BigLeaf_A': (lambda k, r: big_leaf(k, r, 1.4)),
    'BigLeaf_B': (lambda k, r: big_leaf(k, r, 1.1, bud=GLOW_COLOURS[1])),
    'GlowFlowers_A': (lambda k, r: glow_flowers(k, r, GLOW_COLOURS[1], 1.3)),
    'GlowFlowers_B': (lambda k, r: glow_flowers(k, r, GLOW_COLOURS[3], 1.2)),
    'RedFlowers': (lambda k, r: red_flowers(k, r, 1.2)),
}


def main():
    make_atlas()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, build in PLANTS.items():
        bpy.ops.wm.read_factory_settings(use_empty=True)
        kit = Kit()
        build(kit, random.Random(name))
        obj = kit.mesh(f'SM_Pandora_{name}')
        sl.export_fbx(str(OUT / f'SM_Pandora_{name}.fbx'), [obj])
        print(f'PLANT SM_Pandora_{name}: {len(kit.f)} triangles')


if __name__ == '__main__':
    main()
