"""
Sky Links golf clubs: an iron (used for full shots and chips) and a putter, at real size.

Run in Blender 4.2+ (Scripting tab > Open > Run Script) or headless:
    blender --background --python build_clubs.py -- <output folder>

Writes to SkyLinks/Art/Exports: SM_Club_Iron.fbx, SM_Club_Putter.fbx, Clubs.blend, Clubs_preview.png.
The origin is the bottom of the club head and the shaft runs up +Z to the grip, so the game can stand
the club on the ball and point it at the golfer's hands. The club face looks along +X.
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
        if text.filepath.endswith("build_clubs.py"):
            return os.path.dirname(bpy.path.abspath(text.filepath))
    return os.getcwd()


sys.path.insert(0, _script_dir())
import sl_common as sl  # noqa: E402


def materials():
    return dict(
        steel=sl.material("M_Club_Steel", (0.75, 0.76, 0.78), 0.25, metallic=1.0),
        grip=sl.material("M_Club_Grip", (0.02, 0.02, 0.02), 0.8),
        head=sl.material("M_Club_Head", (0.55, 0.56, 0.58), 0.2, metallic=1.0),
        accent=sl.material("M_Club_Accent", (0.6, 0.05, 0.05), 0.4),
    )


def shaft(parts, m, length, grip_length=0.27):
    """Shaft tapering from 7.5 mm at the hosel to 15 mm under the grip, then a rubber grip."""
    top = length - grip_length
    parts.append(sl.cylinder("Hosel", (0, 0, 0.02), (0, 0, 0.09), 0.006, m["steel"], segments=12))
    parts.append(sl.cylinder("Shaft", (0, 0, 0.09), (0, 0, top), 0.0045, m["steel"], segments=12, radius_end=0.0065))
    parts.append(sl.cylinder("Grip", (0, 0, top), (0, 0, length), 0.0115, m["grip"], segments=16, radius_end=0.0135))
    parts.append(sl.cylinder("GripCap", (0, 0, length), (0, 0, length + 0.004), 0.0135, m["grip"], segments=16))


def build_iron(m):
    parts = []
    # Blade: 7.5 cm toe-to-heel along -Y/+Y, 5 cm tall, thin, face towards +X, sole at z=0.
    parts.append(sl.box("Blade", -0.012, 0.004, -0.045, 0.03, 0.0, 0.05, m["head"], round_edges=0.004))
    parts.append(sl.box("Cavity", -0.02, -0.011, -0.035, 0.022, 0.006, 0.035, m["accent"], round_edges=0.003))
    shaft(parts, m, 0.95)
    return sl.join("SM_Club_Iron", parts, uv_scale=0.1)


def build_putter(m):
    parts = []
    # Blade putter: 11 cm long, 2.5 cm tall, face towards +X.
    parts.append(sl.box("PutterHead", -0.025, 0.004, -0.07, 0.04, 0.0, 0.025, m["head"], round_edges=0.004))
    parts.append(sl.box("SightLine", -0.012, -0.004, -0.0015, 0.0015, 0.025, 0.026, m["accent"]))
    shaft(parts, m, 0.88)
    return sl.join("SM_Club_Putter", parts, uv_scale=0.1)


def main():
    sl.reset_scene()
    out = sl.output_dir()
    m = materials()
    iron = build_iron(m)
    putter = build_putter(m)
    sl.export_fbx(os.path.join(out, "SM_Club_Iron.fbx"), [iron])
    sl.export_fbx(os.path.join(out, "SM_Club_Putter.fbx"), [putter])
    iron.location = (0, -0.15, 0)
    putter.location = (0, 0.15, 0)
    for obj in (iron, putter):
        obj.rotation_euler = (math.radians(-30), 0, 0)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Clubs.blend"))
    sl.preview_render(os.path.join(out, "Clubs_preview.png"), target=(0, 0, 0.4), distance=1.6, height=0.4, yaw_degrees=10, ground_size=3)
    print(f"Clubs exported to {out}")


main()
