"""Build the floating-island course: holes 1-6, the jungle rope bridges between them, vines, fog and tree plans.

    python Art/Blender/build_course_islands.py            all holes 1-6 plus bridges, then a course preview
    python Art/Blender/build_course_islands.py -- 3 4     just those holes (bridges need their neighbours)
    ... --no-render                                        skip the Cycles previews

Per hole n (world coordinates, Unreal metres; Scripts/apply_floating_islands.py places them at the origin):
  SM_Hnn_IslandTop / IslandRock             as hole 1 (build_floating_islands.py), placed, turned and raised
  SM_Hnn_Vines     ivy and roots hanging off every cliff edge (sway in the leaf shader), moss on the rock
  SM_Hnn_Water     ponds and brooks (Water surface: a penalty, and the buggy won't drive in)
  SM_Hnn_Props     wooden footbridges over the brooks (the buggy drives over them)
  Holenn_spots.json  tee, aim, cup, tee markers, par/name, the tree plan ("forest") and fog patches
Course-wide:
  SM_Bridge_nn_mm  a sagging jungle rope bridge from hole n's green end to hole n+1's tee island
"""
import json
import math
import random
import sys
from pathlib import Path

import bpy
import numpy as np
import heapq

import shapely
from shapely import affinity
from mathutils import Vector
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import nearest_points, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_floating_islands as B  # noqa: E402
import course_layout as C  # noqa: E402
import sl_common as sl  # noqa: E402

OUT = B.OUT
TREE_KINDS = ['Oak_A', 'Oak_B', 'Poplar', 'Pine', 'Birch', 'Bush_Round', 'Bush_Flowering']
WATER_LEVEL = -0.6   # water surface below the hole's tee height (m)
STEEL = 1.0


# ---------------------------------------------------------------- layouts

PATH_EDGE = 0.2  # m: half the soft band along a footpath's border


def footpaths(number, land, extra=None):
    """Footpaths drawn in the editor (Scripts/apply_floating_islands.py export_paths -> Paths.json) that cross this
    hole's island, as one local-coordinate polygon kept 1.5 m inside the rim (the rim must match the rock)."""
    source = OUT / 'Paths.json'
    shapes = [extra] if extra is not None else []
    for path in (json.loads(source.read_text()).get('paths', []) if source.is_file() else []):
        pts = np.array(path['points'], float)
        lx, ly = C.to_local(number, pts[:, 0], pts[:, 1])
        if len(pts) >= 2:
            shapes.append(LineString(np.column_stack([lx, ly])).buffer(path.get('width', 3.0) / 2, 16))
    if not shapes:
        return None
    area = unary_union(shapes).intersection(land.buffer(-1.5))
    area = shapely.set_precision(area, 0.05)
    return None if area.is_empty or area.area < 1.0 else area


def design_new(number):
    """Island shape and play regions of holes 2-6 (local metres)."""
    h = C.HOLES[number]
    fairways = unary_union(h['fairways'])
    (cx, cy), gr = h['green']
    green = Point(cx, cy).buffer(gr, 96)
    bunkers = [b if hasattr(b, 'geom_type') else Point(b[0], b[1]).buffer(b[2], 64) for b in h['bunkers']]
    tee = box(-4, -6, 4, 6)
    ponds = list(h['ponds'])
    streams = [C.path(pts, w) for pts, w in h['streams']]
    woods = unary_union(h['woods']) if h['woods'] else Point(0, 0).buffer(0.01)

    essentials = [fairways.buffer(22), green.buffer(20), tee.buffer(24), woods.buffer(7)]
    if h.get('stadium'):
        essentials.append(green.buffer(STADIUM_FRONT + STADIUM_TIERS * 1.1 + 12))  # room round the 18th green for the stands
    essentials += [b.buffer(10) for b in bunkers] + [p.buffer(10) for p in ponds]
    essentials += [LineString(pts).buffer(4) for pts, _ in h['streams']]
    # Solid grass landings at both ends of every footbridge, so you can walk (and drive) off it onto land.
    for (fx, fy), heading, length in h['footbridges']:
        d = np.array([math.cos(math.radians(heading)), math.sin(math.radians(heading))])
        essentials.append(LineString([np.array((fx, fy)) - d * (length / 2 + 9), np.array((fx, fy)) + d * (length / 2 + 9)]).buffer(6))
    land = unary_union(essentials).buffer(8, 24).buffer(-8, 24)
    land = B.wobble(land, 6.0, 42.0, number * 7 + 1,
                    keep_inside=unary_union([fairways.buffer(8), green.buffer(10 if not h.get('stadium') else STADIUM_FRONT + STADIUM_TIERS * 1.1 + 8), tee.buffer(14)] + [b.buffer(5) for b in bunkers]))
    if isinstance(land, MultiPolygon):
        land = max(land.geoms, key=lambda g: g.area)

    water = unary_union(ponds + streams).intersection(land.buffer(-1.5)) if (ponds or streams) else None
    wet = water if water is not None and not water.is_empty else None
    blocked = unary_union([b for b in bunkers] + [green, tee] + ([wet] if wet else []))
    regions = {
        B.BUNKER: unary_union(bunkers).intersection(land),
        B.GREEN: green.difference(unary_union(bunkers)),
        B.TEE: tee,
    }
    regions[B.FAIRWAY] = fairways.intersection(land).difference(blocked)
    regions[B.ROUGH] = land.difference(unary_union([regions[B.BUNKER], regions[B.GREEN], regions[B.FAIRWAY], tee]))
    return dict(land=land, main=land, regions=regions, fairways=fairways, green=green, bunkers=bunkers, tee=tee,
                cup=(cx, cy), pads=[((-14, 0), 9)], water=wet, woods=woods, streams=streams, ponds=ponds,
                footbridges=h['footbridges'], trees=[], floaters=[], landform=h.get('landform'), stadium=h.get('stadium', False))


def layout_for(number):
    layout = B.design_hole(1, B.hole_layouts()[0]) if number == 1 else design_new(number)
    return reshape_bunkers(number, layout)


# ---------------------------------------------------------------- bunkers

def organic_blob(centre, radius, rng, stretch=(1.0, 1.7), turn=35.0):
    """A one-off bunker outline: a stretched, lobed, turned blob (sometimes with a second lobe, kidney-like)."""
    theta = np.linspace(0, 2 * np.pi, 72, endpoint=False)
    k = [rng.uniform(0.05, 0.18), rng.uniform(0.03, 0.12), rng.uniform(0.0, 0.07)]
    phase = [rng.uniform(0, 2 * np.pi) for _ in range(3)]
    rr = 1 + k[0] * np.sin(2 * theta + phase[0]) + k[1] * np.sin(3 * theta + phase[1]) + k[2] * np.sin(5 * theta + phase[2])
    aspect = rng.uniform(*stretch)
    pts = np.column_stack([np.cos(theta) * rr * radius * math.sqrt(aspect), np.sin(theta) * rr * radius / math.sqrt(aspect)])
    blob = Polygon(pts).buffer(0)
    if rng.random() < 0.3:
        a = rng.uniform(0, 2 * np.pi)
        blob = blob.union(Point(math.cos(a) * radius * 0.75, math.sin(a) * radius * 0.5).buffer(radius * rng.uniform(0.45, 0.6), 32))
    blob = affinity.rotate(blob, rng.uniform(-turn, turn), origin=(0, 0))
    blob = blob.buffer(0.8, 16).buffer(-0.8, 16)
    return affinity.translate(blob, centre[0], centre[1])


def reshape_bunkers(number, layout):
    """Owner's brief: bunkers belong on the fairway (the rough is hazard enough), every one a different shape,
    deeper, some deeper than others. Fairway bunkers move in so most of their sand is on the fairway; greenside
    bunkers hug the green; big waste bunkers keep their place. Depths go in layout['bunker_depths']."""
    rng = random.Random(number * 7919)
    fair, green, land = layout['fairways'], layout['green'], layout['land']
    gc = green.centroid
    gr = math.sqrt(green.area / math.pi)
    cup = Point(*layout['cup'])
    wet = layout.get('water')
    safe = land.buffer(-4).difference(layout['tee'].buffer(12)).difference(cup.buffer(6))
    if wet is not None:
        safe = safe.difference(wet.buffer(3))
    bunkers, depths = [], []
    for b in layout['bunkers']:
        c = b.centroid
        r = math.sqrt(b.area / math.pi)
        if c.distance(green) < 12:
            r = min(max(r, 3.5), 7.5)
            d = np.array([c.x - gc.x, c.y - gc.y])
            d = d / (np.linalg.norm(d) + 1e-9)
            centre = (gc.x + d[0] * (gr + 0.9 * r), gc.y + d[1] * (gr + 0.9 * r))
            # Tight to the green with a thin grass collar (outlines that cross each other upset the mesher).
            shape = organic_blob(centre, r, rng, (1.0, 1.5), 90.0).difference(green.buffer(0.8)).difference(fair.buffer(1.0))
            depth = rng.uniform(1.1, 1.9)
        elif r > 14:
            shape = organic_blob((c.x, c.y), r, rng, (0.9, 1.3), 20.0).difference(fair.buffer(1.0))
            depth = rng.uniform(0.5, 0.9)
        else:
            # On the fairway: wholly inside it, a metre in from its edge.
            room = fair.buffer(-1.0)
            r = min(max(r, 4.0), 10.0)
            for _ in range(4):
                target = room.buffer(-1.25 * r)
                if not target.is_empty:
                    break
                r *= 0.75
            if target.is_empty:
                continue
            centre = (c.x, c.y) if target.contains(c) else nearest_points(target, c)[0].coords[0]
            shape = organic_blob(centre, r, rng).intersection(room)
            depth = rng.uniform(0.7, 1.4)
        shape = shape.intersection(safe)
        if isinstance(shape, MultiPolygon):
            shape = max(shape.geoms, key=lambda g: g.area)
        if shape.is_empty or shape.area < 6 or any(shape.distance(o) < 2.5 for o in bunkers):
            continue
        # Even 0.8 m spacing round the outline (as every other outline): tiny steps make the mesher over-refine.
        ring = shape.exterior
        count = max(12, int(ring.length / B.EDGE_SPACING))
        bunkers.append(Polygon([ring.interpolate(i / count, normalized=True).coords[0] for i in range(count)]).buffer(0))
        depths.append(round(depth, 2))
    land_ = layout['land']
    tee = layout['tee']
    blocked_water = [wet] if wet is not None else []
    regions = {
        B.BUNKER: unary_union(bunkers).intersection(land_) if bunkers else Polygon(),
        B.GREEN: green.difference(unary_union(bunkers)) if bunkers else green,
        B.TEE: tee,
    }
    regions[B.FAIRWAY] = fair.intersection(land_).difference(unary_union(bunkers + [green, tee] + blocked_water))
    regions[B.ROUGH] = land_.difference(unary_union([regions[B.BUNKER], regions[B.GREEN], regions[B.FAIRWAY], tee]))
    regions = {k: v for k, v in regions.items() if not v.is_empty}
    return dict(layout, bunkers=bunkers, bunker_depths=depths, regions=regions)


# ---------------------------------------------------------------- buggy paths

CART_WIDTH = 3.2        # m
CART_OFFSET = 7.0       # m: the path likes to run this far off the edge of the fairway, in the rough
ANCHORS = {}            # hole -> {'in': (x, y), 'out': (x, y)} local metres; filled in main() from the bridges
CAR_PARK_EXIT = (-73.0, -30.0)  # hole 1: the edge of the clubhouse pad nearest the first tee
HAND_PATHS = set()      # holes whose buggy paths the owner laid by hand
SOFT_PATHS = False      # --soft-paths: no path borders in the mesh (fallback if the mesher chokes on them)


def _route(cost, xs, ys, start, goal):
    """Cheapest 8-connected route over the cost grid between two cells (Dijkstra); None if cut off."""
    ny, nx = cost.shape
    best = np.full(cost.shape, np.inf)
    back = {}
    best[start] = 0.0
    heap = [(0.0, start)]
    steps = [(-1, -1, 1.414), (-1, 0, 1), (-1, 1, 1.414), (0, -1, 1), (0, 1, 1), (1, -1, 1.414), (1, 0, 1), (1, 1, 1.414)]
    while heap:
        d, (j, i) = heapq.heappop(heap)
        if (j, i) == goal:
            break
        if d > best[j, i]:
            continue
        for dj, di, length in steps:
            jj, ii = j + dj, i + di
            if 0 <= jj < ny and 0 <= ii < nx and np.isfinite(cost[jj, ii]):
                nd = d + length * 0.5 * (cost[j, i] + cost[jj, ii])
                if nd < best[jj, ii]:
                    best[jj, ii] = nd
                    back[(jj, ii)] = (j, i)
                    heapq.heappush(heap, (nd, (jj, ii)))
    if not np.isfinite(best[goal]):
        return None, np.inf
    cells = [goal]
    while cells[-1] != start:
        cells.append(back[cells[-1]])
    cells.reverse()
    return [(xs[i], ys[j]) for j, i in cells], best[goal]


def cart_path(number, layout):
    """The buggy path (local LineString): from where you arrive (the rope bridge, or the car park on hole 1) past
    the side of the tee, down one side of the hole in the rough a few metres off the fairway, to the side of
    the green, and on to the bridge to the next hole. It keeps off greens, tees, bunkers and water (brooks are
    crossed only on the footbridges) and away from the cliff edge."""
    land, step = layout['land'], 2.0
    minx, miny, maxx, maxy = land.bounds
    xs, ys = np.arange(minx, maxx, step), np.arange(miny, maxy, step)
    gx, gy = np.meshgrid(xs, ys)
    px, py = gx.ravel(), gy.ravel()
    pts = shapely.points(px, py)
    # Off the cliff edge (a hard 2 m, and it prefers 6 m) but through narrow necks of land where it must.
    cost = np.where(shapely.contains_xy(land.buffer(-2.0), px, py), 1.0, np.inf)
    cost = cost + np.where(shapely.distance(land.exterior, pts) < 6.0, 4.0, 0.0)
    anchors = ANCHORS.get(number, {})
    for a in anchors.values():
        near = (np.hypot(px - a[0], py - a[1]) < 7) & shapely.contains_xy(land, px, py)
        cost[near] = 1.0
    wet = layout.get('water')
    if wet is not None:
        cost[shapely.contains_xy(wet.buffer(1.0), px, py)] = np.inf
        for (cx, cy), heading, length in layout.get('footbridges', []):
            d = np.array([math.cos(math.radians(heading)), math.sin(math.radians(heading))])
            deck = LineString([np.array((cx, cy)) - d * length / 2, np.array((cx, cy)) + d * length / 2])
            approach = LineString([np.array((cx, cy)) - d * (length / 2 + 10), np.array((cx, cy)) + d * (length / 2 + 10)])
            cost[shapely.distance(deck, pts) < 1.8] = 1.0  # the deck itself
            cost[(shapely.distance(approach, pts) < 1.8) & shapely.contains_xy(land, px, py)] = 1.0  # onto the banks
    fair_d = shapely.distance(layout['fairways'], pts)
    cost = cost + np.where(fair_d == 0, 6.0, 0.15 * np.clip(np.abs(fair_d - CART_OFFSET), 0, 20))
    hazards = unary_union([layout['green'].buffer(6), layout['tee'].buffer(4)] + [b.buffer(4) for b in layout['bunkers']])
    cost = cost + np.where(shapely.contains_xy(hazards, px, py), 80.0, 0.0)
    if layout.get('stadium'):
        cost[shapely.contains_xy(stadium_zone(layout), px, py)] = np.inf
    # ...and it keeps a respectful distance from greens and bunkers where it has room.
    clearance = unary_union([layout['green'].buffer(12)] + [b.buffer(7) for b in layout['bunkers']])
    cost = cost + np.where(shapely.contains_xy(clearance, px, py), 3.0, 0.0)
    cost = cost.reshape(gx.shape)

    def cell(p):
        j = int(np.clip(round((p[1] - miny) / step), 0, len(ys) - 1))
        i = int(np.clip(round((p[0] - minx) / step), 0, len(xs) - 1))
        if np.isfinite(cost[j, i]):
            return (j, i)
        ok = np.argwhere(np.isfinite(cost))
        k = np.argmin((ok[:, 0] - j) ** 2 + (ok[:, 1] - i) ** 2)
        return tuple(ok[k])

    cx, cy = layout['cup']
    gr = math.sqrt(layout['green'].area / math.pi)
    u = np.array([cx, cy]) / (math.hypot(cx, cy) + 1e-9)
    v = np.array([-u[1], u[0]])
    start = anchors.get('in', (-6.0, 0.0))
    best = None
    for side in (-1, 1):
        tee_side = (-2.0, 13.0 * side)
        green_side = tuple(np.array([cx, cy]) - u * gr * 0.3 + v * side * (gr + 11))
        stops = [start, tee_side, green_side] + ([anchors['out']] if 'out' in anchors else [])
        route, total = [], 0.0
        for a, b in zip(stops[:-1], stops[1:]):
            leg, c = _route(cost, xs, ys, cell(a), cell(b))
            if leg is None:
                total = np.inf
                break
            route += leg if not route else leg[1:]
            total += c
        if total < (best[0] if best else np.inf):
            best = (total, route)
    if not best or len(best[1]) < 2:
        return None
    line = np.array(best[1])
    for _ in range(3):  # Chaikin smoothing: grid steps become gentle curves
        q = 0.75 * line[:-1] + 0.25 * line[1:]
        r = 0.25 * line[:-1] + 0.75 * line[1:]
        line = np.vstack([line[:1], np.column_stack([q, r]).reshape(-1, 2), line[-1:]])
    return LineString(line).simplify(0.3)


def hole_paths(number, layout):
    """(cart path line, all path area) for a hole: the automatic buggy path plus any drawn in Paths.json."""
    # Hole 1's paths were laid by hand in the editor (decals), so it gets no automatic one.
    cart = cart_path(number, layout) if number not in HAND_PATHS else None
    cart_area = None
    if cart is not None:
        # Off greens, tees and bunkers, and it stops half a metre short of the fairway where it crosses one.
        cart_area = cart.buffer(CART_WIDTH / 2, 12).difference(
            unary_union([layout['green'].buffer(0.5), layout['tee'].buffer(0.5), layout['fairways'].buffer(0.5)]
                        + [b.buffer(0.5) for b in layout['bunkers']]))
    paths = footpaths(number, layout['land'], cart_area)
    if paths is not None:
        # One tidy outline per path (points no closer than ~0.3 m): its border becomes a mesh edge, so the path is
        # crisp without flooding the mesh with slivers.
        paths = shapely.set_precision(paths.simplify(0.25), 0.05)
    return cart, paths


def bunker_floors(layout, ground):
    """Each bunker's floor is dug into the slope rather than draped over it; this is the mean height of its rim."""
    floors = []
    for b, depth in zip(layout['bunkers'], layout.get('bunker_depths', [])):
        ring = b.exterior
        rim = np.array([ring.interpolate(i / 64, normalized=True).coords[0] for i in range(64)])
        floors.append(float(np.mean(ground(rim[:, 0], rim[:, 1]))))
    return floors


def bunker_relief(x, y, h, layout, floors):
    """The bunkers cut into the ground h: inside, a steep face dropping to the level sand floor (tall on the uphill
    side, short on the downhill side); outside, a small grassy lip round the rim, so they read as real hollows."""
    h = h.copy()
    pts = shapely.points(x, y)
    for b, depth, floor in zip(layout['bunkers'], layout.get('bunker_depths', []), floors):
        minx, miny, maxx, maxy = b.bounds
        near = (x > minx - 3) & (x < maxx + 3) & (y > miny - 3) & (y < maxy + 3)
        if not near.any():
            continue
        inside = shapely.contains_xy(b, x[near], y[near])
        edge = shapely.distance(b.boundary, pts[near])
        wall = min(2.2, 0.35 * math.sqrt(b.area / math.pi) + 0.8)
        # Grass lip: zero on the sand's edge, rising to a crest ~0.6 m out and easing back into the turf by 2.4 m.
        lip = 0.2 * depth * np.sin(np.pi * np.clip(edge / 2.4, 0, 1)) ** 1.5
        w = B.smooth(edge / wall)
        # Nearly level sand (a third of the slope left in it), always at least 40% of the depth below the grass:
        # a clear cut face on the uphill side, a low lip on the downhill side.
        sand = np.minimum(0.35 * h[near] + 0.65 * floor - depth, h[near] - 0.4 * depth)
        h[near] = np.where(inside, h[near] * (1 - w) + sand * w, h[near] + lip)
    return h


# Each hole's big shape, in turn round the course so neighbours differ: how the ground falls from tee to green.
LANDFORMS = ['downhill', 'terraced', 'uphill', 'valley', 'ridge', 'plunge']
RELIEF = 2.3      # scales every hole's drops and rises (the designs' numbers are in 'gentle' metres)
BANKS = 1.7       # scales the rough banks either side of the fairways


def landform(number, layout):
    """The hole's landform (m, added to the surface): a tee-to-green profile (falls, rises, terraces, a valley or a
    crest), a camber that tips the fairway down to one side, rough banks rising away from the fairway so it sits
    in a corridor, a green set on its own plateau or in a shallow bowl, and a level tee terrace. Ponds and brooks
    get a level floor of their own. Stores the water level in layout['water_offset']."""
    rng = np.random.default_rng(7919 * number)
    # Each hole's design names its landform (course_layout.HOLES[n]['landform']); hole 1 gets a gentle fall.
    spec = layout.get('landform') or dict(kind='downhill', drop=3.0, camber=0.02, wall_left=2.5, wall_right=2.5, green=0.5)
    kind = spec.get('kind', LANDFORMS[(number - 1) % len(LANDFORMS)])
    cx, cy = layout['cup']
    length = max(60.0, math.hypot(cx, cy))
    ux, uy = cx / length, cy / length
    drop = RELIEF * spec.get('drop', rng.uniform(5.0, 9.0))
    rise = RELIEF * spec.get('rise', rng.uniform(3.0, 6.0))

    def step(t, a, b):
        return B.smooth((t - a) / (b - a))

    def profile(t):
        if kind == 'downhill':     # tee high above a fairway that falls away, green at the bottom
            return -drop * step(t, 0.05, 0.55)
        if kind == 'terraced':     # two distinct levels stepping down
            return -0.45 * drop * step(t, 0.24, 0.32) - 0.55 * drop * step(t, 0.64, 0.72)
        if kind == 'uphill':       # climbing to a raised green
            return rise * step(t, 0.35, 0.95)
        if kind == 'valley':       # down into a dip, back up to the green
            return -drop * np.sin(np.pi * np.clip(t, 0, 1)) ** 1.5 + 0.3 * rise * step(t, 0.7, 1.0)
        if kind == 'ridge':        # up over a crest, then falling to the green
            return 0.5 * rise * np.sin(np.pi * np.clip(t / 0.6, 0, 1)) - 0.7 * drop * step(t, 0.55, 0.95)
        return -1.3 * drop * step(t, 0.1, 0.4)   # plunge: a big drop off the tee, then level

    camber = spec.get('camber', 0.0)       # > 0 tips the ground down to the left (-y), < 0 down to the right
    wall_left, wall_right = BANKS * spec.get('wall_left', 3.0), BANKS * spec.get('wall_right', 3.0)
    green_lift = spec.get('green', 0.0)
    fair, green, tee = layout['fairways'], layout['green'], layout['tee']
    land_edge = layout['land'].exterior
    water = layout.get('water')

    def shape(x, y):
        t = (x * ux + y * uy) / length
        lat = -x * uy + y * ux
        pts = shapely.points(x, y)
        h = profile(t) + camber * np.clip(lat, -35, 35)
        fd = shapely.distance(fair, pts)
        # Banks and humps ease off toward the cliff edge, so the rim stays gentle where it meets the rock.
        rim = B.smooth(shapely.distance(land_edge, pts) / 14)
        h = h + np.where(lat > 0, wall_right, wall_left) * B.smooth((fd - 2) / 16) * rim
        # Rolling ground: broad swales and humps down the fairway too, not just in the rough.
        h = h + 1.4 * B.fbm(x / 45, y / 45, 3, number + 300) * rim
        return h, pts

    water_level = 0.0
    if water is not None:
        wx, wy = np.asarray(water.exterior.coords).T if water.geom_type == 'Polygon' else \
            np.concatenate([np.asarray(g.exterior.coords) for g in water.geoms]).T
        water_level = float(np.mean(shape(wx, wy)[0]))
        if water.distance(tee) < 40:
            water_level = min(water_level, -0.4)  # water just off the tee lies below it
    layout['water_offset'] = water_level
    clat = -cx * uy + cy * ux
    green_level = float(profile(1.0) + camber * np.clip(clat, -35, 35) + green_lift)
    if water is not None and water.distance(green) < 30:
        green_level = max(green_level, water_level + 0.8)  # a green beside water stands above it

    def fn(x, y):
        x, y = np.asarray(x, float), np.asarray(y, float)
        h, pts = shape(x, y)
        if water is not None:
            wb = 1 - B.smooth(shapely.distance(water, pts) / 15)
            h = h * (1 - wb) + water_level * wb
        gb = 1 - B.smooth((shapely.distance(green, pts) - 1) / 8)
        h = h * (1 - gb) + green_level * gb
        tb = 1 - B.smooth((shapely.distance(tee, pts) - 2) / 12)
        h = h * (1 - tb)
        for (px, py), pr in layout['pads']:
            h = h * B.smooth((np.hypot(x - px, y - py) - pr) / 12)
        return h
    return fn


def path_bed(local_h, cart):
    """Set the buggy path into the ground: level across its width (cut into slopes like a terrace) and sunk a
    little below the grass, with soft shoulders either side."""
    if cart is None:
        return local_h
    half = CART_WIDTH / 2

    def fn(x, y):
        x, y = np.asarray(x, float), np.asarray(y, float)
        h = local_h(x, y)
        pts = shapely.points(x, y)
        d = shapely.distance(cart, pts)
        near = d < half + 2.5
        if not near.any():
            return h
        along = shapely.line_locate_point(cart, pts[near])
        centre = shapely.get_coordinates(shapely.line_interpolate_point(cart, along))
        level = local_h(centre[:, 0], centre[:, 1]) - 0.12
        w = 1 - B.smooth((d[near] - half) / 2.5)
        h = h.copy()
        h[near] = h[near] * (1 - w) + level * w
        return h
    return fn


def height_fn(number, layout):
    """Local surface height (m, relative to the tee) as a function of local x, y."""
    plain = dict(layout, bunkers=[])  # the old shallow round dips are replaced by bunker_relief
    land_shape = landform(number, layout)
    level = layout['water_offset']

    def ground(x, y):
        x, y = np.asarray(x, float), np.asarray(y, float)
        return B.top_height(x, y, plain, number) + land_shape(x, y)
    floors = bunker_floors(layout, ground)
    cx, cy = layout['cup']
    cup_level = float(ground(np.array([cx]), np.array([cy]))[0])

    def base(x, y):
        x, y = np.asarray(x, float), np.asarray(y, float)
        h = bunker_relief(x, y, ground(x, y), layout, floors)
        # A level patch round the hole so the cup sits flush on a sloping green.
        w = 1 - B.smooth((np.hypot(x - cx, y - cy) - 0.6) / 1.6)
        return h * (1 - w) + cup_level * w
    water = layout.get('water')
    if water is None:
        return base

    def with_water(x, y):
        h = base(x, y)
        pts = shapely.points(x, y)
        outside = shapely.distance(water, pts)
        inside = shapely.distance(water.boundary, pts) * (outside == 0)
        # Keep the banks above the water line, then drop into a basin under the surface.
        bank = 1 - B.smooth(outside / 8)
        h = np.where(outside > 0, h * (1 - bank) + np.maximum(h, level + 0.15) * bank, h)
        basin = B.smooth(inside / 2.5)
        return np.where(outside > 0, h, level + 0.1 * (1 - basin) - 1.8 * basin)
    return with_water


# ---------------------------------------------------------------- mesh helpers (world placement)

def place(number, verts):
    """Local (x, y, z) -> world, adding the hole's height."""
    wx, wy = C.to_world(number, verts[:, 0], verts[:, 1])
    return np.column_stack([wx, wy, verts[:, 2] + C.PLACE[number][2]])


def moss(colours, z, d, x, y, seed):
    """Moss creeping down from the grass lip and in patches on the rock."""
    green = np.array([0.20, 0.30, 0.11])
    patches = B.smooth(0.5 + 1.2 * B.fbm(x / 11, y / 11 + z / 9, 3, seed + 77))
    lip = 1 - B.smooth((d - 0.8) / 4.0)
    amount = np.clip(0.75 * lip * (0.6 + 0.4 * patches) + 0.45 * patches * (1 - lip) * B.smooth((z + 30) / 30), 0, 0.85)
    return colours * (1 - amount[:, None]) + green[None] * amount[:, None]


class Parts:
    """Loose geometry (planks, ropes, posts, vines) with vertex colour RGBA; material 0 bark/wood, 1 leaves."""

    def __init__(self):
        self.v, self.f, self.c, self.m, self.uv = [], [], [], [], []

    def _add(self, verts, faces, colour, mat, alpha, uvs=None):
        base = len(self.v)
        self.v.extend(verts)
        self.uv.extend(uvs if uvs is not None else [None] * len(verts))
        cols = colour if callable(colour) else (lambda p: colour)
        for p in verts:
            self.c.append((*cols(p), alpha(p) if callable(alpha) else alpha))
        self.f.extend([tuple(base + i for i in face) for face in faces])
        self.m.extend([mat] * len(faces))

    def box(self, centre, along, across, half, colour, mat=0, alpha=0.0):
        """Oriented box: half = (length, width, height) half sizes along `along`, `across`, their cross."""
        c, a, b = Vector(centre), Vector(along).normalized(), Vector(across).normalized()
        up = a.cross(b).normalized()
        hl, hw, hh = half
        verts = [tuple(c + a * sx * hl + b * sy * hw + up * sz * hh) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        self._add(verts, faces, colour, mat, alpha)

    def tube(self, points, radius, colour, mat=0, alpha=0.0, sides=5):
        pts = [Vector(p) for p in points]
        verts, faces = [], []
        for i, p in enumerate(pts):
            d = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
            side = d.orthogonal().normalized()
            up = d.cross(side)
            r = radius(i / max(1, len(pts) - 1)) if callable(radius) else radius
            for k in range(sides):
                a = 2 * math.pi * k / sides
                verts.append(tuple(p + (side * math.cos(a) + up * math.sin(a)) * r))
        for i in range(len(pts) - 1):
            for k in range(sides):
                a, b = i * sides + k, i * sides + (k + 1) % sides
                faces.append((a, b, b + sides, a + sides))
        self._add(verts, faces, colour, mat, alpha)

    def ribbon(self, points, width, facing, colour, alpha, mat=2, tile=2.0):
        """A leafy vine card: a strip `width` wide through `points`, facing `facing` (horizontal), UV v along it."""
        side = Vector((-facing[1], facing[0], 0)).normalized()
        verts, uvs, faces = [], [], []
        run = 0.0
        for i, p in enumerate(points):
            p = Vector(p)
            if i:
                run += (p - Vector(points[i - 1])).length
            w = width * (1.0 - 0.35 * i / max(1, len(points) - 1))
            verts += [tuple(p - side * w / 2), tuple(p + side * w / 2)]
            uvs += [(0.0, run / tile), (1.0, run / tile)]
        for i in range(len(points) - 1):
            a = i * 2
            faces.append((a, a + 1, a + 3, a + 2))
        self._add(verts, faces, colour, mat, alpha, uvs)

    def leaf(self, centre, radius, colour, alpha, rng):
        """Small low-poly leaf clump (icosahedron, 20 triangles)."""
        t = (1 + 5 ** 0.5) / 2
        base = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
                (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
        faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
                 (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
                 (6, 2, 10), (8, 6, 7), (9, 8, 1)]
        c = Vector(centre)
        scale = radius / math.sqrt(1 + t * t)
        verts = [tuple(c + Vector((x * rng.uniform(0.8, 1.2), y * rng.uniform(0.8, 1.2), z * 0.7)) * scale) for x, y, z in base]
        tint = tuple(min(1.0, k * rng.uniform(0.85, 1.15)) for k in colour)
        self._add(verts, [f[::-1] for f in faces], tint, 1, alpha)

    def mesh(self, name, mats=('TreeBark', 'TreeLeaves')):
        v = np.asarray(self.v, float)
        verts = [(float(p[0]), float(-p[1]), float(p[2])) for p in v]  # Unreal -> Blender
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, [], [tuple(int(i) for i in f[::-1]) for f in self.f])
        for name_ in mats:
            mesh.materials.append(bpy.data.materials.get(name_) or vc_material(name_))
        mesh.polygons.foreach_set('material_index', np.asarray(self.m, np.int32))
        attribute = mesh.color_attributes.new('Col', 'BYTE_COLOR', 'POINT')
        attribute.data.foreach_set('color_srgb', np.asarray(self.c, np.float32).ravel())
        mesh.color_attributes.active_color = attribute
        uv = mesh.uv_layers.new(name='UVMap')
        for poly in mesh.polygons:
            for li in poly.loop_indices:
                vi = mesh.loops[li].vertex_index
                given = self.uv[vi]
                co = mesh.vertices[vi].co
                uv.data[li].uv = given if given is not None else (co.x + co.y, co.z)
        mesh.validate()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        return obj


def vc_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes['Principled BSDF']
    attr = nodes.new('ShaderNodeVertexColor')
    attr.layer_name = 'Col'
    texture_path = B.TEXTURES / 'T_Vines.png'
    if name == 'Vines' and texture_path.is_file():
        # Preview only (Unreal builds M_Tree_Vines): ivy texture x vertex colour, cut out by its alpha.
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = bpy.data.images.load(str(texture_path), check_existing=True)
        mix = nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        links.new(tex.outputs['Color'], mix.inputs[6])
        links.new(attr.outputs['Color'], mix.inputs[7])
        links.new(mix.outputs[2], bsdf.inputs['Base Color'])
        links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
        mat.blend_method = 'CLIP'
        return mat
    links.new(attr.outputs['Color'], bsdf.inputs['Base Color'])
    return mat


# ---------------------------------------------------------------- vines

VINE_GREENS = [(0.22, 0.42, 0.12), (0.30, 0.50, 0.15), (0.18, 0.34, 0.12), (0.36, 0.52, 0.18)]
ROOT_BROWN = (0.30, 0.20, 0.12)


def hang(parts, rim_xy, outward, top_z, length, rng, leafy):
    """One strand hanging from the rim, drifting away from the cliff as it falls: a leafy ivy card (crossed
    with a second card when long), or a bare root."""
    steps = max(3, int(length / 0.9))
    pts = []
    sway = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)) * 0.25
    for i in range(steps + 1):
        t = i / steps
        p = Vector((rim_xy[0], rim_xy[1], top_z - 0.25)) + Vector((*outward, 0)) * (0.35 + 1.6 * t ** 1.3) \
            + sway * math.sin(t * 5 + rng.uniform(0, 6)) - Vector((0, 0, length * t))
        pts.append(tuple(p))

    def wind(p):
        return min(1.0, 0.1 + (top_z - p[2]) / max(length, 1.0) * 0.9)
    if not leafy:
        parts.tube(pts, lambda t: 0.06 * (1 - 0.6 * t), ROOT_BROWN, 0, wind, sides=4)
        return
    tint = rng.uniform(0.75, 1.1)
    colour = (tint, tint * rng.uniform(0.95, 1.05), tint * rng.uniform(0.85, 1.0))
    width = rng.uniform(1.3, 2.2)
    tile = width * 3.4  # T_Vines is 1:4, so leaves keep (nearly) their shape
    parts.ribbon(pts, width, outward, colour, wind, tile=tile)
    if length > 6:
        a = math.radians(rng.choice((55, -55)))
        crossed = (outward[0] * math.cos(a) - outward[1] * math.sin(a), outward[0] * math.sin(a) + outward[1] * math.cos(a))
        parts.ribbon(pts, width * 0.8, crossed, colour, wind, tile=tile * 0.8)


def vine_texture():
    """T_Vines.png: a hanging ivy strip (stem and leaves, transparent around them), tiling top to bottom."""
    from PIL import Image, ImageDraw
    w, h = 256, 1024
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    rng = random.Random(11)

    def stem_x(y, k=0):
        # Two stems twining round each other (k = 0, 1), each a whole number of waves so the strip tiles.
        return w / 2 + (30 - 8 * k) * math.sin(2 * math.pi * y / h * (2 + k) + k * 2.1) + 8 * math.sin(2 * math.pi * y / h * 5)
    for k in (0, 1):
        for y in range(0, h, 2):
            x = stem_x(y, k)
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(70, 80, 40, 255))
    greens = [(52, 110, 38), (70, 130, 45), (40, 92, 34), (88, 145, 55), (60, 118, 42)]
    for _ in range(190):
        y = rng.uniform(0, h)
        side = rng.choice((-1, 1))
        length = rng.uniform(40, 78)
        angle = math.radians(rng.uniform(25, 70)) * side
        base = (stem_x(y, rng.randint(0, 1)), y)
        tip = (base[0] + math.sin(angle) * length, base[1] + math.cos(angle) * length * 0.6)
        colour = rng.choice(greens)
        for dy in (-h, 0, h):  # wrap so the strip tiles
            pts = []
            for k in range(14):
                t = k / 13
                bulge = math.sin(math.pi * t) * length * 0.32 * (1.15 if t < 0.5 else 0.9)
                cx = base[0] + (tip[0] - base[0]) * t
                cy = base[1] + (tip[1] - base[1]) * t + dy
                nx, ny = -(tip[1] - base[1]), tip[0] - base[0]
                n = math.hypot(nx, ny) or 1
                pts.append((cx + nx / n * bulge, cy + ny / n * bulge))
            for k in range(13, -1, -1):
                t = k / 13
                bulge = math.sin(math.pi * t) * length * 0.32
                cx = base[0] + (tip[0] - base[0]) * t
                cy = base[1] + (tip[1] - base[1]) * t + dy
                nx, ny = -(tip[1] - base[1]), tip[0] - base[0]
                n = math.hypot(nx, ny) or 1
                pts.append((cx - nx / n * bulge, cy - ny / n * bulge))
            draw.polygon(pts, fill=(*colour, 255))
            draw.line([(base[0], base[1] + dy), (tip[0], tip[1] + dy)], fill=tuple(int(c * 0.7) for c in colour) + (255,), width=2)
    B.TEXTURES.mkdir(parents=True, exist_ok=True)
    img.save(B.TEXTURES / 'T_Vines.png')


def add_vines(parts, poly, height_local, number, rng, skip=(), density=1.0):
    """Ivy and roots along the island rim (local polygon), written into `parts` in world coordinates."""
    ring = poly.exterior
    pts = np.array([ring.interpolate(s).coords[0] for s in np.arange(0, ring.length, 0.75)])
    ccw = ring.is_ccw
    for i, p in enumerate(pts):
        if rng.random() > density:
            continue
        if any(math.hypot(p[0] - sx, p[1] - sy) < sr for sx, sy, sr in skip):
            continue
        q = pts[(i + 1) % len(pts)] - pts[i - 1]
        outward = np.array([q[1], -q[0]]) / (np.linalg.norm(q) + 1e-9)
        if not ccw:
            outward = -outward
        z = float(height_local(np.array([p[0]]), np.array([p[1]]))[0])
        leafy = rng.random() < 0.85
        length = (rng.uniform(4, 11) if rng.random() < 0.45 else rng.uniform(11, 30)) if leafy else rng.uniform(3, 9)
        # Write straight into world space: turn the outward direction with the hole.
        wx, wy = C.to_world(number, p[0], p[1])
        yaw = math.radians(C.PLACE[number][1])
        ox = outward[0] * math.cos(yaw) - outward[1] * math.sin(yaw)
        oy = outward[0] * math.sin(yaw) + outward[1] * math.cos(yaw)
        hang(parts, (float(wx), float(wy)), (ox, oy), z + C.PLACE[number][2], length, rng, leafy)


def add_cliff_vines(parts, rock_v, rock_tris, dist, poly, number, rng, per_metre=0.7):
    """Ivy and roots scattered over the whole underside (not only the rim): strands start on the rock itself,
    anywhere from just under the lip to deep down the hanging cliffs, and hang free below it (the underside is
    a height field, so a strand dropping from its surface never runs back into rock)."""
    corners = rock_v[rock_tris]                               # (n, 3, 3) local metres
    centre = corners.mean(1)
    area = 0.5 * np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
    d = dist[rock_tris].mean(1)
    weight = area * np.clip((d - 0.6) / 1.5, 0, 1) * np.exp(-d / 14.0)   # thickest near the lip, thinning inward
    if weight.sum() <= 0:
        return
    count = int(poly.exterior.length * per_metre)
    picks = np.random.default_rng(rng.randint(0, 2 ** 31)).choice(len(centre), size=count, p=weight / weight.sum())
    yaw = math.radians(C.PLACE[number][1])
    for i in picks:
        a, b, c = corners[i]
        u, v = rng.random(), rng.random()
        if u + v > 1:
            u, v = 1 - u, 1 - v
        p = a + (b - a) * u + (c - a) * v
        edge = poly.exterior.interpolate(poly.exterior.project(Point(p[0], p[1])))
        out = np.array([edge.x - p[0], edge.y - p[1]])
        out = out / (np.linalg.norm(out) + 1e-9)
        ox = out[0] * math.cos(yaw) - out[1] * math.sin(yaw)
        oy = out[0] * math.sin(yaw) + out[1] * math.cos(yaw)
        wx, wy = C.to_world(number, p[0], p[1])
        leafy = rng.random() < 0.85
        length = (rng.uniform(3, 9) if rng.random() < 0.55 else rng.uniform(9, 22)) if leafy else rng.uniform(3, 8)
        hang(parts, (float(wx), float(wy)), (ox, oy), float(p[2]) + C.PLACE[number][2] + 0.3, length, rng, leafy)


# ---------------------------------------------------------------- bridges

WOOD = [(0.42, 0.30, 0.18), (0.36, 0.25, 0.15), (0.48, 0.34, 0.20)]
ROPE = (0.62, 0.52, 0.34)


def rope_bridge(deck_parts, parts, a, b, rng, width=2.4, sag_ratio=0.055, leafy=True, ground=None, guard=None):
    """Planks on a sagging deck between two anchor points (world x, y, z) into `deck_parts` (looks only: the
    buggy drives on a smooth slab in `guard`); rope rails, hangers, log posts and a gate tall enough for the buggy into `parts` (no
    collision). ground(x, y) -> island height or None: over land the deck never dips under the grass, so the
    buggy meets no lip at the cliff edge. `guard` gets low walls along both edges (hidden, they only collide)
    so the buggy can't drive off the side."""
    a, b = Vector(a), Vector(b)
    span = (b - a).length
    sag = 0.8 + span * sag_ratio
    along = (b - a).normalized()
    flat = Vector((along.x, along.y, 0)).normalized()
    across = Vector((-flat.y, flat.x, 0))

    # Deck height along the span: the sagging rope curve, lifted flush with the grass over land, then eased so it
    # never falls away faster than a gentle ramp (no lip where it leaves the cliff edge).
    ts = np.linspace(0.0, 1.0, 401)
    zs = np.array([(a.lerp(b, t)).z - sag * 4 * t * (1 - t) for t in ts])
    if ground:
        for i, t in enumerate(ts):
            p = a.lerp(b, t)
            g = ground(p.x, p.y)
            if g is not None:
                zs[i] = max(zs[i], g - 0.02)
    dz = 0.3 * span / 400
    for i in range(1, len(zs)):
        zs[i] = max(zs[i], zs[i - 1] - dz)
    for i in range(len(zs) - 2, -1, -1):
        zs[i] = max(zs[i], zs[i + 1] - dz)

    def deck(t):
        p = a.lerp(b, t)
        p.z = float(np.interp(t, ts, zs))
        return p

    count = int(span / 0.42)
    for i in range(count + 1):
        t = i / count
        p = deck(t)
        tangent = (deck(min(1, t + 0.01)) - deck(max(0, t - 0.01))).normalized()
        jitter = Vector((0, 0, rng.uniform(-0.02, 0.02)))
        deck_parts.box(p + jitter, tangent, across, (0.17, width / 2 * rng.uniform(0.9, 1.0), 0.04), rng.choice(WOOD))
    steps = max(8, int(span / 1.2))
    for side in (-1, 1):
        edge = [tuple(deck(i / steps) + across * side * width / 2) for i in range(steps + 1)]
        rail = [tuple(deck(i / steps) + across * side * width / 2 + Vector((0, 0, 1.1 - 0.25 * math.sin(math.pi * i / steps))))
                for i in range(steps + 1)]
        parts.tube(edge, 0.045, ROPE, sides=4)
        parts.tube(rail, 0.05, ROPE, sides=4)
        for i in range(0, steps + 1, 2):
            parts.tube([edge[i], rail[i]], 0.02, ROPE, sides=3)
            if leafy and rng.random() < 0.45:
                # A short strand of ivy trailing off the rope rail, outside the deck.
                top = Vector(rail[i]) + across * side * 0.05
                drop = rng.uniform(1.0, 3.2)
                strand = [tuple(top + across * side * 0.25 * (k / 4) ** 2 - Vector((0, 0, drop * k / 4))) for k in range(5)]
                w = rng.uniform(0.45, 0.7)
                parts.ribbon(strand, w, tuple(across * side), (0.9, 0.95, 0.85), 0.5, tile=w * 3.4)
        for end, sign in ((a, 1), (b, -1)):
            post = end + across * side * (width / 2 + 0.2) - flat * sign * 0.6
            parts.tube([tuple(post - Vector((0, 0, 0.8))), tuple(post + Vector((0, 0, 2.95)))], 0.16, rng.choice(WOOD), sides=6)
            parts.tube([tuple(post + Vector((0, 0, 1.4))), tuple(end + across * side * width / 2 + Vector((0, 0, 1.1)))], 0.035, ROPE, sides=4)
    for end, sign in ((a, 1), (b, -1)):   # crossbar over each end, jungle-gate style
        centre = end - flat * sign * 0.6 + Vector((0, 0, 2.8))  # the buggy's roof clears it
        parts.tube([tuple(centre - across * (width / 2 + 0.4)), tuple(centre + across * (width / 2 + 0.4))], 0.1, rng.choice(WOOD), sides=6)
    if guard is not None:
        # The smooth surface the buggy actually drives on (the planks are looks only): a thin slab just at
        # plank-top height, running 1.5 m past each anchor and dipping into the grass so there's no lip.
        path = [a - flat * 1.5 - Vector((0, 0, 0.2))] + [deck(i / (4 * steps)) + Vector((0, 0, 0.04))
                                                          for i in range(4 * steps + 1)] + [b + flat * 1.5 - Vector((0, 0, 0.2))]
        half = across * (width / 2)
        top_v = [q for p in path for q in (tuple(p - half), tuple(p + half))]
        bottom_v = [tuple(Vector(q) - Vector((0, 0, 0.08))) for q in top_v]
        quads = [(2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1) for i in range(len(path) - 1)]
        guard._add(top_v, quads, ROPE, 0, 0.0)
        guard._add(bottom_v, [q[::-1] for q in quads], ROPE, 0, 0.0)
        for side in (-1, 1):
            for i in range(steps):
                p0, p1 = deck(i / steps), deck((i + 1) / steps)
                d = p1 - p0
                mid = (p0 + p1) / 2 + across * side * (width / 2 + 0.08) + Vector((0, 0, 0.6))
                guard.box(mid, d, across, (d.length / 2 + 0.05, 0.06, 0.6), ROPE)
    return span, sag


FOOTBRIDGE_WIDTH = 3.0  # m: the Fab bridge (2 m wide) is stretched to this so the buggy fits


def footbridge(parts, number, height_local, centre, heading, length, rng):
    """A footbridge over a brook (local placement). The looks come from the Fab bridge mesh placed by
    Scripts/apply_floating_islands.py; this writes only the flat deck it drives on (hidden in game, it
    collides) and returns where the bridge goes: world x, y, deck z (m), yaw (deg), length (m)."""
    ang = math.radians(heading)
    d = np.array([math.cos(ang), math.sin(ang)])
    ends = [np.array(centre) - d * length / 2, np.array(centre) + d * length / 2]
    zs = [float(height_local(np.array([e[0]]), np.array([e[1]]))[0]) for e in ends]
    base = C.PLACE[number][2]
    deck_z = max(zs) + base + 0.08
    wa = C.to_world(number, *ends[0])
    wb = C.to_world(number, *ends[1])
    a = Vector((float(wa[0]), float(wa[1]), deck_z))
    b = Vector((float(wb[0]), float(wb[1]), deck_z))
    flat = (b - a).normalized()
    across = Vector((-flat.y, flat.x, 0))
    # Flat across the brook, easing down into each bank over 1.5 m so there's no lip to drive over.
    deck = [a - flat * 1.5 - Vector((0, 0, deck_z - zs[0] - base + 0.25))] + [a.lerp(b, i / 20) for i in range(21)] \
        + [b + flat * 1.5 - Vector((0, 0, deck_z - zs[1] - base + 0.25))]
    half = across * (FOOTBRIDGE_WIDTH / 2)
    top_v = [q for p in deck for q in (tuple(p - half), tuple(p + half))]
    bottom_v = [tuple(Vector(q) - Vector((0, 0, 0.1))) for q in top_v]
    quads = [(2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1) for i in range(len(deck) - 1)]
    parts._add(top_v, quads, WOOD[1], 0, 0.0)
    parts._add(bottom_v, [q[::-1] for q in quads], WOOD[1], 0, 0.0)
    mid = (a + b) / 2
    yaw = math.degrees(math.atan2(flat.y, flat.x))
    return [round(mid.x, 3), round(mid.y, 3), round(deck_z, 3), round(yaw, 2), round(length, 2)]


# ---------------------------------------------------------------- forest plan

def forest_plan(number, layout, height_local, rng):
    """Where trees and bushes go (world x, y, z, yaw, scale, kind): thick in the woods, sparse in the rough."""
    land = layout['land']
    keep_clear = unary_union([layout['fairways'].buffer(6), layout['green'].buffer(9), layout['tee'].buffer(16)]
                             + [b.buffer(3) for b in layout['bunkers']]
                             + ([layout['water'].buffer(2.5)] if layout.get('water') is not None else [])
                             + ([layout['paths'].buffer(2.5)] if layout.get('paths') is not None else [])
                             + ([stadium_zone(layout)] if layout.get('stadium') else []))
    mix = C.HOLES[number]['mix'] if number in C.HOLES else {'Oak_A': 3, 'Oak_B': 3, 'Poplar': 1, 'Birch': 2, 'Bush_Round': 2, 'Bush_Flowering': 1}
    kinds, weights = zip(*mix.items())
    woods = layout.get('woods')
    minx, miny, maxx, maxy = land.bounds
    placed = []
    plan = []
    for _ in range(9000):
        x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
        p = Point(x, y)
        if not land.buffer(-3).contains(p) or keep_clear.contains(p):
            continue
        in_wood = woods is not None and woods.contains(p)
        spacing = 6.5 if in_wood else 15.0
        if any((x - px) ** 2 + (y - py) ** 2 < spacing ** 2 for px, py in placed):
            continue
        if not in_wood and rng.random() < 0.55:
            continue
        kind = rng.choices(kinds, weights)[0]
        z = float(height_local(np.array([x]), np.array([y]))[0])
        wx, wy = C.to_world(number, x, y)
        plan.append([round(float(wx), 2), round(float(wy), 2), round(z + C.PLACE[number][2] - 0.1, 2),
                     round(rng.uniform(0, 360), 1), round(rng.uniform(0.8, 1.2), 2), kind])
        placed.append((x, y))
    return plan


# ---------------------------------------------------------------- build one hole

STADIUM_FRONT = 14.0   # m beyond the green's edge where the first row of seats starts
STADIUM_TIERS = 9


def stadium_zone(layout):
    """Ground the 18th-green stands, hospitality box and leaderboard take up (local), or None."""
    if not layout.get('stadium'):
        return None
    gr = math.sqrt(layout['green'].area / math.pi)
    outer = Point(*layout['cup']).buffer(gr + STADIUM_FRONT + STADIUM_TIERS * 1.1 + 4)
    return outer.difference(Point(*layout['cup']).buffer(gr + STADIUM_FRONT - 1.5))


def build_stadium(parts, number, layout, local_h, rng):
    """The finale: a horseshoe grandstand behind the 18th green packed with a colourful crowd, flags along the
    top, a glass-fronted hospitality box on one side and a big leaderboard on the other, and a timber sleeper
    wall holding the pond in front of the green. Material 0 is vertex-coloured, 1 glass / screens."""
    cx, cy = layout['cup']
    gr = math.sqrt(layout['green'].area / math.pi)
    base = C.PLACE[number][2]
    yaw = math.radians(C.PLACE[number][1])

    def world(x, y, z):
        wx, wy = C.to_world(number, x, y)
        return Vector((float(wx), float(wy), float(z) + base))

    def ground(x, y):
        return float(local_h(np.array([float(x)]), np.array([float(y)]))[0])

    def wdir(dx, dy):
        c, s_ = math.cos(yaw), math.sin(yaw)
        return Vector((dx * c - dy * s_, dx * s_ + dy * c, 0.0)).normalized()

    concrete, facade, blue = (0.72, 0.72, 0.7), (0.93, 0.94, 0.95), (0.05, 0.22, 0.62)
    shirts = [(0.85, 0.12, 0.1), (0.1, 0.3, 0.8), (0.95, 0.95, 0.95), (0.95, 0.75, 0.1), (0.1, 0.55, 0.25),
              (0.9, 0.45, 0.65), (0.2, 0.2, 0.22), (0.95, 0.5, 0.1), (0.4, 0.7, 0.95)]
    skins = [(0.93, 0.76, 0.62), (0.75, 0.55, 0.4), (0.45, 0.3, 0.2), (0.98, 0.85, 0.72)]
    r0 = gr + STADIUM_FRONT
    tread, rise = 1.1, 0.55
    a_from, a_to, step = -105.0, 105.0, 5.0      # degrees round the green, 0 = straight behind it
    angles = np.arange(a_from, a_to + 0.01, step)
    for a0, a1 in zip(angles[:-1], angles[1:]):
        am = math.radians((a0 + a1) / 2)
        seg = math.radians(step) * r0
        # The stands stand on the lowest ground under this slice; they are built up level from there.
        gx, gy = cx + math.cos(am) * (r0 + 5), cy + math.sin(am) * (r0 + 5)
        floor = min(ground(cx + math.cos(am) * r, cy + math.sin(am) * r) for r in (r0, r0 + 5, r0 + 10)) - 0.5
        top = max(ground(cx + math.cos(am) * r0, cy + math.sin(am) * r0), floor + 0.5)
        radial = wdir(math.cos(am), math.sin(am))
        tangent = wdir(-math.sin(am), math.cos(am))
        for k in range(STADIUM_TIERS):
            r = r0 + (k + 0.5) * tread
            seat_top = top + 0.4 + k * rise
            mid = world(cx + math.cos(am) * r, cy + math.sin(am) * r, (floor + seat_top) / 2)
            parts.box(tuple(mid), tangent, radial, (seg * r / r0 / 2 + 0.02, tread / 2, (seat_top - floor) / 2), concrete)
            # The crowd: a seated spectator every 0.6 m (body, head), all sorts of shirts.
            count = int(seg * r / r0 / 0.62)
            for i in range(count):
                if rng.random() < 0.08:
                    continue
                t = (i + 0.5) / count - 0.5
                px, py = cx + math.cos(am) * (r + 0.15), cy + math.sin(am) * (r + 0.15)
                pos = world(px, py, seat_top) + tangent * t * seg * r / r0
                shirt = rng.choice(shirts)
                parts.box(tuple(pos + Vector((0, 0, 0.35))), tangent, radial, (0.2, 0.14, 0.35), shirt)
                parts.box(tuple(pos + Vector((0, 0, 0.84))), tangent, radial, (0.1, 0.1, 0.12), rng.choice(skins))
        # Back wall: white, a blue band with the event's boards, flags on poles every other slice.
        rb = r0 + STADIUM_TIERS * tread + 0.3
        wall_top = top + 0.4 + STADIUM_TIERS * rise + 2.2
        mid = world(cx + math.cos(am) * rb, cy + math.sin(am) * rb, (floor + wall_top) / 2)
        parts.box(tuple(mid), tangent, radial, (seg * rb / r0 / 2 + 0.03, 0.3, (wall_top - floor) / 2), facade)
        band = world(cx + math.cos(am) * (rb - 0.32), cy + math.sin(am) * (rb - 0.32), wall_top - 0.9)
        parts.box(tuple(band), tangent, radial, (seg * rb / r0 / 2, 0.02, 0.6), blue)
        # Front wall of the stands facing the green: blue hoardings.
        front = world(cx + math.cos(am) * (r0 - 0.1), cy + math.sin(am) * (r0 - 0.1), top + 0.1)
        parts.box(tuple(front), tangent, radial, (seg / 2 + 0.02, 0.1, 0.55), blue)
        if int(round(a0 / step)) % 2 == 0:
            pole = world(cx + math.cos(am) * rb, cy + math.sin(am) * rb, wall_top)
            parts.tube([tuple(pole), tuple(pole + Vector((0, 0, 4.5)))], 0.06, (0.9, 0.9, 0.9))
            parts.box(tuple(pole + Vector((0, 0, 4.0)) + tangent * 0.7), tangent, Vector((0, 0, 1)).cross(tangent),
                      (0.7, 0.45, 0.02), rng.choice([(0.05, 0.22, 0.62), (0.95, 0.95, 0.95), (0.85, 0.12, 0.1)]))

    def building(angle, radius, size, frame, glass_band):
        am = math.radians(angle)
        x, y = cx + math.cos(am) * radius, cy + math.sin(am) * radius
        radial = wdir(math.cos(am), math.sin(am))
        tangent = wdir(-math.sin(am), math.cos(am))
        g = min(ground(x + dx, y + dy) for dx in (-4, 4) for dy in (-4, 4)) - 0.4
        half = (size[0] / 2, size[1] / 2, size[2] / 2)
        parts.box(tuple(world(x, y, g + half[2])), tangent, radial, half, frame)
        return x, y, g, am, radial, tangent

    # Hospitality box on the left: white, two storeys of dark glass looking at the green, a blue roof band.
    x, y, g, am, radial, tangent = building(a_from - 14, r0 + 6, (20, 8, 7.5), facade, True)
    for level in (1.9, 5.2):
        glass = world(x - math.cos(am) * 4.05, y - math.sin(am) * 4.05, g + level)
        parts.box(tuple(glass), tangent, radial, (9.2, 0.05, 1.3), (0.05, 0.08, 0.12), mat=1)
    parts.box(tuple(world(x, y, g + 7.6)), tangent, radial, (10.2, 4.2, 0.35), blue)
    # Leaderboard on the right: a tall white frame with a dark screen and rows of names and scores.
    x, y, g, am, radial, tangent = building(a_to + 14, r0 + 4, (11, 1.2, 9), facade, False)
    face = -radial
    screen = world(x - math.cos(am) * 0.62, y - math.sin(am) * 0.62, g + 5.2)
    parts.box(tuple(screen), tangent, radial, (4.8, 0.03, 3.2), (0.03, 0.05, 0.12), mat=1)
    parts.box(tuple(world(x, y, g + 9.3)), tangent, radial, (5.6, 0.7, 0.4), blue)
    # The live standings are drawn on the screen in game (ASkyLinksLeaderboard): where the screen is and which way
    # it faces (world metres, yaw in degrees).
    front = world(x - math.cos(am) * 0.7, y - math.sin(am) * 0.7, g + 5.2)
    layout['leaderboard'] = [round(front.x, 2), round(front.y, 2), round(front.z, 2), round(math.degrees(math.atan2(face.y, face.x)), 1)]

    # Timber sleeper wall where the pond meets the green bank: planks from below the water to the top of the bank.
    water = layout.get('water')
    if water is not None:
        ring = water.exterior if water.geom_type == 'Polygon' else max(water.geoms, key=lambda g_: g_.area).exterior
        level = WATER_LEVEL + layout.get('water_offset', 0.0)
        n = int(ring.length / 0.26)
        pts = [ring.interpolate(i / n, normalized=True) for i in range(n + 1)]
        for p, q in zip(pts[:-1], pts[1:]):
            mx, my = (p.x + q.x) / 2, (p.y + q.y) / 2
            if math.hypot(mx - cx, my - cy) > gr + 22:
                continue   # only the stretch facing the green
            top = ground(mx, my) + 0.25
            along = wdir(q.x - p.x, q.y - p.y)
            out = Vector((0, 0, 1)).cross(along)
            mid = world(mx, my, (level - 0.6 + top) / 2)
            shade = rng.uniform(0.8, 1.1)
            parts.box(tuple(mid), along, out, (0.14, 0.09, (top - level + 0.6) / 2), (0.36 * shade, 0.24 * shade, 0.14 * shade))


def surface_uvs(layout, xy):
    """Per-vertex data for the surface materials.
    UV1 'Hole': hole-local metres (x down the hole from the tee, y across) for mowing stripes.
    UV2 'Edges': x = metres to the nearest bunker edge (sand lips, turf walls, lip tufts),
                 y = metres to the nearest fairway / green / tee edge (green collars, first cut of rough)."""
    pts = shapely.points(xy[:, 0], xy[:, 1])
    bunkers = [b for b in layout['bunkers'] if not b.is_empty]
    bunker_d = shapely.distance(unary_union([b.boundary for b in bunkers]), pts) if bunkers else np.full(len(xy), 10.0)
    rings = []
    for shape in (layout['fairways'], layout['green'], layout['tee']):
        for poly in getattr(shape, 'geoms', [shape]):
            if not poly.is_empty:
                rings.append(poly.exterior)
    edge_d = shapely.distance(unary_union(rings), pts)
    # UV3 'Path': signed metres to the buggy path's edge (negative on it). The path outline is in the mesh, so the
    # zero line of this runs exactly along it: the material draws a clean edge there whatever the triangles do.
    paths = layout.get('paths')
    if paths is not None and not paths.is_empty:
        sd = shapely.distance(paths.boundary, pts) * np.where(shapely.contains_xy(paths, xy[:, 0], xy[:, 1]), -1.0, 1.0)
    else:
        sd = np.full(len(xy), 10.0)
    return [('Hole', xy), ('Edges', np.column_stack([np.minimum(bunker_d, 10.0), np.minimum(edge_d, 10.0)])),
            ('Path', np.column_stack([np.clip(sd, -10.0, 10.0), np.zeros(len(xy))]))]


def build_hole(number, rng):
    layout = layout_for(number)
    local_h = height_fn(number, layout)
    sl.reset_scene()
    B.build_materials()
    name = f'SM_H{number:02d}'

    cart, paths = hole_paths(number, layout)
    layout = dict(layout, paths=paths, cart=cart)
    if paths is not None and not SOFT_PATHS:
        # Path border plus a second outline 0.3 m out: the dirt fades to grass across that thin, even band.
        layout = dict(layout, extra_lines=[paths, paths.buffer(0.3, 8)])
    local_h = path_bed(local_h, cart)
    xy, tris, attrs = B.triangulate_top(layout)
    z = local_h(xy[:, 0], xy[:, 1])
    top_cols = B.top_colours(xy[:, 0], xy[:, 1], number)
    if paths is not None:
        on_path = shapely.contains_xy(paths.buffer(0.02), xy[:, 0], xy[:, 1])
        top_cols[:, 2] = on_path.astype(float)  # B: 1 on the path (its border vertices included)
    top = B.make_mesh(f'{name}_IslandTop', place(number, np.column_stack([xy, z])), tris, attrs,
                      [B.REGION_MATERIAL[i] for i in range(5)], top_cols, extra_uvs=surface_uvs(layout, xy))

    land = layout['land']
    uxy, utris = B.triangulate_underside(land, [0.8, 2.0, 4.0, 7.5, 13, 21, 32], 14)
    if number == 1:
        pts = shapely.points(uxy[:, 0], uxy[:, 1])
        depth = np.where(shapely.distance(layout['main'], pts) < 1e-6, B.DESIGNS[1]['depth'][0], B.DESIGNS[1]['depth'][1])
    else:
        depth = np.full(len(uxy), 40.0 + 0.1 * math.sqrt(land.area))
    rock_v, dist, t = B.underside(uxy, land, local_h, depth, number * 13)
    colours = moss(B.rock_colours(rock_v[:, 2], dist, t, uxy[:, 0], uxy[:, 1], number), rock_v[:, 2], dist,
                   uxy[:, 0], uxy[:, 1], number)
    rock = B.make_mesh(f'{name}_IslandRock', place(number, rock_v), utris[:, ::-1], np.zeros(len(utris), int),
                       ['IslandRock'], colours)

    # Floaters: hole 1 keeps its hand-placed ones; the others get a ring of small islands. They hang high above
    # the hole (background decoration, clear of play) and each is its own mesh with its pivot at its middle,
    # so they can be moved one by one in the editor.
    floaters = layout['floaters'] if number == 1 else ring_of_floaters(number, land, rng)
    for stale in OUT.glob(f'{name}_Floater*.fbx'):
        stale.unlink()
    floater_spots = []
    vines = Parts()
    skip = [(0, 0, 18)]  # keep the tee edge clear
    for i, (poly, _) in enumerate(floaters):
        top_z = rng.uniform(50, 120)
        fn = lambda x, y, tz=top_z, s=i, pl=poly: tz + 0.8 * B.fbm(x / 12, y / 12, 3, 500 + s) - 0.6 * (1 - B.smooth(  # noqa: E731
            shapely.distance(pl.exterior, shapely.points(x, y)) / 3))
        cx, cy = poly.centroid.x, poly.centroid.y
        wcx, wcy = (float(v) for v in C.to_world(number, cx, cy))
        pivot = np.array([wcx, wcy, top_z + C.PLACE[number][2]])
        vx, tx = B.triangulate_underside(poly, [], 1.5)
        ux, ut = B.triangulate_underside(poly, [0.8, 2.0, 4.0, 7.0], 6)
        radius = math.sqrt(poly.area / math.pi)
        rv, rd, rt = B.underside(ux, poly, fn, radius * 1.7, 700 + i + number * 50)
        verts = np.concatenate([place(number, np.column_stack([vx, fn(vx[:, 0], vx[:, 1])])), place(number, rv)]) - pivot
        f_tris = np.concatenate([tx, ut[:, ::-1] + len(vx)])
        f_mats = np.concatenate([np.zeros(len(tx), int), np.ones(len(ut), int)])
        cols = np.concatenate([B.top_colours(vx[:, 0], vx[:, 1], number),
                               moss(B.rock_colours(rv[:, 2], rd, rt, ux[:, 0], ux[:, 1], 700 + i), rv[:, 2], rd, ux[:, 0], ux[:, 1], i)])
        floater_name = f'{name}_Floater{i + 1:02d}'
        far = np.full((len(verts), 2), 10.0)  # no bunkers or fairways on a floater: plain rough
        rock_obj = B.make_mesh(floater_name, verts, f_tris, f_mats, ['Rough', 'IslandRock'], cols,
                               extra_uvs=[('Hole', np.zeros((len(verts), 2))), ('Edges', far), ('Path', far)])
        ivy = Parts()
        add_vines(ivy, poly, fn, number, rng, density=0.8)
        add_cliff_vines(ivy, rv, ut, rd, poly, number, rng, per_metre=0.5)
        ivy.v = [tuple(np.asarray(v, float) - pivot) for v in ivy.v]
        ivy_obj = ivy.mesh(f'{floater_name}_Ivy', ('TreeBark', 'TreeLeaves', 'Vines')) if ivy.f else None
        sl.export_fbx(str(OUT / f'{floater_name}.fbx'), [rock_obj, ivy_obj] if ivy.f else [rock_obj])
        floater_spots.append([floater_name, *[round(float(v), 2) for v in pivot]])

    add_vines(vines, land, local_h, number, rng, skip=skip)
    add_cliff_vines(vines, rock_v, utris, dist, land, number, rng)
    vine_obj = vines.mesh(f'{name}_Vines', ('TreeBark', 'TreeLeaves', 'Vines'))
    exported = [top, rock, vine_obj]

    if layout.get('water') is not None:
        wxy, wtris = B.triangulate_underside(layout['water'], [], 6)
        wv = place(number, np.column_stack([wxy, np.full(len(wxy), WATER_LEVEL + layout.get('water_offset', 0.0))]))
        exported.append(B.make_mesh(f'{name}_Water', wv, wtris, np.zeros(len(wtris), int), ['Water'],
                                    np.tile([0.5, 0.0, 0.0], (len(wv), 1))))
    footbridge_spots = []
    if layout.get('footbridges'):
        props = Parts()
        for centre, heading, length in layout['footbridges']:
            footbridge_spots.append(footbridge(props, number, local_h, centre, heading, length, rng))
        exported.append(props.mesh(f'{name}_Props'))
    if layout.get('stadium'):
        stands = Parts()
        build_stadium(stands, number, layout, local_h, random.Random(number * 31))
        exported.append(stands.mesh(f'{name}_Stadium', mats=('IslandRock', 'Water')))

    for obj in exported:
        sl.export_fbx(str(OUT / f'{obj.name}.fbx'), [obj])

    def ground(x, y):
        return round(float(local_h(np.array([x], float), np.array([y], float))[0]) + C.PLACE[number][2], 3)

    def world(x, y):
        wx, wy = C.to_world(number, x, y)
        return [round(float(wx), 3), round(float(wy), 3), ground(x, y)]
    paths_zone = layout['paths'].buffer(4) if layout.get('paths') is not None else None
    clear_trees = [(x, y) for x, y in layout['trees'] if paths_zone is None or not paths_zone.contains(Point(x, y))]
    cx, cy = layout['cup']
    info = C.HOLES.get(number, dict(name='Harbor Point', par=4, aim=(240, 0)))
    spots = {'hole': number, 'name': info['name'], 'par': info['par'],
             'tee': world(0, 0), 'yaw': C.PLACE[number][1], 'aim_local': list(info['aim']),
             'cup': world(cx, cy), 'tee_markers': [world(1.5, s * 2.5) for s in (-1, 1)],
             'player_start': world(-5.0, 0.0),
             'gameplay_trees': [world(x, y) for x, y in clear_trees],
             'land_outline': [[round(float(v), 2) for v in C.to_world(number, x, y)] for x, y in
                              layout['land'].buffer(3).simplify(1.0).exterior.coords],
             'cart_path': [world(x, y) for x, y in (layout['cart'].coords if layout.get('cart') is not None else [])],
             'forest': forest_plan(number, layout, local_h, rng), 'floaters': floater_spots, 'footbridges': footbridge_spots, 'leaderboard': layout.get('leaderboard')}
    if number == 1:
        spots['trees'] = [[x, y, ground(x, y)] for x, y in clear_trees]
        spots['clubhouse'] = [*B.DESIGNS[1]['clubhouse'], ground(*B.DESIGNS[1]['clubhouse'])]
    (OUT / f'Hole{number:02d}_spots.json').write_text(json.dumps(spots, indent=1) + '\n')
    print(f'HOLE {number} {spots["name"]}: top {len(tris)}, rock {len(utris)}, vines {len(vines.f)} faces, '
          f'{len(floaters)} floaters, {len(spots["forest"])} trees, water {layout.get("water") is not None}')
    return layout, local_h


def ring_of_floaters(number, land, rng):
    """Seven small islands scattered round a hole (local), clear of the island itself."""
    out = []
    for i in range(40):
        if len(out) >= 7:
            break
        edge = land.exterior.interpolate(rng.uniform(0, land.exterior.length))
        c = land.centroid
        away = np.array([edge.x - c.x, edge.y - c.y])
        away /= np.linalg.norm(away) + 1e-9
        centre = np.array([edge.x, edge.y]) + away * rng.uniform(28, 70) + np.array([rng.uniform(-15, 15), rng.uniform(-15, 15)])
        radius = rng.uniform(6, 15)
        blob = B.wobble(Point(*centre).buffer(radius, 48), radius * 0.35, radius * 1.4, 900 + number * 20 + i)
        if blob.distance(land) < 12 or any(blob.distance(o) < 8 for o, _ in out):
            continue
        out.append((blob, rng.uniform(-30, 10)))
    return out


# ---------------------------------------------------------------- course: bridges and fog

def world_land(number, layout):
    return C.world_geom(number, layout['land'])


def bridge_anchor_points(layouts):
    """Where each rope bridge lands (world metres): {n: (ax, ay, bx, by)} for the bridge from hole n's green end
    to hole n+1's tee island, 4 m in from each cliff edge so the posts stand on grass."""
    out = {}
    for n in range(1, max(C.PLACE)):
        if n not in layouts or n + 1 not in layouts:
            continue
        la, lb = layouts[n][0], layouts[n + 1][0]
        wa, wb = world_land(n, la), world_land(n + 1, lb)
        cup = Point(*C.to_world(n, *la['cup']))
        tee = Point(*C.to_world(n + 1, 0, 0))
        near_a = wa.intersection(cup.buffer(110))
        near_b = wb.intersection(tee.buffer(90))
        pa, pb = nearest_points(near_a.boundary, near_b.boundary)
        va = np.array([pb.x - pa.x, pb.y - pa.y])
        va /= np.linalg.norm(va)
        out[n] = (pa.x - va[0] * 4, pa.y - va[1] * 4, pb.x + va[0] * 4, pb.y + va[1] * 4)
    return out


def build_bridges(layouts, rng):
    """Rope bridge from each hole's green end to the next hole's tee island."""
    bridges = []
    anchors = bridge_anchor_points(layouts)
    for n in range(1, max(C.PLACE)):
        if n not in anchors:
            continue
        la, ha = layouts[n]
        lb, hb = layouts[n + 1]
        wa, wb = world_land(n, la), world_land(n + 1, lb)
        ax, ay, bx, by = anchors[n]
        za = float(ha(*[np.array([v]) for v in C.to_local(n, ax, ay)])[0]) + C.PLACE[n][2]
        zb = float(hb(*[np.array([v]) for v in C.to_local(n + 1, bx, by)])[0]) + C.PLACE[n + 1][2]
        def ground(x, y, n=n, ha=ha, hb=hb, wa=wa, wb=wb):
            for num, land, h in ((n, wa, ha), (n + 1, wb, hb)):
                if land.contains(Point(x, y)):
                    lx, ly = C.to_local(num, x, y)
                    return float(h(np.array([lx]), np.array([ly]))[0]) + C.PLACE[num][2]
            return None
        deck, rails, guard = Parts(), Parts(), Parts()
        span, sag = rope_bridge(deck, rails, (ax, ay, za - 0.02), (bx, by, zb - 0.02), rng, ground=ground, guard=guard)
        base = f'SM_Bridge_{n:02d}_{n + 1:02d}'
        obj, rails_obj, guard_obj = deck.mesh(base), rails.mesh(f'{base}_Rails', ('TreeBark', 'TreeLeaves', 'Vines')), guard.mesh(f'{base}_Guard')
        for o in (obj, rails_obj, guard_obj):
            sl.export_fbx(str(OUT / f'{o.name}.fbx'), [o])
        bridges.append(dict(name=obj.name, rails=rails_obj.name, guard=guard_obj.name, a=[ax, ay, za], b=[bx, by, zb],
                            span=round(span, 1), sag=round(sag, 1)))
        print(f'BRIDGE {n}->{n + 1}: {span:.0f} m, drop {za - zb:+.1f} m, sag {sag:.1f} m')
    return bridges


def fog_plan(layouts, bridges, rng):
    """Cloud-like fog patches: under every bridge and drifting in the gaps round each island."""
    fog = []
    for b in bridges:
        mid = (np.array(b['a']) + np.array(b['b'])) / 2
        fog.append([round(float(mid[0]), 1), round(float(mid[1]), 1), round(float(mid[2]) - rng.uniform(14, 26), 1),
                    round(rng.uniform(45, 70), 1)])
    for n, (layout, _) in layouts.items():
        land = world_land(n, layout)
        for _ in range(4):
            edge = land.exterior.interpolate(rng.uniform(0, land.exterior.length))
            away = np.array([edge.x - land.centroid.x, edge.y - land.centroid.y])
            away /= np.linalg.norm(away)
            p = np.array([edge.x, edge.y]) + away * rng.uniform(40, 90)
            fog.append([round(float(p[0]), 1), round(float(p[1]), 1),
                        round(C.PLACE[n][2] - rng.uniform(20, 45), 1), round(rng.uniform(55, 95), 1)])
    return fog


def check_course(layouts):
    """No two islands closer than 25 m (floaters aside)."""
    worlds = {n: world_land(n, l) for n, (l, _) in layouts.items()}
    for n, w in worlds.items():
        print(f'BOUNDS hole {n}: x {w.bounds[0]:.0f}..{w.bounds[2]:.0f}, y {w.bounds[1]:.0f}..{w.bounds[3]:.0f}, z {C.PLACE[n][2]:+.0f}')
    ok = True
    for a in worlds:
        for b in worlds:
            if a < b:
                gap = worlds[a].distance(worlds[b])
                if gap < 25:
                    ok = False
                print(f'GAP hole {a} - hole {b}: {gap:.0f} m' + ('  <-- too close' if gap < 25 else ''))
    return ok


def render_course(layouts):
    """An aerial overview of all built islands, bridges included (imports the FBXs just written)."""
    sl.reset_scene()
    for fbx in sorted(OUT.glob('SM_*.fbx')):
        if fbx.stem.startswith(('SM_H', 'SM_Bridge')):
            bpy.ops.import_scene.fbx(filepath=str(fbx))
    ivy = vc_material('Vines')
    for obj in bpy.data.objects:
        for slot in obj.material_slots:
            if slot.material and slot.material.name.startswith('Vines') and slot.material != ivy:
                slot.material = ivy
    for mat in bpy.data.materials:
        if mat.use_nodes and 'Principled BSDF' in mat.node_tree.nodes and not any(n.type == 'VERTEX_COLOR' for n in mat.node_tree.nodes):
            attr = mat.node_tree.nodes.new('ShaderNodeVertexColor')
            attr.layer_name = 'Col'
            colours = {'Rough': (0.05, 0.13, 0.02), 'Fairway': (0.08, 0.22, 0.03), 'Green': (0.09, 0.27, 0.04),
                       'TeeBox': (0.08, 0.22, 0.03), 'Bunker': (0.29, 0.21, 0.12), 'Water': (0.02, 0.07, 0.1)}
            key = next((k for k in colours if mat.name.startswith(k)), None)
            if key:
                mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (*colours[key], 1)
            else:
                mat.node_tree.links.new(attr.outputs['Color'], mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    scene = bpy.context.scene
    world = bpy.data.worlds.new('Sky')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.45, 0.62, 0.9, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.8
    scene.world = world
    sun_data = bpy.data.lights.new('Sun', 'SUN')
    sun_data.energy = 3.5
    sun = bpy.data.objects.new('Sun', sun_data)
    sun.rotation_euler = (math.radians(40), 0, math.radians(-150))
    scene.collection.objects.link(sun)
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 1600, 1000
    scene.view_settings.view_transform = 'AgX'
    for label, eye, target, lens in (('course', (-1500, 900, 1300), (0, 900, -20), 24),
                                     ('closeup', (150, 330, 60), (360, 300, 5), 28)):
        cam_data = bpy.data.cameras.new(label)
        cam_data.lens = lens
        cam_data.clip_end = 10000
        cam = bpy.data.objects.new(label, cam_data)
        cam.location = Vector((eye[0], -eye[1], eye[2]))
        cam.rotation_euler = (Vector((target[0], -target[1], target[2])) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        scene.collection.objects.link(cam)
        scene.camera = cam
        scene.render.filepath = str(OUT / f'Course_preview_{label}.png')
        bpy.ops.render.render(write_still=True)


def settle_heights(grade=0.1):
    """The landforms move each green well above or below its tee, so re-seat every island's height along the chain
    (hole 1 stays put): each rope bridge from a green to the next tee climbs or falls at most `grade`."""
    layouts = {n: layout_for(n) for n in C.PLACE}
    anchors = bridge_anchor_points({n: (lay, None) for n, lay in layouts.items()})
    heights = {n: height_fn(n, lay) for n, lay in layouts.items()}

    def ground(n, wx, wy):
        lx, ly = C.to_local(n, wx, wy)
        return float(heights[n](np.array([float(lx)]), np.array([float(ly)]))[0])
    for n in sorted(C.PLACE)[:-1]:
        if n not in anchors:
            continue
        ax, ay, bx, by = anchors[n]
        za = C.PLACE[n][2] + ground(n, ax, ay)
        zb_local = ground(n + 1, bx, by)
        gap = math.hypot(bx - ax, by - ay)
        target = za + float(np.clip(C.PLACE[n + 1][2] + zb_local - za, -grade * gap, grade * gap))
        xy, yaw, _ = C.PLACE[n + 1]
        C.PLACE[n + 1] = (xy, yaw, round(target - zb_local, 2))
    print('HEIGHTS', {n: C.PLACE[n][2] for n in sorted(C.PLACE)})


def main():
    settle_heights()
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    wanted = [int(a) for a in args if a.isdigit()] or sorted(C.PLACE)
    OUT.mkdir(parents=True, exist_ok=True)
    vine_texture()
    layouts = {}
    for number in sorted(set(wanted) | {n for w in wanted for n in (w - 1, w + 1) if n in C.PLACE}):
        layouts[number] = (layout_for(number), None)
    for number in layouts:
        layouts[number] = (layouts[number][0], height_fn(number, layouts[number][0]))
    if '--check' in args:
        check_course(layouts)
        return
    global SOFT_PATHS
    SOFT_PATHS = '--soft-paths' in args
    # Buggy paths start at the bridge you arrive on (the car park on hole 1) and end at the one you leave on.
    for n, (ax, ay, bx, by) in bridge_anchor_points(layouts).items():
        ANCHORS.setdefault(n, {})['out'] = tuple(float(v) for v in C.to_local(n, ax, ay))
        ANCHORS.setdefault(n + 1, {})['in'] = tuple(float(v) for v in C.to_local(n + 1, bx, by))
    ANCHORS.setdefault(1, {})['in'] = CAR_PARK_EXIT
    # --links-only: skip the islands (already built) and redo the bridges, fog and previews for the whole course.
    if '--links-only' in args:
        layouts = {n: (layout_for(n), None) for n in C.PLACE}
        layouts = {n: (lay, height_fn(n, lay)) for n, (lay, _) in layouts.items()}
        wanted = sorted(C.PLACE)
    # --props-only: rebuild just the footbridges (SM_Hnn_Props) of the wanted holes.
    if '--props-only' in args:
        for number in wanted:
            sl.reset_scene()
            layout = layout_for(number)
            if layout.get('footbridges'):
                local_h = height_fn(number, layout)
                props = Parts()
                rng = random.Random(number * 1009)
                placed = [footbridge(props, number, local_h, centre, heading, length, rng)
                          for centre, heading, length in layout['footbridges']]
                obj = props.mesh(f'SM_H{number:02d}_Props')
                sl.export_fbx(str(OUT / f'{obj.name}.fbx'), [obj])
                spots_path = OUT / f'Hole{number:02d}_spots.json'
                spots = json.loads(spots_path.read_text())
                spots['footbridges'] = placed
                spots_path.write_text(json.dumps(spots, indent=1) + '\n')
                print(f'PROPS {number}: {len(layout["footbridges"])} footbridges')
        return
    for number in (wanted if '--links-only' not in args else []):
        layout, local_h = build_hole(number, random.Random(number * 1009))
        layouts[number] = (layout, local_h)
    check_course(layouts)
    rng = random.Random(77)
    bridges = build_bridges(layouts, rng)
    fog = fog_plan({n: layouts[n] for n in wanted}, bridges, rng)
    (OUT / 'Course_links.json').write_text(json.dumps({'bridges': bridges, 'fog': fog}, indent=1) + '\n')
    if '--no-render' not in args:
        render_course(layouts)


if __name__ == '__main__':
    main()
