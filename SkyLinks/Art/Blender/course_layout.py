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


# Design rules (owner's brief, second pass): every hazard is in play. Fairway bunkers sit where drives and lay-ups
# land, greenside bunkers guard the way in, water crosses the line of play or hugs the fairway so it has to be
# carried or respected, and woods frame the corridor rather than filling dead ground. Each hole also has its own
# landform (see build_course_islands.landform): how the ground falls from tee to green, which way the fairway is
# cambered (camber > 0 tips it down to the left, < 0 down to the right), how high the rough banks rise either side,
# and whether the green sits up on a plateau (green > 0) or down in a bowl.
HOLES = {
    2: dict(name='Rhododendron', par=4, aim=(185, 0),
            fairways=[path([(28, 0), (120, -2), (185, 4), (225, 24), (245, 50)], 34)],
            green=((262, 72), 15), bunkers=[(205, -8, 7), (196, 22, 5), (249, 88, 5), (278, 60, 5)],
            woods=[ellipse(150, 55, 30, 16, 30), ellipse(100, -44, 55, 13), ellipse(288, 98, 18, 10)],
            ponds=[ellipse(214, 46, 13, 9, 35)], streams=[], footbridges=[],
            landform=dict(kind='downhill', drop=7.0, camber=-0.06, wall_left=5.0, wall_right=2.5, green=0.8),
            mix={'Oak_A': 3, 'Oak_B': 3, 'Birch': 2, 'Bush_Flowering': 5, 'Bush_Round': 2}),
    3: dict(name='Twin Brooks', par=4, aim=(225, 24),
            fairways=[path([(25, 0), (78, 0)], 30), path([(135, -20), (230, -26), (298, -12)], 22),
                      path([(150, 20), (240, 28), (300, 14)], 22)],
            green=((330, 0), 16), bunkers=[(225, -30, 6), (252, 30, 6), (316, -19, 5), (346, 17, 5)],
            woods=[path([(152, 0), (290, 1)], 12), ellipse(60, -40, 30, 10), ellipse(200, 55, 60, 10)],
            ponds=[], streams=[([(80, -60), (104, -12), (118, 20), (138, 66)], 7)],
            footbridges=[((110, 5), 0.0, 13)],
            landform=dict(kind='terraced', drop=7.0, camber=0.03, wall_left=3.0, wall_right=3.5, green=1.0),
            mix={'Oak_A': 3, 'Oak_B': 2, 'Poplar': 2, 'Birch': 3, 'Bush_Round': 3}),
    # Owner's edit kept: the lake in the middle of the fairway (lay up or carry it), the brook off the tee and the
    # big bunker front left of the green. Now it dips down to the lake and climbs back to the green.
    4: dict(name='Lakeside', par=5, aim=(140, 0),
            fairways=[path([(30, 0), (150, 5), (300, -5), (440, 0)], 38)],
            green=((478, 0), 17), bunkers=[(460, -19, 5), (468, 21, 5), (497, 18, 4), (132, -25, 6), (305, 18, 6),
                                           ellipse(425, -12, 32, 18)],
            woods=[ellipse(200, -56, 90, 14), ellipse(425, -46, 50, 13), ellipse(120, 45, 40, 11)],
            ponds=[ellipse(50, -42, 16, 11), ellipse(208, 0, 55, 23)],
            streams=[([(56, -32), (72, 0), (88, 42)], 6)], footbridges=[((72, 0), 0.0, 11)],
            landform=dict(kind='valley', drop=6.0, camber=0.04, wall_left=4.0, wall_right=3.0, green=1.2),
            mix={'Oak_A': 3, 'Oak_B': 3, 'Poplar': 3, 'Birch': 1, 'Bush_Round': 3}),
    # Dogleg left, uphill: the pond sits inside the corner for anyone cutting it; bunker through the corner.
    5: dict(name='Last Fir', par=4, aim=(175, 0),
            fairways=[path([(30, 0), (160, 0), (230, -22), (275, -58)], 34)],
            green=((298, -86), 15), bunkers=[(205, 18, 7), (283, -104, 5), (314, -70, 4)],
            woods=[ellipse(140, -52, 30, 13), ellipse(120, 42, 60, 12), ellipse(320, -40, 22, 14)],
            ponds=[ellipse(212, -44, 22, 12, -30)], streams=[], footbridges=[],
            landform=dict(kind='uphill', rise=5.0, camber=0.05, wall_left=2.0, wall_right=5.0, green=1.5),
            mix={'Pine': 7, 'Oak_B': 1, 'Birch': 1, 'Bush_Round': 2}),
    6: dict(name='Stepping Stones', par=3, aim=(150, 4),
            fairways=[path([(100, 0), (128, 3)], 22)],
            green=((150, 4), 17), bunkers=[(137, -17, 5), (166, 23, 5)],
            woods=[ellipse(20, -46, 25, 12), ellipse(108, -46, 30, 12), ellipse(118, 50, 30, 12)],
            ponds=[], streams=[([(40, -62), (55, -15), (62, 15), (76, 62)], 8)],
            footbridges=[((52, -26), 0.0, 13), ((65, 30), 0.0, 13)],
            landform=dict(kind='downhill', drop=8.0, camber=0.0, wall_left=3.0, wall_right=3.0, green=0.0),
            mix={'Oak_A': 2, 'Pine': 3, 'Birch': 2, 'Bush_Round': 3, 'Bush_Flowering': 2}),

    # Holes 7-18 follow the owner's second set of reference maps, in the order they were sent.
    # Over a crest, then down to a green with the lake biting in front left; bunker right where drives finish.
    7: dict(name='Lakeside Bend', par=4, aim=(230, -8),
            fairways=[path([(30, 0), (150, 0), (255, -12)], 36)],
            green=((315, -24), 16), bunkers=[(215, 14, 7), (302, 0, 5), (336, -6, 5)],
            woods=[ellipse(180, 50, 90, 12), ellipse(115, -45, 45, 12), ellipse(345, 20, 22, 12)],
            ponds=[ellipse(278, -44, 32, 13, -20)], streams=[], footbridges=[],
            landform=dict(kind='ridge', rise=4.0, drop=6.0, camber=0.05, wall_left=1.5, wall_right=5.0, green=0.3),
            mix={'Oak_A': 3, 'Oak_B': 3, 'Birch': 2, 'Poplar': 2, 'Bush_Round': 2}),
    8: dict(name='The Crossing', par=3, aim=(150, 0),
            fairways=[path([(18, 0), (38, 0)], 18)],
            green=((152, 0), 16), bunkers=[(141, -19, 5), (162, 19, 5), (168, -13, 4), (134, 16, 4)],
            woods=[ellipse(30, -45, 20, 10), ellipse(196, 4, 12, 28), ellipse(40, 45, 22, 10)],
            ponds=[ellipse(90, -8, 38, 50)], streams=[], footbridges=[],
            landform=dict(kind='plunge', drop=8.0, camber=0.0, wall_left=3.0, wall_right=3.0, green=0.5),
            mix={'Pine': 5, 'Oak_B': 2, 'Birch': 1, 'Bush_Round': 2}),
    # A pond sits in the middle of the landing zone: lay up short, squeeze past either side, or carry it.
    9: dict(name='Long Water', par=4, aim=(240, -5),
            fairways=[path([(25, 0), (160, -2), (305, -12)], 32)],
            green=((336, -20), 16), bunkers=[(215, -18, 6), (250, -22, 5), (318, -39, 5), (353, -3, 5), (349, -37, 4)],
            woods=[ellipse(160, -52, 120, 12)],
            ponds=[ellipse(172, -3, 26, 10, -4)], streams=[], footbridges=[],
            landform=dict(kind='downhill', drop=6.0, camber=-0.04, wall_left=5.0, wall_right=3.0, green=0.6),
            mix={'Oak_A': 3, 'Oak_B': 2, 'Poplar': 2, 'Bush_Flowering': 3, 'Bush_Round': 2}),
    10: dict(name='Over the Top', par=3, aim=(160, -10),
             fairways=[path([(120, -18), (135, -15)], 16)],
             green=((162, -10), 16), bunkers=[(147, -28, 5), (175, 8, 5)],
             woods=[ellipse(172, 40, 30, 12), ellipse(30, -45, 22, 10)],
             ponds=[ellipse(82, 2, 42, 52, 15)], streams=[], footbridges=[],
             landform=dict(kind='uphill', rise=4.0, camber=0.0, wall_left=3.0, wall_right=3.0, green=1.5),
             mix={'Oak_A': 2, 'Birch': 3, 'Pine': 2, 'Bush_Round': 3}),
    # Par 5 in steps: a pond sits in the lay-up zone (go left of it, right of it, or carry it), bunker at the drive.
    11: dict(name='Grand Sweep', par=5, aim=(250, 0),
             fairways=[path([(30, 0), (200, 0), (340, 30), (440, 70)], 38)],
             green=((476, 86), 17), bunkers=[(240, -12, 7), (300, 52, 7), (460, 106, 5), (494, 67, 5)],
             woods=[ellipse(200, -45, 120, 12), ellipse(225, 55, 60, 14), ellipse(482, 22, 30, 12)],
             ponds=[ellipse(365, 40, 20, 12, 20)], streams=[], footbridges=[],
             landform=dict(kind='terraced', drop=8.0, camber=-0.04, wall_left=4.0, wall_right=2.5, green=1.0),
             mix={'Oak_A': 3, 'Oak_B': 3, 'Birch': 2, 'Poplar': 2, 'Bush_Round': 2}),
    # Dogleg right that sweeps down and to the right (the owner's reference), a pond tucked inside the corner.
    12: dict(name='Corner Pocket', par=4, aim=(215, 0),
             fairways=[path([(30, 0), (200, 0), (262, 25), (290, 70)], 32)],
             green=((300, 100), 15), bunkers=[(222, -12, 7), (318, 86, 5), (281, 115, 4)],
             woods=[ellipse(160, 58, 35, 16, 20), ellipse(150, -45, 100, 12), ellipse(335, 40, 20, 15)],
             ponds=[ellipse(236, 52, 16, 11, 40)], streams=[], footbridges=[],
             landform=dict(kind='downhill', drop=8.0, camber=-0.07, wall_left=5.5, wall_right=1.5, green=0.5),
             mix={'Oak_A': 3, 'Oak_B': 3, 'Poplar': 1, 'Birch': 1, 'Bush_Round': 3}),
    13: dict(name='Creek Run', par=5, aim=(250, 0),
             fairways=[path([(25, 0), (95, 0)], 30), path([(148, 0), (300, 5), (452, 0)], 40)],
             green=((490, 0), 17), bunkers=[(255, 16, 7), (405, -18, 7), (378, -22, 6), (470, -21, 6), (506, 20, 5)],
             woods=[ellipse(262, -56, 180, 12), ellipse(300, 56, 150, 12)],
             ponds=[], streams=[([(116, -72), (121, -20), (127, 20), (139, 72)], 7)], footbridges=[((124, 0), 0.0, 12)],
             landform=dict(kind='terraced', drop=7.0, camber=0.04, wall_left=3.5, wall_right=3.5, green=1.2),
             mix={'Oak_A': 3, 'Oak_B': 3, 'Pine': 2, 'Birch': 2, 'Bush_Round': 2}),
    14: dict(name='Cross Bunkers', par=4, aim=(215, -5),
             fairways=[path([(30, 0), (170, 0), (290, -30), (340, -45)], 30)],
             green=((366, -52), 15), bunkers=[(186, -9, 4), (200, 2, 4), (212, -15, 4), (353, -70, 4), (382, -33, 4), (373, -70, 3)],
             woods=[ellipse(185, -52, 85, 14, -10), ellipse(210, 40, 120, 12)],
             ponds=[], streams=[], footbridges=[],
             landform=dict(kind='ridge', rise=4.0, drop=7.0, camber=-0.04, wall_left=4.0, wall_right=4.0, green=0.5),
             mix={'Pine': 4, 'Oak_B': 2, 'Oak_A': 2, 'Bush_Round': 3}),
    # A burn now crosses the narrows at the bottom of the valley: carry it or lay up short.
    15: dict(name='The Narrows', par=4, aim=(230, 0),
             fairways=[path([(25, 0), (200, -5), (322, 5)], 26)],
             green=((350, 20), 14), bunkers=[(245, -8, 5), (363, 4, 4), (340, 37, 4)],
             woods=[ellipse(172, -36, 150, 10), ellipse(172, 34, 150, 10)],
             ponds=[], streams=[([(150, -60), (160, -10), (168, 20), (175, 60)], 6)],
             footbridges=[((164, 3), 0.0, 11)],
             landform=dict(kind='valley', drop=6.0, camber=0.0, wall_left=5.0, wall_right=5.0, green=1.0),
             mix={'Oak_A': 2, 'Oak_B': 3, 'Birch': 2, 'Bush_Round': 3, 'Bush_Flowering': 2}),
    # Drives through the corner run into the lake; waste bunker inside the dogleg, another left of the green.
    16: dict(name='Waste Lake', par=4, aim=(170, 20),
             fairways=[path([(30, 0), (130, 0), (190, 34)], 30)],
             green=((272, 56), 15), bunkers=[ellipse(150, 58, 30, 13), ellipse(262, -8, 34, 17), (258, 76, 5)],
             woods=[ellipse(60, -40, 30, 10)],
             ponds=[ellipse(204, 2, 30, 14, 25)], streams=[], footbridges=[],
             landform=dict(kind='downhill', drop=6.0, camber=0.05, wall_left=1.5, wall_right=4.0, green=0.8),
             mix={'Pine': 3, 'Oak_A': 2, 'Bush_Round': 3}),
    # Tee perched high above the fairway; a pond guards the green's right.
    17: dict(name='Harbour Wall', par=4, aim=(215, -5),
             fairways=[path([(30, 0), (170, 0), (260, -20)], 32)],
             green=((302, -36), 15), bunkers=[ellipse(250, -42, 22, 6, 20), (198, -12, 6)],
             woods=[ellipse(140, -45, 100, 12)],
             ponds=[ellipse(322, 4, 22, 26)], streams=[], footbridges=[],
             landform=dict(kind='plunge', drop=7.0, camber=-0.05, wall_left=4.0, wall_right=3.0, green=0.5),
             mix={'Oak_A': 2, 'Oak_B': 2, 'Poplar': 3, 'Bush_Round': 3}),
    # Home hole: carry the waste bunker, then up to a raised last green with a pond short left.
    18: dict(name='Home Waste', par=4, aim=(240, -8),
             fairways=[path([(30, 0), (108, 0)], 30), path([(192, -14), (300, -5)], 30)],
             green=((332, -5), 16), bunkers=[ellipse(150, 4, 38, 30), (338, 16, 5), (349, -4, 4), (352, 24, 4)],
             woods=[ellipse(190, 50, 110, 12)],
             ponds=[ellipse(316, -30, 14, 8, 10)], streams=[], footbridges=[],
             landform=dict(kind='uphill', rise=5.0, camber=0.03, wall_left=3.0, wall_right=3.0, green=1.5),
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
