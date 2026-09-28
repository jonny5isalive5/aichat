"""Sky Links course plan: where each floating island sits and what is on it (holes 1-6).

Hole 1 keeps its own design in build_floating_islands.py. Holes 2-6 follow the owner's reference hole maps:
  2 Rhododendron   par 4 dogleg right between woods, rhododendrons round the green
  3 Twin Brooks    par 4, a brook to carry, then two fairway lanes split by a line of trees
  4 Lakeside       par 5, pond and brook by the tee, a lake down the right of the second half
  5 Last Fir       par 4 dogleg left round a stand of firs, a pond left of the tee
  6 Stepping Stones par 3 over a brook with two footbridges
Holes 7-18 follow the owner's second set of twelve reference maps (in the order they were sent).
Bunkers are (x, y, radius) circles or any shape (ellipse(...)) for big fairway and waste bunkers.

Local frame of every hole: tee at (0, 0), +x toward the green, +y to the golfer's right (metres).
PLACE puts the tee in the world (x, y), turns the hole (yaw, degrees, Unreal convention) and lifts it (z).
"""
import math

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

# Tee position (world m), heading (deg), height of the tee (m). Islands step up and down along the chain.
PLACE = {
    1: ((0.0, 0.0), 0.0, 0.0),
    2: ((430.0, 130.0), 90.0, 18.0),
    3: ((320.0, 520.0), 100.0, 6.0),
    4: ((330.0, 950.0), 75.0, -10.0),
    5: ((600.0, 1445.0), 110.0, 12.0),
    6: ((470.0, 1860.0), 185.0, 28.0),
    # 7-18 found by a search: each tee 45-85 m of sky from the last green (one rope bridge), 70 m clear of the rest.
    7: ((375.6, 1692.6), 240.0, 8.0),
    8: ((146.1, 1290.8), 285.0, -6.0),
    9: ((147.2, 927.4), 135.0, 16.0),
    10: ((-204.8, 1025.9), 300.0, 2.0),
    11: ((-273.4, 829.3), 315.0, 22.0),
    12: ((124.0, 343.5), 165.0, 6.0),
    13: ((-281.7, 480.4), 120.0, -8.0),
    14: ((-427.1, 988.4), 60.0, 12.0),
    15: ((-20.5, 1344.3), 150.0, 26.0),
    16: ((-169.1, 1597.0), 0.0, 4.0),
    17: ((-42.6, 1775.1), 180.0, -4.0),
    18: ((-483.2, 1731.1), 255.0, 14.0),
}


def ellipse(cx, cy, rx, ry, rot=0.0):
    return affinity.rotate(affinity.scale(Point(cx, cy).buffer(1.0, 48), rx, ry), rot, origin=(cx, cy))


def path(points, width):
    return LineString(points).buffer(width / 2, 24, join_style='round')


HOLES = {
    2: dict(name='Rhododendron', par=4, aim=(185, 0),
            fairways=[path([(28, 0), (120, -2), (185, 4), (225, 24), (245, 50)], 34)],
            green=((262, 72), 15), bunkers=[(247, 89, 5), (280, 58, 5), (214, -15, 7)],
            woods=[ellipse(162, 50, 32, 20, 30), ellipse(100, -44, 55, 13), ellipse(262, 10, 20, 16)],
            ponds=[], streams=[], footbridges=[],
            mix={'Oak_A': 3, 'Oak_B': 3, 'Birch': 2, 'Bush_Flowering': 5, 'Bush_Round': 2}),
    3: dict(name='Twin Brooks', par=4, aim=(225, 24),
            fairways=[path([(25, 0), (78, 0)], 30), path([(135, -20), (230, -26), (298, -12)], 22),
                      path([(150, 20), (240, 28), (300, 14)], 22)],
            green=((330, 0), 16), bunkers=[(316, -19, 5), (346, 17, 5), (262, -42, 6)],
            woods=[path([(152, 0), (290, 1)], 12), ellipse(60, -40, 30, 10), ellipse(200, 55, 60, 10)],
            ponds=[], streams=[([(80, -60), (104, -12), (118, 20), (138, 66)], 7)],
            footbridges=[((110, 5), 0.0, 13)],
            mix={'Oak_A': 3, 'Oak_B': 2, 'Poplar': 2, 'Birch': 3, 'Bush_Round': 3}),
    # Owner's edit: the lake moves from the right-hand side into the middle of the fairway (lay up or carry it),
    # the island narrows where the lake was, and a big bunker guards the front left of the green.
    4: dict(name='Lakeside', par=5, aim=(140, 0),
            fairways=[path([(30, 0), (150, 5), (300, -5), (440, 0)], 38)],
            green=((478, 0), 17), bunkers=[(460, -19, 5), (468, 21, 5), (497, 18, 4), (132, -25, 6), (305, 18, 6),
                                           ellipse(425, -12, 32, 18)],
            woods=[ellipse(200, -56, 90, 14), ellipse(425, -46, 50, 13), ellipse(120, 45, 40, 11)],
            ponds=[ellipse(50, -42, 16, 11), ellipse(208, 0, 55, 23)],
            streams=[([(56, -32), (72, 0), (88, 42)], 6)], footbridges=[((72, 0), 0.0, 11)],
            mix={'Oak_A': 3, 'Oak_B': 3, 'Poplar': 3, 'Birch': 1, 'Bush_Round': 3}),
    5: dict(name='Last Fir', par=4, aim=(175, 0),
            fairways=[path([(30, 0), (160, 0), (230, -22), (275, -58)], 34)],
            green=((298, -86), 15), bunkers=[(283, -104, 5), (314, -70, 4), (200, 27, 7)],
            woods=[ellipse(182, -60, 36, 18, -20), ellipse(120, 42, 60, 12), ellipse(320, -40, 22, 14)],
            ponds=[ellipse(46, -46, 28, 14)], streams=[], footbridges=[],
            mix={'Pine': 7, 'Oak_B': 1, 'Birch': 1, 'Bush_Round': 2}),
    6: dict(name='Stepping Stones', par=3, aim=(150, 4),
            fairways=[path([(100, 0), (128, 3)], 22)],
            green=((150, 4), 17), bunkers=[(137, -17, 5), (166, 23, 5)],
            woods=[ellipse(20, -46, 25, 12), ellipse(108, -46, 30, 12), ellipse(118, 50, 30, 12)],
            ponds=[], streams=[([(40, -62), (55, -15), (62, 15), (76, 62)], 8)],
            footbridges=[((52, -26), 0.0, 13), ((65, 30), 0.0, 13)],
            mix={'Oak_A': 2, 'Pine': 3, 'Birch': 2, 'Bush_Round': 3, 'Bush_Flowering': 2}),

    # Holes 7-18 follow the owner's second set of reference maps, in the order they were sent.
    7: dict(name='Lakeside Bend', par=4, aim=(230, -8),
            fairways=[path([(30, 0), (150, 0), (255, -12)], 36)],
            green=((315, -24), 16), bunkers=[(302, 0, 5), (336, -6, 5)],
            woods=[ellipse(180, 50, 90, 12), ellipse(115, -45, 45, 12), ellipse(345, 20, 22, 12)],
            ponds=[ellipse(282, -64, 40, 17, -20)], streams=[], footbridges=[],
            mix={'Oak_A': 3, 'Oak_B': 3, 'Birch': 2, 'Poplar': 2, 'Bush_Round': 2}),
    8: dict(name='The Crossing', par=3, aim=(150, 0),
            fairways=[path([(18, 0), (38, 0)], 18)],
            green=((152, 0), 16), bunkers=[(141, -19, 5), (162, 19, 5), (168, -13, 4), (134, 16, 4)],
            woods=[ellipse(30, -45, 20, 10), ellipse(196, 4, 12, 28), ellipse(40, 45, 22, 10)],
            ponds=[ellipse(90, -8, 38, 50)], streams=[], footbridges=[],
            mix={'Pine': 5, 'Oak_B': 2, 'Birch': 1, 'Bush_Round': 2}),
    9: dict(name='Long Water', par=4, aim=(240, -5),
            fairways=[path([(25, 0), (160, -2), (305, -12)], 32)],
            green=((336, -20), 16), bunkers=[(318, -39, 5), (353, -3, 5), (349, -37, 4), (215, -26, 6), (246, -30, 5)],
            woods=[ellipse(160, -52, 120, 12)],
            ponds=[ellipse(190, 46, 118, 19, -4)], streams=[], footbridges=[],
            mix={'Oak_A': 3, 'Oak_B': 2, 'Poplar': 2, 'Bush_Flowering': 3, 'Bush_Round': 2}),
    10: dict(name='Over the Top', par=3, aim=(160, -10),
             fairways=[path([(120, -18), (135, -15)], 16)],
             green=((162, -10), 16), bunkers=[(147, -28, 5), (175, 8, 5)],
             woods=[ellipse(172, 40, 30, 12), ellipse(30, -45, 22, 10)],
             ponds=[ellipse(82, 2, 42, 52, 15)], streams=[], footbridges=[],
             mix={'Oak_A': 2, 'Birch': 3, 'Pine': 2, 'Bush_Round': 3}),
    11: dict(name='Grand Sweep', par=5, aim=(250, 0),
             fairways=[path([(30, 0), (200, 0), (340, 30), (440, 70)], 38)],
             green=((476, 86), 17), bunkers=[(300, 58, 9), (460, 106, 5), (494, 67, 5)],
             woods=[ellipse(200, -45, 120, 12), ellipse(225, 55, 60, 14), ellipse(482, 22, 30, 12)],
             ponds=[ellipse(432, 132, 20, 12)], streams=[], footbridges=[],
             mix={'Oak_A': 3, 'Oak_B': 3, 'Birch': 2, 'Poplar': 2, 'Bush_Round': 2}),
    12: dict(name='Corner Pocket', par=4, aim=(215, 0),
             fairways=[path([(30, 0), (200, 0), (262, 25), (290, 70)], 32)],
             green=((300, 100), 15), bunkers=[(318, 86, 5), (281, 115, 4), (210, -22, 6)],
             woods=[ellipse(185, 58, 55, 20, 20), ellipse(150, -45, 100, 12), ellipse(335, 40, 20, 15)],
             ponds=[], streams=[], footbridges=[],
             mix={'Oak_A': 3, 'Oak_B': 3, 'Poplar': 1, 'Birch': 1, 'Bush_Round': 3}),
    13: dict(name='Creek Run', par=5, aim=(250, 0),
             fairways=[path([(25, 0), (95, 0)], 30), path([(148, 0), (300, 5), (452, 0)], 40)],
             green=((490, 0), 17), bunkers=[(470, -21, 6), (506, 20, 5), (405, -24, 7), (378, -27, 6)],
             woods=[ellipse(262, -56, 180, 12), ellipse(300, 56, 150, 12)],
             ponds=[], streams=[([(116, -72), (121, -20), (127, 20), (139, 72)], 7)], footbridges=[((124, 0), 0.0, 12)],
             mix={'Oak_A': 3, 'Oak_B': 3, 'Pine': 2, 'Birch': 2, 'Bush_Round': 2}),
    14: dict(name='Cross Bunkers', par=4, aim=(215, -5),
             fairways=[path([(30, 0), (170, 0), (290, -30), (340, -45)], 30)],
             green=((366, -52), 15), bunkers=[(186, -9, 4), (200, 7, 4), (212, -15, 4), (353, -70, 4), (382, -33, 4), (373, -70, 3)],
             woods=[ellipse(185, -52, 85, 14, -10), ellipse(210, 40, 120, 12)],
             ponds=[], streams=[], footbridges=[],
             mix={'Pine': 4, 'Oak_B': 2, 'Oak_A': 2, 'Bush_Round': 3}),
    15: dict(name='The Narrows', par=4, aim=(230, 0),
             fairways=[path([(25, 0), (200, -5), (322, 5)], 26)],
             green=((350, 20), 14), bunkers=[(363, 4, 4), (340, 37, 4)],
             woods=[ellipse(172, -36, 150, 10), ellipse(172, 34, 150, 10)],
             ponds=[], streams=[], footbridges=[],
             mix={'Oak_A': 2, 'Oak_B': 3, 'Birch': 2, 'Bush_Round': 3, 'Bush_Flowering': 2}),
    16: dict(name='Waste Lake', par=4, aim=(170, 20),
             fairways=[path([(30, 0), (130, 0), (190, 34)], 30)],
             green=((272, 56), 15), bunkers=[ellipse(150, 58, 30, 13), ellipse(262, -8, 34, 17), (258, 76, 5)],
             woods=[ellipse(60, -40, 30, 10)],
             ponds=[ellipse(190, -18, 48, 26, 20)], streams=[], footbridges=[],
             mix={'Pine': 3, 'Oak_A': 2, 'Bush_Round': 3}),
    17: dict(name='Harbour Wall', par=4, aim=(215, -5),
             fairways=[path([(30, 0), (170, 0), (260, -20)], 32)],
             green=((302, -36), 15), bunkers=[ellipse(250, -42, 22, 6, 20), (206, -28, 6)],
             woods=[ellipse(140, -45, 100, 12)],
             ponds=[ellipse(200, 52, 85, 22, -10), ellipse(322, 4, 22, 26)], streams=[], footbridges=[],
             mix={'Oak_A': 2, 'Oak_B': 2, 'Poplar': 3, 'Bush_Round': 3}),
    18: dict(name='Home Waste', par=4, aim=(240, -8),
             fairways=[path([(30, 0), (108, 0)], 30), path([(192, -14), (300, -5)], 30)],
             green=((332, -5), 16), bunkers=[ellipse(150, 4, 38, 30), (338, 16, 5), (349, -4, 4), (352, 24, 4)],
             woods=[ellipse(190, 50, 110, 12)],
             ponds=[], streams=[], footbridges=[],
             mix={'Pine': 5, 'Oak_B': 2, 'Bush_Round': 3}),
}


def to_world(number, x, y):
    """Local hole metres -> world metres (arrays or scalars)."""
    (ox, oy), yaw, _ = PLACE[number]
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    return ox + x * c - y * s, oy + x * s + y * c


def to_local(number, wx, wy):
    (ox, oy), yaw, _ = PLACE[number]
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    dx, dy = np.asarray(wx, float) - ox, np.asarray(wy, float) - oy
    return dx * c + dy * s, -dx * s + dy * c


def world_geom(number, geom):
    (ox, oy), yaw, _ = PLACE[number]
    return affinity.translate(affinity.rotate(geom, yaw, origin=(0, 0)), ox, oy)
