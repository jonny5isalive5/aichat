"""
Builds /Game/Maps/Course: a playable 18-hole blockout of the Sky Links course.

Run inside the Unreal Editor (Tools > Execute Python Script, or `py path/to/this.py` in the
Output Log). The C++ module must be compiled first so `unreal.GolfHole` exists.

It creates:
  - Physical materials with the surface types the ball physics reads (Fairway, Rough, ...)
  - Flat-colour materials in the reference's bright palette
  - 18 holes laid out in two rows (front nine, back nine), each with rough, fairway, green,
    bunkers, water, trees, giant mushrooms and a teal tee pad
  - A GolfHole actor per hole with par, name, cup and default aim point
  - Sun, sky atmosphere, sky light and fog

Re-running the script clears everything in the "Course" outliner folders and rebuilds it.
Replace the blockout pieces with real art once the layouts play well.
"""

import unreal

MAP_PATH = "/Game/Maps/Course"
MAT_DIR = "/Game/Course/Materials"
M = 100.0  # metres -> cm

# Top surface heights (cm). Later layers sit on top so overlaps resolve the right way, and the
# steps stay under the ball radius so a rolling ball rides over them.
TOP = {"rough": 0.0, "water": 0.4, "fairway": 0.8, "tee": 0.9, "green": 1.2, "bunker": 1.6}

SURFACES = {
    "Fairway": unreal.PhysicalSurface.SURFACE_TYPE1,
    "Rough": unreal.PhysicalSurface.SURFACE_TYPE2,
    "Bunker": unreal.PhysicalSurface.SURFACE_TYPE3,
    "Green": unreal.PhysicalSurface.SURFACE_TYPE4,
    "Water": unreal.PhysicalSurface.SURFACE_TYPE5,
    "OutOfBounds": unreal.PhysicalSurface.SURFACE_TYPE6,
}

# name: (linear colour, physical surface)
MATERIALS = {
    "Rough": ((0.10, 0.42, 0.08), "Rough"),
    "Fairway": ((0.22, 0.70, 0.10), "Fairway"),
    "Green": ((0.40, 0.85, 0.18), "Green"),
    "Bunker": ((0.95, 0.80, 0.45), "Bunker"),
    "Water": ((0.05, 0.45, 0.85), "Water"),
    "TeePad": ((0.05, 0.65, 0.75), "Fairway"),
    "Trunk": ((0.35, 0.18, 0.07), "Rough"),
    "Canopy": ((0.12, 0.55, 0.12), "Rough"),
    "MushroomCap": ((0.85, 0.12, 0.08), "Rough"),
    "MushroomStem": ((0.95, 0.88, 0.72), "Rough"),
    "Lighthouse": ((0.95, 0.95, 0.92), "Rough"),
}

# Hole layouts in metres. Local frame: tee at (0, 0), +x toward the green, +y to the right.
# fairway / water: (x0, x1, y0, y1) rectangles. bunkers: (x, y, radius). trees, mushrooms: (x, y).
HOLES = [
    dict(name="Lighthouse Point", par=4, cup=(360, 0), green=16, aim=(240, 0),
         fairway=[(40, 310, -20, 20)], bunkers=[(335, -22, 7), (245, 24, 8)],
         trees=[(150, -45), (210, 46), (90, 40)], lighthouse=(420, 70)),
    dict(name="Mushroom Grove", par=3, cup=(170, 4), green=15, aim=(170, 4),
         fairway=[(125, 150, -14, 14)], water=[(55, 115, -20, 20)], bunkers=[(160, -20, 6), (182, 19, 6)],
         mushrooms=[(80, -38), (110, 40), (60, 32), (140, -42)]),
    dict(name="Coral Bend", par=4, cup=(240, 165), green=16, aim=(215, 0),
         fairway=[(40, 230, -18, 18), (200, 250, -18, 120)], bunkers=[(262, 140, 7), (215, 95, 6)],
         trees=[(170, 45), (160, 75), (185, 60)]),
    dict(name="Twin Lagoons", par=5, cup=(500, -5), green=17, aim=(230, 0),
         fairway=[(40, 200, -22, 22), (250, 440, -22, 22)], water=[(200, 250, -40, 40), (300, 340, 28, 60)],
         bunkers=[(470, -25, 8)], trees=[(120, -50), (380, -45)]),
    dict(name="Windy Mesa", par=3, cup=(190, -10), green=16, aim=(190, -10),
         fairway=[(110, 140, -15, 15)], bunkers=[(170, -30, 7), (205, 12, 7), (150, 15, 5)],
         mushrooms=[(60, -30), (90, 35)]),
    dict(name="Palm Row", par=4, cup=(380, 0), green=15, aim=(240, 0),
         fairway=[(40, 330, -18, 18)], bunkers=[(360, 20, 6)],
         trees=[(x, y) for x in range(60, 320, 40) for y in (-30, 30)]),
    dict(name="Island Hop", par=3, cup=(160, 0), green=16, aim=(160, 0),
         fairway=[(-10, 15, -12, 12)], water=[(20, 190, -50, 50)], bunkers=[(172, -12, 4)]),
    dict(name="Sandy Shore", par=4, cup=(370, 5), green=16, aim=(240, 5),
         fairway=[(40, 320, -20, 20)], water=[(60, 360, -80, -45)],
         bunkers=[(100, -32, 10), (160, -34, 11), (220, -32, 10), (280, -30, 9)]),
    dict(name="Homeward Light", par=5, cup=(520, 30), green=17, aim=(240, 0),
         fairway=[(40, 260, -22, 22), (230, 470, 10, 50)], water=[(430, 470, -40, 0)],
         bunkers=[(290, -5, 9), (495, 5, 7)], trees=[(250, -40), (330, 70), (400, -10)]),
    dict(name="Cloud Terrace", par=4, cup=(350, -20), green=16, aim=(240, -5),
         fairway=[(40, 300, -20, 20)], bunkers=[(320, 5, 7), (200, -28, 8)],
         mushrooms=[(120, 40), (260, 40), (180, -45)]),
    dict(name="Toadstool Alley", par=4, cup=(225, -160), green=16, aim=(205, 0),
         fairway=[(40, 220, -18, 18), (190, 240, -120, 18)], bunkers=[(250, -140, 6)],
         mushrooms=[(160, -40), (175, -70), (150, -60)]),
    dict(name="Blue Hole", par=3, cup=(180, 0), green=15, aim=(180, 0),
         fairway=[(120, 150, -15, 15)], water=[(40, 110, -40, 40), (160, 210, 25, 50)], bunkers=[(195, -18, 6)]),
    dict(name="Long Reef", par=5, cup=(560, 0), green=17, aim=(250, 0),
         fairway=[(40, 180, -20, 20), (230, 520, -20, 20)], water=[(180, 230, -60, 60)],
         bunkers=[(300, 25, 8), (420, -25, 8)], trees=[(100, -40), (360, 40)]),
    dict(name="Pinwheel", par=3, cup=(175, 15), green=16, aim=(175, 15),
         fairway=[(100, 130, -12, 12)], bunkers=[(155, -5, 5), (175, -8, 5), (195, 10, 5), (170, 38, 6)]),
    dict(name="Harbor Run", par=4, cup=(360, 10), green=15, aim=(240, -3),
         fairway=[(40, 310, -20, 20)], water=[(0, 380, 30, 70)], bunkers=[(340, -15, 7)],
         trees=[(150, -40), (250, -40)]),
    dict(name="Giant's Step", par=4, cup=(370, 0), green=16, aim=(240, 0),
         fairway=[(40, 160, -20, 20), (170, 330, -20, 20)], bunkers=[(165, 0, 7)],
         trees=[(100, 40), (280, -40)]),
    dict(name="Sunset Carry", par=3, cup=(215, 0), green=15, aim=(215, 0),
         fairway=[(-10, 20, -12, 12)], water=[(30, 200, -40, 40)], bunkers=[(230, 15, 6), (205, -18, 5)]),
    dict(name="Grand Finale", par=5, cup=(520, 15), green=18, aim=(230, 0),
         fairway=[(40, 240, -24, 24), (260, 470, -10, 40)], water=[(240, 260, -60, 60), (450, 500, -45, -12)],
         bunkers=[(300, -20, 9), (505, 40, 7)], trees=[(200, 50), (300, 60)],
         mushrooms=[(150, -50), (350, -35), (420, 70)]),
]

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
CUBE = unreal.load_asset("/Engine/BasicShapes/Cube")
CYLINDER = unreal.load_asset("/Engine/BasicShapes/Cylinder")
SPHERE = unreal.load_asset("/Engine/BasicShapes/Sphere")


def get_or_create(name, path, cls, factory):
    full = f"{path}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(full):
        return unreal.load_asset(full)
    return asset_tools.create_asset(name, path, cls, factory)


def build_materials():
    physical = {}
    for surface, surface_type in SURFACES.items():
        pm = get_or_create(f"PM_{surface}", MAT_DIR, unreal.PhysicalMaterial, unreal.PhysicalMaterialFactoryNew())
        pm.set_editor_property("surface_type", surface_type)
        unreal.EditorAssetLibrary.save_loaded_asset(pm)
        physical[surface] = pm

    materials = {}
    lib = unreal.MaterialEditingLibrary
    for name, (colour, surface) in MATERIALS.items():
        mat = get_or_create(f"M_{name}", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
        lib.delete_all_material_expressions(mat)
        base = lib.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -400, 0)
        base.set_editor_property("constant", unreal.LinearColor(colour[0], colour[1], colour[2], 1.0))
        lib.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
        rough = lib.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 200)
        rough.set_editor_property("r", 0.9)
        lib.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
        mat.set_editor_property("phys_material", physical[surface])
        lib.recompile_material(mat)
        unreal.EditorAssetLibrary.save_loaded_asset(mat)
        materials[name] = mat
    return materials


def spawn(mesh, material, location, scale, folder, label, collide=True):
    actor = actors.spawn_actor_from_object(mesh, unreal.Vector(*location), unreal.Rotator(0, 0, 0))
    actor.set_actor_scale3d(unreal.Vector(*scale))
    component = actor.static_mesh_component
    component.set_material(0, material)
    if not collide:
        component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    actor.set_actor_label(label)
    actor.set_folder_path(folder)
    return actor


def slab(origin, rect, top, material, folder, label):
    """A flat 20 cm box whose top face sits at `top` cm."""
    x0, x1, y0, y1 = rect
    centre = (origin[0] + (x0 + x1) * 0.5 * M, origin[1] + (y0 + y1) * 0.5 * M, top - 10.0)
    return spawn(CUBE, material, centre, (x1 - x0, y1 - y0, 0.2), folder, label)


def disc(origin, x, y, radius, top, material, folder, label):
    centre = (origin[0] + x * M, origin[1] + y * M, top - 10.0)
    return spawn(CYLINDER, material, centre, (radius * 2, radius * 2, 0.2), folder, label)


def tree(origin, x, y, mats, folder, index):
    base = (origin[0] + x * M, origin[1] + y * M)
    spawn(CYLINDER, mats["Trunk"], (base[0], base[1], 300), (1.2, 1.2, 6), folder, f"TreeTrunk{index}")
    spawn(SPHERE, mats["Canopy"], (base[0], base[1], 800), (8, 8, 7), folder, f"TreeCanopy{index}")


def mushroom(origin, x, y, mats, folder, index):
    base = (origin[0] + x * M, origin[1] + y * M)
    spawn(CYLINDER, mats["MushroomStem"], (base[0], base[1], 500), (2.5, 2.5, 10), folder, f"MushroomStem{index}")
    spawn(SPHERE, mats["MushroomCap"], (base[0], base[1], 1050), (14, 14, 5), folder, f"MushroomCap{index}")


def bounds(hole):
    xs, ys = [0, hole["cup"][0]], [0, hole["cup"][1]]
    for key in ("fairway", "water"):
        for x0, x1, y0, y1 in hole.get(key, []):
            xs += [x0, x1]
            ys += [y0, y1]
    for x, y, r in hole.get("bunkers", []):
        xs += [x - r, x + r]
        ys += [y - r, y + r]
    for key in ("trees", "mushrooms"):
        for x, y in hole.get(key, []):
            xs.append(x)
            ys.append(y)
    margin = 35
    return (min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin)


def build_hole(number, hole, mats):
    row, column = divmod(number - 1, 9)
    origin = (row * 800 * M, column * 350 * M)
    folder = f"Course/Hole{number:02d}"

    slab(origin, bounds(hole), TOP["rough"], mats["Rough"], folder, "Rough")
    for i, rect in enumerate(hole.get("water", [])):
        slab(origin, rect, TOP["water"], mats["Water"], folder, f"Water{i}")
    for i, rect in enumerate(hole.get("fairway", [])):
        slab(origin, rect, TOP["fairway"], mats["Fairway"], folder, f"Fairway{i}")
    disc(origin, 0, 0, 5, TOP["tee"], mats["TeePad"], folder, "TeePad")
    cx, cy = hole["cup"]
    disc(origin, cx, cy, hole["green"], TOP["green"], mats["Green"], folder, "Green")
    for i, (x, y, r) in enumerate(hole.get("bunkers", [])):
        disc(origin, x, y, r, TOP["bunker"], mats["Bunker"], folder, f"Bunker{i}")
    for i, (x, y) in enumerate(hole.get("trees", [])):
        tree(origin, x, y, mats, folder, i)
    for i, (x, y) in enumerate(hole.get("mushrooms", [])):
        mushroom(origin, x, y, mats, folder, i)
    if "lighthouse" in hole:
        lx, ly = hole["lighthouse"]
        base = (origin[0] + lx * M, origin[1] + ly * M)
        spawn(CYLINDER, mats["Lighthouse"], (base[0], base[1], 1500), (6, 6, 30), folder, "Lighthouse")
        spawn(CYLINDER, mats["MushroomCap"], (base[0], base[1], 3150), (7, 7, 3), folder, "LighthouseTop")

    golf_hole = actors.spawn_actor_from_class(unreal.GolfHole, unreal.Vector(origin[0], origin[1], TOP["tee"]), unreal.Rotator(0, 0, 0))
    golf_hole.set_actor_label(f"GolfHole{number:02d}")
    golf_hole.set_folder_path(folder)
    golf_hole.set_editor_property("hole_number", number)
    golf_hole.set_editor_property("par", hole["par"])
    golf_hole.set_editor_property("hole_name", hole["name"])
    ax, ay = hole["aim"]
    golf_hole.set_editor_property("aim_point", unreal.Vector(ax * M, ay * M, 0))
    cup_root = golf_hole.get_editor_property("cup_root")
    cup_root.set_world_location(unreal.Vector(origin[0] + cx * M, origin[1] + cy * M, TOP["green"]), False, False)
    return origin


def build_environment():
    folder = "Course/Environment"
    sun = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 5000), unreal.Rotator(0, -45, 30))
    sun.set_folder_path(folder)
    sun.light_component.set_editor_property("atmosphere_sun_light", True)
    sun.light_component.set_editor_property("intensity", 8.0)
    for cls in (unreal.SkyAtmosphere, unreal.ExponentialHeightFog):
        actors.spawn_actor_from_class(cls, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0)).set_folder_path(folder)
    sky = actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 1000), unreal.Rotator(0, 0, 0))
    sky.set_folder_path(folder)
    sky.light_component.set_editor_property("real_time_capture", True)


def clear_course():
    for actor in actors.get_all_level_actors():
        if str(actor.get_folder_path()).startswith("Course"):
            actors.destroy_actor(actor)


def main():
    if not hasattr(unreal, "GolfHole"):
        raise RuntimeError("unreal.GolfHole not found. Compile the SkyLinks C++ module, then run this again.")

    if unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH):
        levels.load_level(MAP_PATH)
        clear_course()
    else:
        levels.new_level(MAP_PATH)

    mats = build_materials()
    first_tee = None
    with unreal.ScopedSlowTask(len(HOLES), "Building Sky Links course") as task:
        task.make_dialog(True)
        for number, hole in enumerate(HOLES, start=1):
            task.enter_progress_frame(1, f"Hole {number}: {hole['name']}")
            origin = build_hole(number, hole, mats)
            first_tee = first_tee or origin

    start = actors.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(first_tee[0] - 500, first_tee[1], 120), unreal.Rotator(0, 0, 0))
    start.set_folder_path("Course/Environment")
    build_environment()

    levels.save_current_level()
    unreal.log(f"Sky Links: built {len(HOLES)} holes, par {sum(h['par'] for h in HOLES)}.")


main()
