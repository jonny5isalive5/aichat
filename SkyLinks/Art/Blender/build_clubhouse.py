"""
Sky Links clubhouse, after the owner's reference photos: a two-storey red-brick clubhouse under an
orange clay-tile hip roof with deep eaves and a dark fascia. Along the left two thirds a first-floor
balcony with white railings sits on brick piers and arches (a loggia underneath); a straight staircase
comes down from the balcony toward the practice green. The right wing has big upstairs windows, a white
door, benches and the club sign. In front: a practice putting green with flags and a white stake-and-rope
fence, flagpoles, planters and shrubs. Behind: a small car park with painted bays and parked cars.

Run headless (bpy module or Blender 4.2+):
    python Art/Blender/build_clubhouse.py            (or blender --background --python ... -- <out>)

Writes to SkyLinks/Art/Exports:
    SM_Clubhouse.fbx + ClubhouseTextures/*.png   building and grounds, UCX_ collision for the building
    Clubhouse.blend, Clubhouse_preview_front.png, Clubhouse_preview_aerial.png
The entrance side faces -Y. Origin is on the ground at the centre of the main block. The grounds span
about x -19..19, y -31..26 m, so the island pad under it (build_floating_islands.py) is 36 m in radius.
Clears the current scene.
"""

import math
import os
import random
import sys

import bpy
import numpy as np


def _script_dir():
    path = globals().get("__file__", "")
    if path and os.path.isfile(path):
        return os.path.dirname(os.path.abspath(path))
    return os.getcwd()


sys.path.insert(0, _script_dir())
import sl_common as sl  # noqa: E402

UV_TILE = 2.0  # metres covered by one repeat of every texture below

# Main block (metres). Left section carries the balcony; the right wing is flush.
X0, X1, Y0, Y1 = -15.0, 15.0, -5.0, 6.0
SPLIT = 3.0            # balcony / loggia runs from X0 to here
FRONT = -7.5           # balcony edge and pier line
FLOOR1 = 3.3           # first floor level (balcony top)
EAVE = 6.4
RIDGE = 9.4
STAIR_X = -4.6         # centre of the staircase
STAIR_W = 2.4


# ---------------------------------------------------------------- textures

def _save(name, rgb, out):
    from PIL import Image
    folder = os.path.join(out, "ClubhouseTextures")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{name}.png")
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).save(path)
    return path


def make_textures(out, size=1024):
    """Tiling textures, each covering UV_TILE metres: brick, roof tiles, paving, asphalt."""
    rng = np.random.default_rng(7)
    px = size / UV_TILE
    v, u = np.mgrid[0:size, 0:size].astype(float)
    grain = rng.normal(0, 1, (size, size))

    # Stretcher bond: 9 bricks across, 27 courses up (22.2 x 7.4 cm incl. 1 cm mortar).
    course = np.floor(v / (size / 27)).astype(int)
    shift = (course % 2) * 0.5
    col = np.floor(u / (size / 9) + shift).astype(int) % 9
    brick_id = course * 9 + col
    tint = rng.normal(0, 1, (27 * 9 + 9, 3))
    base = np.array([168, 82, 58]) + tint[brick_id] * np.array([16, 9, 7])
    mortar_u = ((u / (size / 9) + shift) % 1.0) * (size / 9) < px * 0.01
    mortar_v = (v % (size / 27)) < px * 0.01
    brick = base + grain[..., None] * 6
    brick[mortar_u | mortar_v] = np.array([196, 188, 172]) + grain[mortar_u | mortar_v, None] * 5
    paths = {"T_CH_Brick": _save("T_CH_Brick", brick, out)}

    # Clay roof tiles: 8 courses, 12 tiles across, dark shadow under each course.
    course = np.floor(v / (size / 8)).astype(int)
    col = np.floor(u / (size / 12) + (course % 2) * 0.5).astype(int) % 12
    tint = rng.normal(0, 1, (8 * 12 + 12, 3))
    tile = np.array([164, 78, 46]) + tint[course * 12 + col] * np.array([12, 7, 5]) + grain[..., None] * 5
    frac = (v % (size / 8)) / (size / 8)
    tile *= (0.62 + 0.38 * np.clip(frac / 0.18, 0, 1))[..., None]
    edge = ((u / (size / 12) + (course % 2) * 0.5) % 1.0) < 0.03
    tile[edge] *= 0.8
    paths["T_CH_RoofTile"] = _save("T_CH_RoofTile", tile, out)

    # Paving slabs 50 cm.
    slab = np.floor(u / (size / 4)).astype(int) * 4 + np.floor(v / (size / 4)).astype(int)
    pave = np.array([150, 146, 138]) + rng.normal(0, 6, 16)[slab, None] + grain[..., None] * 7
    joint = ((u % (size / 4)) < 3) | ((v % (size / 4)) < 3)
    pave[joint] = [105, 102, 96]
    paths["T_CH_Paving"] = _save("T_CH_Paving", pave, out)

    asphalt = np.array([58, 58, 60]) + grain[..., None] * 9 + rng.normal(0, 1, (size, size))[..., None] * 4
    paths["T_CH_Asphalt"] = _save("T_CH_Asphalt", asphalt, out)
    return paths


def textured(name, image_path, roughness=0.85):
    mat = sl.material(name, (0.5, 0.5, 0.5), roughness)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image_path)
    links.new(tex.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
    return mat


def materials(tex):
    return dict(
        brick=textured("M_CH_Brick", tex["T_CH_Brick"], 0.9),
        roof=textured("M_CH_RoofTile", tex["T_CH_RoofTile"], 0.75),
        paving=textured("M_CH_Paving", tex["T_CH_Paving"], 0.9),
        asphalt=textured("M_CH_Asphalt", tex["T_CH_Asphalt"], 0.95),
        fascia=sl.material("M_CH_Fascia", (0.12, 0.06, 0.035), 0.6),
        white=sl.material("M_CH_WhitePaint", (0.85, 0.85, 0.83), 0.45),
        glass=sl.material("M_CH_Glass", (0.04, 0.06, 0.08), 0.05, metallic=0.5),
        concrete=sl.material("M_CH_Concrete", (0.45, 0.43, 0.4), 0.9),
        putting=sl.material("M_CH_PuttingGreen", (0.06, 0.22, 0.04), 0.7),
        fringe=sl.material("M_CH_Fringe", (0.05, 0.16, 0.03), 0.85),
        cup=sl.material("M_CH_Cup", (0.01, 0.01, 0.01), 0.9),
        flag=sl.material("M_CH_FlagRed", (0.7, 0.03, 0.03), 0.6),
        clubflag=sl.material("M_CH_FlagGreen", (0.02, 0.3, 0.08), 0.6),
        hedge=sl.material("M_CH_Hedge", (0.02, 0.09, 0.02), 0.95),
        soil=sl.material("M_CH_Soil", (0.08, 0.05, 0.03), 1.0),
        wood=sl.material("M_CH_Wood", (0.3, 0.18, 0.09), 0.8),
        sign=sl.material("M_CH_SignBoard", (0.02, 0.12, 0.06), 0.5),
        gold=sl.material("M_CH_SignText", (0.8, 0.62, 0.25), 0.3, metallic=1.0),
        rope=sl.material("M_CH_Rope", (0.8, 0.8, 0.78), 0.8),
        tyre=sl.material("M_CH_Tyre", (0.02, 0.02, 0.02), 0.8),
        lines=sl.material("M_CH_LinePaint", (0.9, 0.9, 0.88), 0.6),
    )


# ---------------------------------------------------------------- parts

def window(parts, m, x, z0, z1, width, face_y, facing=-1, bars=1):
    """White-framed window (or glazed door) on a wall plane at y = face_y; facing -1 is the -Y side."""
    t, d = 0.08, 0.06
    y_out = face_y + facing * d
    lo, hi = sorted((face_y - facing * 0.02, y_out))
    parts.append(sl.box("glass", x - width / 2, x + width / 2, face_y - 0.02, face_y + 0.02, z0, z1, m["glass"]))
    for a, b, c, e in ((x - width / 2 - t, x - width / 2, z0, z1), (x + width / 2, x + width / 2 + t, z0, z1),
                       (x - width / 2 - t, x + width / 2 + t, z1, z1 + t), (x - width / 2 - t, x + width / 2 + t, z0 - t, z0)):
        parts.append(sl.box("frame", a, b, lo, hi, c, e, m["white"]))
    for i in range(1, bars + 1):
        bx = x - width / 2 + width * i / (bars + 1)
        parts.append(sl.box("mullion", bx - 0.03, bx + 0.03, lo, hi, z0, z1, m["white"]))


def side_window(parts, m, y, z0, z1, width, face_x, facing):
    """Window on an end wall (plane x = face_x), facing -1 (-X) or +1 (+X)."""
    t = 0.08
    lo, hi = sorted((face_x - facing * 0.02, face_x + facing * 0.06))
    parts.append(sl.box("glass", face_x - 0.02, face_x + 0.02, y - width / 2, y + width / 2, z0, z1, m["glass"]))
    for a, b, c, e in ((y - width / 2 - t, y - width / 2, z0, z1), (y + width / 2, y + width / 2 + t, z0, z1),
                       (y - width / 2 - t, y + width / 2 + t, z1, z1 + t), (y - width / 2 - t, y + width / 2 + t, z0 - t, z0)):
        parts.append(sl.box("frame", lo, hi, a, b, c, e, m["white"]))


def arch_spandrel(x0, x1, y0, y1, spring, top, rise, mat):
    """Brick between two piers with a segmental arch cut out underneath."""
    pts = [(x0, top), (x1, top), (x1, spring)]
    for i in range(1, 16):
        t = i / 16
        pts.append((x1 - (x1 - x0) * t, spring + rise * math.sin(math.pi * t)))
    pts.append((x0, spring))
    return sl.prism("spandrel", pts, y0, y1, mat)


def railing(parts, m, a, b, height=1.0, spacing=1.2, post=0.06):
    """White post-and-rail railing along the ground-plane segment a -> b (z from a[2])."""
    ax, ay, az = a
    bx, by, bz = b
    length = math.hypot(bx - ax, by - ay)
    count = max(1, round(length / spacing))
    for i in range(count + 1):
        t = i / count
        x, y, z = ax + (bx - ax) * t, ay + (by - ay) * t, az + (bz - az) * t
        parts.append(sl.box("post", x - post, x + post, y - post, y + post, z, z + height, m["white"]))
    for h in (height, height * 0.5):
        parts.append(sl.cylinder("rail", (ax, ay, az + h), (bx, by, bz + h), 0.035, m["white"], segments=8))


def shrub(parts, m, x, y, r, rng):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=r, location=(x, y, r * 0.75))
    obj = bpy.context.object
    obj.scale = (rng.uniform(0.9, 1.2), rng.uniform(0.9, 1.2), rng.uniform(0.7, 0.95))
    obj.data.materials.append(m["hedge"])
    parts.append(obj)


def car(parts, m, x, y, heading, colour_name, colour):
    """Simple hatchback: body, cabin with glass, wheels. Nose toward `heading` degrees (0 = +X)."""
    body_mat = sl.material(colour_name, colour, 0.35, metallic=0.4)
    pieces = [sl.box("car", -2.0, 2.0, -0.87, 0.87, 0.3, 0.95, body_mat, round_edges=0.12),
              sl.box("cabin", -1.4, 0.9, -0.8, 0.8, 0.95, 1.45, m["glass"], round_edges=0.1),
              sl.box("roof", -1.3, 0.8, -0.78, 0.78, 1.42, 1.5, body_mat)]
    for wx in (-1.3, 1.3):
        for wy in (-0.8, 0.8):
            pieces.append(sl.cylinder("wheel", (wx, wy - 0.1, 0.32), (wx, wy + 0.1, 0.32), 0.32, m["tyre"], segments=14))
    rot = math.radians(heading)
    for piece in pieces:
        piece.rotation_euler = (0, 0, rot)
        piece.location = (x, y, 0)
    parts.extend(pieces)


# ---------------------------------------------------------------- build

def build_building(m):
    parts = []
    # Walls: ground floor of the loggia section is recessed to y = Y0 like the rest; the balcony and
    # piers stand in front of it. A slightly darker plinth course runs round the base.
    parts.append(sl.box("walls", X0, X1, Y0, Y1, 0.0, EAVE - 0.2, m["brick"]))
    parts.append(sl.box("plinth", X0 - 0.05, X1 + 0.05, Y0 - 0.05, Y1 + 0.05, 0.0, 0.35, m["brick"]))
    # Deep eaves: dark fascia board round the roof edge, soffit under it.
    for name, x0, x1, y0, y1 in (("fascia_main", X0 - 0.9, X1 + 0.9, Y0 - 0.9, Y1 + 0.9),
                                 ("fascia_front", X0 - 0.9, SPLIT + 0.9, FRONT - 0.9, Y0)):
        parts.append(sl.box(name, x0, x1, y0, y1, EAVE - 0.45, EAVE, m["fascia"]))
    parts.append(sl.hip_roof("roof_main", X0 - 0.9, X1 + 0.9, Y0 - 0.9, Y1 + 0.9, EAVE, RIDGE, m["roof"]))
    # A lower hip over the balcony section, meeting the main roof (as in the photos).
    parts.append(sl.hip_roof("roof_front", X0 - 0.9, SPLIT + 0.9, FRONT - 0.9, 1.5, EAVE, RIDGE - 1.0, m["roof"]))

    # Balcony slab, piers with arches (the loggia), railings with a gap for the stairs.
    parts.append(sl.box("balcony", X0, SPLIT, FRONT, Y0, FLOOR1 - 0.25, FLOOR1, m["concrete"]))
    piers = [X0 + i * (SPLIT - X0) / 5 for i in range(6)]
    for px in piers:
        parts.append(sl.box("pier", px - 0.35, px + 0.35, FRONT, FRONT + 0.6, 0.0, FLOOR1 - 0.25, m["brick"]))
    for a, b in zip(piers[:-1], piers[1:]):
        if abs((a + b) / 2 - STAIR_X) < 1.0:
            continue  # the staircase lands in this bay
        parts.append(arch_spandrel(a + 0.35, b - 0.35, FRONT, FRONT + 0.6, 2.1, FLOOR1 - 0.25, 0.7, m["brick"]))
    parts.append(sl.box("balcony_edge", X0, SPLIT, FRONT - 0.05, FRONT + 0.6, FLOOR1 - 0.45, FLOOR1 - 0.25, m["brick"]))
    gap0, gap1 = STAIR_X - STAIR_W / 2, STAIR_X + STAIR_W / 2
    railing(parts, m, (X0, FRONT, FLOOR1), (gap0, FRONT, FLOOR1))
    railing(parts, m, (gap1, FRONT, FLOOR1), (SPLIT, FRONT, FLOOR1))
    railing(parts, m, (X0, FRONT, FLOOR1), (X0, Y0, FLOOR1))
    railing(parts, m, (SPLIT, FRONT, FLOOR1), (SPLIT, Y0, FLOOR1))
    # Tables on the balcony.
    for tx in (-12.5, -9.0, -1.0, 1.5):
        parts.append(sl.cylinder("table", (tx, -6.3, FLOOR1), (tx, -6.3, FLOOR1 + 0.72), 0.45, m["white"], segments=16))

    # Staircase straight down toward the green: 18 steps of 18 cm, 28 cm treads, brick cheek walls, rails.
    steps = 18
    rise = FLOOR1 / steps
    for i in range(steps):
        y1 = FRONT - i * 0.28
        top = FLOOR1 - i * rise
        parts.append(sl.box("step", gap0, gap1, y1 - 0.28, y1, 0.0, top, m["concrete"]))
        for sx0, sx1 in ((gap0 - 0.3, gap0), (gap1, gap1 + 0.3)):
            parts.append(sl.box("cheek", sx0, sx1, y1 - 0.28, y1, 0.0, top + 0.12, m["brick"]))
    bottom_y = FRONT - steps * 0.28
    for sx in (gap0 - 0.15, gap1 + 0.15):
        railing(parts, m, (sx, FRONT, FLOOR1 + 0.12), (sx, bottom_y, 0.12), height=0.95, spacing=0.9)

    # Front windows. Upper floor: glazed doors onto the balcony, big windows on the right wing.
    for x in (-13.0, -9.5, -6.5, -1.5, 1.6):
        window(parts, m, x, FLOOR1 + 0.1, FLOOR1 + 2.4, 1.6, Y0, bars=1)
    for x in (5.6, 9.2, 12.8):
        window(parts, m, x, FLOOR1 + 0.7, FLOOR1 + 2.3, 2.6, Y0, bars=2)
    # Ground floor: windows and doors in the loggia, windows and the white door on the right wing.
    for x in (-12.5, -8.5, 0.2):
        window(parts, m, x, 0.9, 2.2, 1.8, Y0, bars=1)
    window(parts, m, -4.6, 0.02, 2.3, 1.6, Y0, bars=1)
    for x in (6.2, 12.4):
        window(parts, m, x, 1.0, 2.1, 2.2, Y0, bars=2)
    parts.append(sl.box("door", 8.8, 10.0, Y0 - 0.06, Y0 + 0.02, 0.0, 2.35, m["white"]))
    parts.append(sl.box("door_glass", 9.1, 9.7, Y0 - 0.08, Y0 - 0.05, 1.2, 2.1, m["glass"]))
    # Back and ends.
    for x in (-11.0, -5.0, 1.0, 7.0, 12.0):
        window(parts, m, x, FLOOR1 + 0.7, FLOOR1 + 2.1, 1.8, Y1, facing=1, bars=1)
        window(parts, m, x, 1.0, 2.1, 1.8, Y1, facing=1, bars=1)
    parts.append(sl.box("back_door", -2.4, -1.2, Y1 - 0.02, Y1 + 0.06, 0.0, 2.3, m["white"]))
    for face_x, facing in ((X0, -1), (X1, 1)):
        for y in (-2.0, 2.5):
            side_window(parts, m, y, FLOOR1 + 0.7, FLOOR1 + 2.1, 1.6, face_x, facing)
            side_window(parts, m, y, 1.0, 2.1, 1.6, face_x, facing)

    # Club sign on the right wing, benches under the windows.
    parts.append(sl.box("sign", 10.9, 14.1, Y0 - 0.1, Y0 - 0.02, 2.55, 3.1, m["sign"]))
    text = sl.text_mesh("sign_text", "SKY LINKS GOLF CLUB", 0.26, m["gold"], depth=0.02)
    text.rotation_euler = (math.radians(90), 0, 0)
    text.location = (12.5, Y0 - 0.11, 2.82)
    parts.append(text)
    for bx in (5.2, 12.0):
        parts.append(sl.box("bench_seat", bx - 0.9, bx + 0.9, Y0 - 0.7, Y0 - 0.3, 0.42, 0.48, m["wood"]))
        parts.append(sl.box("bench_back", bx - 0.9, bx + 0.9, Y0 - 0.32, Y0 - 0.26, 0.48, 0.9, m["wood"]))
        for lx in (bx - 0.8, bx + 0.8):
            parts.append(sl.box("bench_leg", lx - 0.04, lx + 0.04, Y0 - 0.7, Y0 - 0.3, 0.0, 0.42, m["white"]))
    return parts


def build_grounds(m, rng):
    parts = []
    # Paving round the building and a path from the stairs toward the first tee (+Y is the car park).
    parts.append(sl.box("apron", X0 - 3.0, X1 + 3.0, FRONT - 1.0, Y1 + 2.0, 0.0, 0.04, m["paving"]))
    bottom_y = FRONT - 18 * 0.28
    parts.append(sl.box("stair_path", STAIR_X - 1.6, STAIR_X + 1.6, bottom_y - 3.0, FRONT - 1.0, 0.0, 0.04, m["paving"]))
    parts.append(sl.box("side_path", X1 + 3.0, X1 + 5.5, -34.0, Y1 + 2.0, 0.0, 0.04, m["paving"]))

    # Practice putting green: a kidney shape with fringe, cups and short red flags.
    def kidney(scale):
        pts = []
        for i in range(48):
            a = 2 * math.pi * i / 48
            r = 1.0 + 0.18 * math.sin(2 * a + 0.6) + 0.08 * math.cos(3 * a)
            pts.append((math.cos(a) * 13.0 * r * scale, math.sin(a) * 7.0 * r * scale))
        return pts
    cx, cy = -1.5, -23.5
    for name, pts_scale, z, mat in (("fringe", 1.08, 0.05, m["fringe"]), ("putting_green", 1.0, 0.07, m["putting"])):
        bm_pts = [(cx + px, cy + py) for px, py in kidney(pts_scale)]
        mesh = bpy.data.meshes.new(name)
        verts = [(x, y, z) for x, y in bm_pts] + [(x, y, 0.0) for x, y in bm_pts]
        n = len(bm_pts)
        faces = [tuple(range(n))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.data.materials.append(mat)
        parts.append(obj)
    for fx, fy in ((-9.0, -22.0), (-3.0, -27.5), (3.5, -20.5), (8.0, -25.0), (-1.0, -18.5)):
        parts.append(sl.cylinder("cup", (fx, fy, 0.070), (fx, fy, 0.075), 0.06, m["cup"], segments=12))
        parts.append(sl.cylinder("practice_pin", (fx, fy, 0.07), (fx, fy, 1.25), 0.012, m["white"], segments=6))
        parts.append(sl.box("practice_flag", fx, fx + 0.32, fy - 0.004, fy + 0.004, 1.02, 1.24, m["flag"]))

    # White stake-and-rope fence between the building and the green.
    xs = np.linspace(-17.0, 13.0, 11)
    fy = -15.5
    for x in xs:
        if abs(x - STAIR_X) < 1.8:
            continue
        parts.append(sl.box("stake", x - 0.04, x + 0.04, fy - 0.04, fy + 0.04, 0.0, 0.75, m["white"]))
    for a, b in zip(xs[:-1], xs[1:]):
        if abs(a - STAIR_X) < 1.8 or abs(b - STAIR_X) < 1.8:
            continue
        parts.append(sl.cylinder("rope", (a, fy, 0.62), (b, fy, 0.62), 0.012, m["rope"], segments=6))

    # Flagpoles with the club flag, brick planters with shrubs, shrubs along the right wing.
    for px, py in ((17.5, -9.5), (-18.0, -10.0)):
        parts.append(sl.cylinder("flagpole", (px, py, 0.0), (px, py, 9.0), 0.06, m["white"], segments=10, radius_end=0.035))
        parts.append(sl.box("club_flag", px + 0.06, px + 1.9, py - 0.01, py + 0.01, 7.8, 8.9, m["clubflag"]))
        parts.append(sl.box("club_flag_stripe", px + 0.06, px + 0.7, py - 0.012, py + 0.012, 7.8, 8.9, m["flag"]))
    for px, py in ((X1 + 2.0, -10.0), (X0 - 2.0, -11.0), (STAIR_X - 2.6, bottom_y - 1.0), (STAIR_X + 2.6, bottom_y - 1.0)):
        parts.append(sl.box("planter", px - 0.6, px + 0.6, py - 0.6, py + 0.6, 0.0, 0.55, m["brick"]))
        parts.append(sl.box("planter_soil", px - 0.5, px + 0.5, py - 0.5, py + 0.5, 0.5, 0.56, m["soil"]))
        shrub(parts, m, px, py, 0.55, rng)
        parts[-1].location.z += 0.5
    for x in np.arange(4.6, 14.6, 1.25):
        shrub(parts, m, x, Y0 - 1.6, rng.uniform(0.45, 0.6), rng)

    # Car park behind the clubhouse: two rows of ten bays with painted lines, a central aisle.
    parts.append(sl.box("car_park", -16.0, 16.0, 8.5, 25.5, 0.0, 0.05, m["asphalt"]))
    parts.append(sl.box("kerb", -16.2, 16.2, 25.5, 25.8, 0.0, 0.15, m["concrete"]))
    for row_y0, row_y1 in ((8.5, 13.5), (20.5, 25.5)):
        for i in range(11):
            x = -12.5 + i * 2.5
            parts.append(sl.box("bay_line", x - 0.05, x + 0.05, row_y0 + 0.2, row_y1 - 0.2, 0.05, 0.056, m["lines"]))
    colours = [("M_CH_CarRed", (0.45, 0.02, 0.02)), ("M_CH_CarBlue", (0.02, 0.07, 0.3)),
               ("M_CH_CarSilver", (0.55, 0.56, 0.58)), ("M_CH_CarBlack", (0.02, 0.02, 0.025)),
               ("M_CH_CarWhite", (0.8, 0.8, 0.8)), ("M_CH_CarGreen", (0.03, 0.18, 0.08))]
    taken = [(0, 0), (1, 0), (3, 0), (6, 0), (7, 0), (9, 0), (2, 1), (4, 1), (5, 1), (8, 1)]
    for index, (bay, row) in enumerate(taken):
        x = -11.25 + bay * 2.5
        y, heading = (11.0, 90) if row == 0 else (23.0, -90)
        name, colour = colours[index % len(colours)]
        car(parts, m, x, y, heading + rng.uniform(-3, 3), name, colour)
    return parts


def collision_boxes():
    return [
        sl.box("UCX_SM_Clubhouse_00", X0, X1, Y0, Y1, 0.0, EAVE),
        sl.box("UCX_SM_Clubhouse_01", X0 + 5.5, X1 - 5.5, Y0 + 0.5, Y1 - 0.5, EAVE, RIDGE),
        sl.box("UCX_SM_Clubhouse_02", X0, SPLIT, FRONT, Y0, FLOOR1 - 0.45, FLOOR1 + 1.0),
        sl.box("UCX_SM_Clubhouse_03", STAIR_X - STAIR_W / 2 - 0.3, STAIR_X + STAIR_W / 2 + 0.3, FRONT - 18 * 0.28, FRONT, 0.0, FLOOR1),
    ]


def main():
    sl.reset_scene()
    out = sl.output_dir()
    rng = random.Random(5)
    m = materials(make_textures(out))
    building = sl.join("SM_Clubhouse", build_building(m) + build_grounds(m, rng), uv_scale=UV_TILE)
    collision = collision_boxes()
    for box in collision:
        box.display_type = "WIRE"
        box.hide_render = True
    sl.export_fbx(os.path.join(out, "SM_Clubhouse.fbx"), [building] + collision)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Clubhouse.blend"))
    tris = sum(len(p.vertices) - 2 for p in building.data.polygons)
    print(f"CLUBHOUSE {tris} triangles, {len(building.data.materials)} materials")
    if "--no-render" not in sys.argv:
        sl.preview_render(os.path.join(out, "Clubhouse_preview_front.png"), target=(0.0, -6.0, 3.5), distance=42, height=2.0,
                          yaw_degrees=-84, ground_size=90, lens=32)
        sl.preview_render(os.path.join(out, "Clubhouse_preview_aerial.png"), target=(0.0, -2.0, 0.0), distance=62, height=42,
                          yaw_degrees=-58, ground_size=90, lens=30)
    print(f"Clubhouse exported to {out}")


main()
