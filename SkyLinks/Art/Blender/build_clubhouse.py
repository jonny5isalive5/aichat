"""
Sky Links clubhouse: two-storey colonial clubhouse with a columned entrance, a single-storey
pro shop wing with a deck, stone chimneys and the club sign. Real size (about 42 x 20 m).

Run in Blender 4.2+ (Scripting tab > Open > Run Script), or headless:
    blender --background --python build_clubhouse.py -- <output folder>

Writes to SkyLinks/Art/Exports:
    SM_Clubhouse.fbx       the building plus UCX_ collision boxes Unreal picks up automatically
    Clubhouse.blend        editable source
    Clubhouse_preview.png  render
The entrance faces -Y. Origin is on the ground at the centre of the main block. Clears the current scene.
"""

import math
import os
import sys

import bpy


def _script_dir():
    path = globals().get("__file__", "")
    if path and os.path.isfile(path):
        return os.path.dirname(os.path.abspath(path))
    for text in bpy.data.texts:
        if text.filepath.endswith("build_clubhouse.py"):
            return os.path.dirname(bpy.path.abspath(text.filepath))
    return os.getcwd()


sys.path.insert(0, _script_dir())
import sl_common as sl  # noqa: E402

# Main block footprint and heights (metres).
MX0, MX1, MY0, MY1 = -15.0, 15.0, -7.0, 7.0
PLINTH = 0.6
EAVE = 7.4
RIDGE = 11.0
# Pro shop wing on the east end.
WX0, WX1, WY0, WY1 = 15.0, 27.0, -5.0, 5.0
WING_EAVE = 4.4


def materials():
    return dict(
        wall=sl.material("M_Clubhouse_Render", (0.78, 0.76, 0.7), 0.85),
        roof=sl.material("M_Clubhouse_Slate", (0.06, 0.065, 0.075), 0.6),
        trim=sl.material("M_Clubhouse_Trim", (0.9, 0.9, 0.88), 0.5),
        frame=sl.material("M_Clubhouse_WindowFrame", (0.03, 0.06, 0.045), 0.4),
        glass=sl.material("M_Clubhouse_Glass", (0.05, 0.07, 0.09), 0.05, metallic=0.4),
        stone=sl.material("M_Clubhouse_Stone", (0.32, 0.29, 0.25), 0.9),
        door=sl.material("M_Clubhouse_Door", (0.2, 0.1, 0.05), 0.5),
        deck=sl.material("M_Clubhouse_Deck", (0.3, 0.2, 0.12), 0.8),
        gold=sl.material("M_Clubhouse_Sign", (0.8, 0.6, 0.25), 0.3, metallic=1.0),
    )


def window(parts, m, face_y, x, z0, z1, width, facing):
    """Framed window with glazing bars, set on a wall at y = face_y. facing is -1 (front) or +1 (back)."""
    half = width / 2
    parts.append(sl.box("Glass", x - half, x + half, *sorted((face_y, face_y + facing * 0.03)), z0, z1, m["glass"]))
    frame_y0, frame_y1 = sorted((face_y, face_y + facing * 0.1))
    f = 0.08
    parts.append(sl.box("FrameL", x - half - f, x - half, frame_y0, frame_y1, z0 - f, z1 + f, m["frame"]))
    parts.append(sl.box("FrameR", x + half, x + half + f, frame_y0, frame_y1, z0 - f, z1 + f, m["frame"]))
    parts.append(sl.box("FrameT", x - half - f, x + half + f, frame_y0, frame_y1, z1, z1 + f, m["frame"]))
    parts.append(sl.box("Sill", x - half - 0.15, x + half + 0.15, *sorted((face_y, face_y + facing * 0.16)), z0 - 0.14, z0, m["trim"]))
    parts.append(sl.box("BarV", x - 0.025, x + 0.025, frame_y0, frame_y1, z0, z1, m["frame"]))
    for i in range(1, 3):
        zb = z0 + (z1 - z0) * i / 3
        parts.append(sl.box("BarH", x - half, x + half, frame_y0, frame_y1, zb - 0.02, zb + 0.02, m["frame"]))


def build(m):
    parts = []
    add = parts.append

    # Main two-storey block on a stone plinth, with a band course between floors and a cornice.
    add(sl.box("Plinth", MX0 - 0.15, MX1, MY0 - 0.15, MY1 + 0.15, 0.0, PLINTH, m["stone"]))
    add(sl.box("MainWalls", MX0, MX1, MY0, MY1, PLINTH, EAVE, m["wall"]))
    add(sl.box("BandCourse", MX0 - 0.06, MX1, MY0 - 0.06, MY1 + 0.06, 3.9, 4.1, m["trim"]))
    add(sl.box("Cornice", MX0 - 0.25, MX1 + 0.25, MY0 - 0.25, MY1 + 0.25, EAVE - 0.3, EAVE, m["trim"]))
    for x in (MX0, MX1):
        for y in (MY0, MY1):
            add(sl.box("Quoin", x - 0.2, x + 0.2, y - 0.2, y + 0.2, PLINTH, EAVE - 0.3, m["trim"]))
    add(sl.hip_roof("MainRoof", MX0 - 0.7, MX1 + 0.7, MY0 - 0.7, MY1 + 0.7, EAVE, RIDGE, m["roof"]))

    # Dormers on the front roof slope.
    for x in (-8.0, 8.0):
        add(sl.box("Dormer", x - 1.1, x + 1.1, MY0 + 1.2, MY0 + 3.2, EAVE - 0.2, EAVE + 1.9, m["wall"]))
        add(sl.prism("DormerRoof", [(x - 1.35, EAVE + 1.9), (x + 1.35, EAVE + 1.9), (x, EAVE + 2.7)], MY0 + 1.0, MY0 + 3.4, m["roof"]))
        window(parts, m, MY0 + 1.2, x, EAVE + 0.2, EAVE + 1.5, 1.0, -1)

    # Front windows, ground and first floor, skipping the entrance bay.
    for x in (-12.5, -9.5, -6.5, 6.5, 9.5, 12.5):
        window(parts, m, MY0, x, 1.3, 3.4, 1.5, -1)
    for x in (-12.5, -9.5, -6.5, -3.0, 3.0, 6.5, 9.5, 12.5):
        window(parts, m, MY0, x, 4.7, 6.5, 1.3, -1)
    # Rear: tall windows onto the course.
    for x in (-12.5, -9.5, -6.5, -3.5, 0.0, 3.5, 6.5, 9.5, 12.5):
        window(parts, m, MY1, x, 1.2, 3.5, 1.8, 1)
        window(parts, m, MY1, x, 4.7, 6.5, 1.3, 1)

    # Entrance portico: four columns, entablature with the club name, pediment, steps and double doors.
    add(sl.box("PorticoFloor", -3.6, 3.6, MY0 - 3.4, MY0, 0.0, PLINTH, m["stone"]))
    for i in range(3):
        depth = 0.4 * (i + 1)
        add(sl.box(f"Step{i}", -2.4, 2.4, MY0 - 3.4 - depth, MY0 - 3.4 - depth + 0.4, 0.0, PLINTH - 0.2 * (i + 1) + 0.2, m["stone"]))
    for x in (-3.0, -1.1, 1.1, 3.0):
        add(sl.cylinder("ColumnBase", (x, MY0 - 3.0, PLINTH), (x, MY0 - 3.0, PLINTH + 0.25), 0.32, m["trim"]))
        add(sl.cylinder("Column", (x, MY0 - 3.0, PLINTH + 0.25), (x, MY0 - 3.0, 4.6), 0.24, m["trim"], radius_end=0.21))
        add(sl.box("Capital", x - 0.32, x + 0.32, MY0 - 3.32, MY0 - 2.68, 4.6, 4.8, m["trim"]))
    add(sl.box("Entablature", -3.7, 3.7, MY0 - 3.5, MY0, 4.8, 5.5, m["trim"]))
    add(sl.prism("Pediment", [(-3.9, 5.5), (3.9, 5.5), (0.0, 7.0)], MY0 - 3.55, MY0, m["trim"]))
    # Roof over the portico: a chevron, so the triangular pediment stays visible underneath.
    add(sl.prism("PedimentRoof", [(-4.1, 5.45), (-3.75, 5.45), (0.0, 6.98), (3.75, 5.45), (4.1, 5.45), (0.0, 7.18)], MY0 - 3.75, MY0 - 0.2, m["roof"]))
    add(sl.box("DoorSurround", -1.4, 1.4, MY0 - 0.12, MY0, PLINTH, 3.7, m["trim"]))
    add(sl.box("Doors", -1.1, 1.1, MY0 - 0.16, MY0 - 0.1, PLINTH, 3.4, m["door"]))
    add(sl.box("DoorSplit", -0.02, 0.02, MY0 - 0.18, MY0 - 0.15, PLINTH, 3.4, m["frame"]))
    add(sl.box("Fanlight", -1.1, 1.1, MY0 - 0.17, MY0 - 0.12, 3.45, 3.65, m["glass"]))

    sign = sl.text_mesh("Sign", "SKY LINKS GOLF CLUB", 0.36, m["gold"], depth=0.02)
    sign.rotation_euler = (math.radians(90), 0, 0)
    sign.location = (0.0, MY0 - 3.53, 5.15)
    add(sign)

    # Stone chimneys through the roof.
    for x in (-10.5, 10.5):
        add(sl.box("Chimney", x - 0.7, x + 0.7, 1.5, 3.0, EAVE - 1.0, RIDGE + 1.2, m["stone"]))
        add(sl.box("ChimneyCap", x - 0.85, x + 0.85, 1.35, 3.15, RIDGE + 1.2, RIDGE + 1.4, m["trim"]))

    # Pro shop wing with its own hip roof and shopfront windows.
    add(sl.box("WingPlinth", WX0, WX1 + 0.15, WY0 - 0.15, WY1 + 0.15, 0.0, 0.4, m["stone"]))
    add(sl.box("WingWalls", WX0, WX1, WY0, WY1, 0.4, WING_EAVE, m["wall"]))
    add(sl.box("WingCornice", WX0, WX1 + 0.2, WY0 - 0.2, WY1 + 0.2, WING_EAVE - 0.25, WING_EAVE, m["trim"]))
    add(sl.hip_roof("WingRoof", WX0 - 0.2, WX1 + 0.6, WY0 - 0.6, WY1 + 0.6, WING_EAVE, WING_EAVE + 2.6, m["roof"]))
    for x in (17.5, 20.0, 22.5, 25.0):
        window(parts, m, WY0, x, 0.9, 3.3, 2.0, -1)
    add(sl.box("ShopDoor", 26.0 - 0.05, 26.0 + 0.05, -1.0, 1.0, 0.4, 3.0, m["door"]))

    # Timber deck along the back of the wing, looking over the course, with a railing.
    add(sl.box("Deck", WX0, WX1 + 0.4, WY1, WY1 + 4.0, 0.0, 0.4, m["deck"]))
    posts = [WX0 + 0.2 + i * 1.5 for i in range(9)]
    for x in posts:
        add(sl.box("RailPost", x - 0.06, x + 0.06, WY1 + 3.85, WY1 + 3.97, 0.4, 1.4, m["trim"]))
    add(sl.box("RailTop", WX0, WX1 + 0.4, WY1 + 3.84, WY1 + 3.98, 1.35, 1.45, m["trim"]))
    add(sl.box("RailMid", WX0, WX1 + 0.4, WY1 + 3.88, WY1 + 3.94, 0.85, 0.9, m["trim"]))
    for x in (18.0, 22.5):
        add(sl.cylinder("Table", (x, WY1 + 2.0, 0.4), (x, WY1 + 2.0, 1.15), 0.05, m["frame"], segments=12))
        add(sl.cylinder("TableTop", (x, WY1 + 2.0, 1.15), (x, WY1 + 2.0, 1.19), 0.55, m["trim"], segments=24))
        add(sl.cylinder("Umbrella", (x, WY1 + 2.0, 1.19), (x, WY1 + 2.0, 2.6), 0.025, m["frame"], segments=8))
        add(sl.cylinder("Canopy", (x, WY1 + 2.0, 2.3), (x, WY1 + 2.0, 2.75), 1.4, m["door"], segments=8, radius_end=0.05))

    building = sl.join("SM_Clubhouse", parts, uv_scale=2.0)

    # Simple convex collision, picked up by Unreal because of the UCX_ prefix and matching name.
    collision = [
        sl.box("UCX_SM_Clubhouse_00", MX0 - 0.3, MX1, MY0 - 0.3, MY1 + 0.3, 0.0, EAVE),
        sl.box("UCX_SM_Clubhouse_01", MX0 + 7.0, MX1 - 7.0, MY0 + 1.0, MY1 - 1.0, EAVE, RIDGE),
        sl.box("UCX_SM_Clubhouse_02", WX0, WX1 + 0.4, WY0 - 0.2, WY1 + 0.2, 0.0, WING_EAVE + 1.5),
        sl.box("UCX_SM_Clubhouse_03", -3.9, 3.9, MY0 - 3.7, MY0, 0.0, 6.0),
        sl.box("UCX_SM_Clubhouse_04", WX0, WX1 + 0.4, WY1, WY1 + 4.0, 0.0, 1.45),
    ]
    return building, collision


def main():
    sl.reset_scene()
    out = sl.output_dir()
    m = materials()
    building, collision = build(m)
    for box in collision:
        box.display_type = "WIRE"
        box.hide_render = True

    sl.export_fbx(os.path.join(out, "SM_Clubhouse.fbx"), [building] + collision)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Clubhouse.blend"))
    sl.preview_render(os.path.join(out, "Clubhouse_preview.png"), target=(4.0, 0.0, 4.0), distance=48, height=12, yaw_degrees=-62, ground_size=90)
    print(f"Clubhouse exported to {out}")


main()
