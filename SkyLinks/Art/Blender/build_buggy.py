"""
Sky Links golf buggy: a two-seat electric golf cart, modelled at real size (2.45 m long).

Run in Blender 4.2+ (Scripting tab > Open > Run Script), or headless:
    blender --background --python build_buggy.py -- <output folder>

Writes to SkyLinks/Art/Exports:
    SM_Buggy_Body.fbx   body, seats, canopy, windshield, bag rack (origin on the ground between the axles)
    SM_Buggy_Wheel.fbx  one wheel, origin at the hub, axle along Y, hub cap facing +Y (the cart's left)
    Buggy.blend         editable source
    Buggy_preview.png   render
Front is +X. This clears the current Blender scene.
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
        if text.filepath.endswith("build_buggy.py"):
            return os.path.dirname(bpy.path.abspath(text.filepath))
    return os.getcwd()


sys.path.insert(0, _script_dir())
import sl_common as sl  # noqa: E402

# Real golf cart proportions (metres).
WHEEL_RADIUS = 0.23
WHEEL_WIDTH = 0.18
FRONT_AXLE = 0.82
REAR_AXLE = -0.83
TRACK = 0.92  # distance between left and right wheel centres


def build_body():
    white = sl.material("M_Buggy_Body", (0.82, 0.82, 0.8), 0.25)
    trim = sl.material("M_Buggy_Trim", (0.015, 0.015, 0.015), 0.6)
    seat = sl.material("M_Buggy_Seat", (0.45, 0.33, 0.2), 0.7)
    metal = sl.material("M_Buggy_Metal", (0.8, 0.8, 0.82), 0.25, metallic=1.0)
    glass = sl.material("M_Buggy_Glass", (0.6, 0.7, 0.75), 0.05, alpha=0.3)
    bag = sl.material("M_Buggy_Bag", (0.12, 0.02, 0.03), 0.5)
    light = sl.material("M_Buggy_Light", (1.0, 0.95, 0.85), 0.2, emission=2.0)

    parts = []
    add = parts.append

    # Chassis and floor pan, open between the seats and the front cowl.
    add(sl.box("Floor", -1.0, 1.05, -0.56, 0.56, 0.26, 0.33, trim))
    add(sl.box("Floormat", -0.3, 0.72, -0.5, 0.5, 0.33, 0.345, trim, round_edges=0.01))

    # Front cowl with wheel arches cut in by stacking: lower nose, upper hood, dash.
    add(sl.box("NoseLower", 0.95, 1.22, -0.58, 0.58, 0.26, 0.62, white, round_edges=0.045))
    add(sl.box("Hood", 0.62, 1.14, -0.6, 0.6, 0.55, 0.8, white, round_edges=0.05))
    add(sl.box("Dash", 0.52, 0.72, -0.56, 0.56, 0.62, 0.98, white, round_edges=0.035))
    add(sl.box("FrontBumper", 1.18, 1.3, -0.55, 0.55, 0.28, 0.4, trim, round_edges=0.04))
    for side in (-1, 1):
        # Front fenders over the wheels and footwell side panels.
        add(sl.box(f"FrontFender{side}", FRONT_AXLE - 0.3, FRONT_AXLE + 0.32, side * 0.42 - 0.1, side * 0.42 + 0.1, 0.42, 0.6, white, round_edges=0.04))
        add(sl.cylinder(f"Headlight{side}", (1.2, side * 0.38, 0.66), (1.25, side * 0.38, 0.66), 0.07, light))

    # Seat pedestal and rear body.
    add(sl.box("SeatBase", -0.42, 0.22, -0.57, 0.57, 0.33, 0.6, white, round_edges=0.06))
    add(sl.box("RearBody", -1.22, -0.4, -0.6, 0.6, 0.3, 0.74, white, round_edges=0.05))
    add(sl.box("RearBumper", -1.3, -1.18, -0.55, 0.55, 0.28, 0.38, trim, round_edges=0.04))

    # Bench seat and backrest, split in two like a real cart.
    for side in (-1, 1):
        y0, y1 = (0.02, 0.54) if side > 0 else (-0.54, -0.02)
        add(sl.box(f"Cushion{side}", -0.38, 0.2, y0, y1, 0.6, 0.7, seat, round_edges=0.04))
        add(sl.box(f"Backrest{side}", -0.46, -0.36, y0, y1, 0.72, 1.12, seat, round_edges=0.04))
        add(sl.box(f"Armrest{side}", -0.4, 0.15, side * 0.57 - 0.03, side * 0.57 + 0.03, 0.72, 0.76, trim, round_edges=0.015))

    # Steering: column from the floor to a wheel in front of the left (driver's) seat.
    add(sl.cylinder("SteeringColumn", (0.62, 0.28, 0.4), (0.4, 0.28, 0.98), 0.025, trim))
    wheel = sl.cylinder("SteeringWheel", (0.41, 0.28, 0.96), (0.37, 0.28, 1.03), 0.19, trim, segments=32)
    add(wheel)
    add(sl.box("Pedals", 0.6, 0.7, 0.15, 0.4, 0.34, 0.38, trim))

    # Canopy: four struts and a moulded roof.
    for side in (-1, 1):
        add(sl.cylinder(f"FrontStrut{side}", (0.66, side * 0.53, 0.9), (0.72, side * 0.56, 1.9), 0.022, metal))
        add(sl.cylinder(f"RearStrut{side}", (-0.44, side * 0.55, 0.74), (-0.44, side * 0.56, 1.9), 0.022, metal))
    add(sl.box("Roof", -0.62, 0.98, -0.66, 0.66, 1.88, 1.95, white, round_edges=0.03))
    add(sl.box("RoofRim", -0.64, 1.0, -0.68, 0.68, 1.86, 1.89, trim))

    # Fold-down windshield, raked back slightly.
    windshield = sl.box("Windshield", 0.705, 0.715, -0.54, 0.54, 0.98, 1.84, glass)
    windshield.rotation_euler = (0.0, math.radians(-4), 0.0)
    add(windshield)

    # Rear bag rack with a golf bag and a few club heads.
    add(sl.box("BagWell", -1.22, -0.95, -0.56, 0.56, 0.74, 0.8, trim))
    add(sl.cylinder("BagStrap", (-1.1, 0.0, 0.8), (-1.1, 0.0, 1.18), 0.012, trim))
    # Crossbar between the rear struts, with a bracket holding the top of the bag.
    add(sl.box("RearCrossbar", -0.47, -0.41, -0.56, 0.56, 1.18, 1.22, metal))
    add(sl.cylinder("BagBracket", (-0.44, 0.2, 1.2), (-1.0, 0.2, 1.42), 0.015, metal, segments=8))
    bag_body = sl.cylinder("GolfBag", (-1.02, 0.18, 0.78), (-1.08, 0.2, 1.62), 0.13, bag)
    add(bag_body)
    add(sl.cylinder("GolfBagRim", (-1.08, 0.2, 1.6), (-1.085, 0.2, 1.66), 0.14, trim))
    for i, (dy, height) in enumerate(((0.12, 1.9), (0.22, 1.86), (0.2, 1.94), (0.28, 1.84))):
        add(sl.cylinder(f"Shaft{i}", (-1.08, dy, 1.6), (-1.1, dy, height), 0.008, metal, segments=8))
        add(sl.box(f"ClubHead{i}", -1.14, -1.06, dy - 0.03, dy + 0.03, height, height + 0.06, trim if i % 2 else metal, round_edges=0.015))

    return sl.join("SM_Buggy_Body", parts, uv_scale=1.0)


def build_wheel():
    tyre = sl.material("M_Buggy_Tyre", (0.02, 0.02, 0.02), 0.9)
    rim = sl.material("M_Buggy_Rim", (0.75, 0.75, 0.77), 0.3, metallic=1.0)
    half = WHEEL_WIDTH / 2
    parts = []
    tyre_body = sl.cylinder("Tyre", (0, -half, 0), (0, half, 0), WHEEL_RADIUS, tyre, segments=40)
    sl.bevel(tyre_body, 0.045, segments=4)
    parts.append(tyre_body)
    parts.append(sl.cylinder("Rim", (0, half - 0.02, 0), (0, half + 0.005, 0), WHEEL_RADIUS * 0.62, rim, segments=32))
    parts.append(sl.cylinder("HubCap", (0, half, 0), (0, half + 0.025, 0), WHEEL_RADIUS * 0.28, rim, segments=24))
    for i in range(5):
        angle = 2 * math.pi * i / 5
        x, z = math.cos(angle) * WHEEL_RADIUS * 0.42, math.sin(angle) * WHEEL_RADIUS * 0.42
        parts.append(sl.cylinder(f"Lug{i}", (x, half, z), (x, half + 0.018, z), 0.012, rim, segments=8))
    return sl.join("SM_Buggy_Wheel", parts, uv_scale=0.5)


def main():
    sl.reset_scene()
    out = sl.output_dir()

    body = build_body()
    wheel = build_wheel()
    sl.export_fbx(os.path.join(out, "SM_Buggy_Body.fbx"), [body])
    sl.export_fbx(os.path.join(out, "SM_Buggy_Wheel.fbx"), [wheel])

    # Four wheel copies only for the .blend and the preview; the game places wheels itself.
    copies = []
    for x in (FRONT_AXLE, REAR_AXLE):
        for side in (-1, 1):
            copy = wheel.copy()
            copy.location = (x, side * TRACK / 2, WHEEL_RADIUS)
            if side < 0:
                copy.rotation_euler = (0, 0, math.pi)  # hub cap faces outward on the right side
            bpy.context.scene.collection.objects.link(copy)
            copies.append(copy)
    wheel.location = (0, 0, -5)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Buggy.blend"))

    sl.preview_render(os.path.join(out, "Buggy_preview.png"), target=(0.0, 0.0, 0.8), distance=5.2, height=1.6, yaw_degrees=35, ground_size=20)
    print(f"Buggy exported to {out}")


main()
