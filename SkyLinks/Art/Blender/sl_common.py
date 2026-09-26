"""
Shared helpers for the Sky Links Blender scripts (Blender 4.2+).

Models are built in metres with +X as the front and +Z up, which imports into Unreal facing +X.
Every exported mesh gets box-projected UVs (1 UV unit = 1 metre) so tiling textures work straight away.
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector


def output_dir():
    """Exports go to SkyLinks/Art/Exports, or to the folder given after `--` on the command line."""
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1:]
        if args:
            os.makedirs(args[0], exist_ok=True)
            return args[0]
    here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
    candidate = os.path.normpath(os.path.join(here, "..", "Exports"))
    if here and os.path.isdir(os.path.dirname(candidate)):
        os.makedirs(candidate, exist_ok=True)
        return candidate
    fallback = os.path.join(os.path.expanduser("~"), "SkyLinksExports")
    os.makedirs(fallback, exist_ok=True)
    return fallback


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0


_materials = {}


def material(name, color, roughness=0.5, metallic=0.0, alpha=1.0, emission=0.0):
    if name in _materials:
        return _materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        mat.blend_method = "BLEND"
    if emission > 0.0:
        bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission
    mat.diffuse_color = (*color, alpha)
    _materials[name] = mat
    return mat


def _link(name, bm, mat, smooth=False):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    if smooth:
        for poly in mesh.polygons:
            poly.use_smooth = True
        mesh.set_sharp_from_angle(angle=math.radians(40))
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    if mat is not None:
        mesh.materials.append(mat)
    return obj


def bevel(obj, width, segments=3):
    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(40)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.set_sharp_from_angle(angle=math.radians(40))
    return obj


def box(name, x0, x1, y0, y1, z0, z1, mat=None, round_edges=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((x0 + (v.co.x + 0.5) * (x1 - x0), y0 + (v.co.y + 0.5) * (y1 - y0), z0 + (v.co.z + 0.5) * (z1 - z0)))
    obj = _link(name, bm, mat)
    if round_edges > 0.0:
        bevel(obj, round_edges)
    return obj


def cylinder(name, start, end, radius, mat, segments=24, radius_end=None):
    """Cylinder (or cone) running from `start` to `end`."""
    start, end = Vector(start), Vector(end)
    axis = end - start
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=radius, radius2=radius if radius_end is None else radius_end, depth=axis.length)
    rotation = Vector((0, 0, 1)).rotation_difference(axis.normalized()).to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((start + end) / 2) @ rotation, verts=bm.verts)
    return _link(name, bm, mat, smooth=True)


def prism(name, points_xz, y0, y1, mat):
    """Extrudes a polygon drawn in the XZ plane along Y (gables, roof ends)."""
    bm = bmesh.new()
    front = [bm.verts.new((x, y0, z)) for x, z in points_xz]
    back = [bm.verts.new((x, y1, z)) for x, z in points_xz]
    bm.faces.new(front[::-1])
    bm.faces.new(back)
    n = len(points_xz)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((front[i], front[j], back[j], back[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _link(name, bm, mat)


def hip_roof(name, x0, x1, y0, y1, z_eave, z_ridge, mat, thickness=0.18):
    """Hipped roof over a rectangle: four sloped faces meeting at a ridge along the long axis."""
    width = y1 - y0
    length = x1 - x0
    inset = min(width, length) / 2
    cy = (y0 + y1) / 2
    cx = (x0 + x1) / 2
    bm = bmesh.new()
    if length >= width:
        ridge = [bm.verts.new((x0 + inset, cy, z_ridge)), bm.verts.new((x1 - inset, cy, z_ridge))]
    else:
        ridge = [bm.verts.new((cx, y0 + inset, z_ridge)), bm.verts.new((cx, y1 - inset, z_ridge))]
    a = bm.verts.new((x0, y0, z_eave))
    b = bm.verts.new((x1, y0, z_eave))
    c = bm.verts.new((x1, y1, z_eave))
    d = bm.verts.new((x0, y1, z_eave))
    r0, r1 = ridge
    if length >= width:
        bm.faces.new((a, b, r1, r0))
        bm.faces.new((b, c, r1))
        bm.faces.new((c, d, r0, r1))
        bm.faces.new((d, a, r0))
    else:
        bm.faces.new((a, b, r0))
        bm.faces.new((b, c, r1, r0))
        bm.faces.new((c, d, r1))
        bm.faces.new((d, a, r0, r1))
    bm.faces.new((d, c, b, a))  # soffit underneath
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _link(name, bm, mat)
    mod = obj.modifiers.new("Solidify", "SOLIDIFY")
    mod.thickness = thickness
    return obj


def text_mesh(name, body, size, mat, depth=0.02):
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = body
    curve.size = size
    curve.extrude = depth
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    tmp = bpy.data.objects.new(name + "_curve", curve)
    bpy.context.scene.collection.objects.link(tmp)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(tmp.evaluated_get(depsgraph))
    bpy.data.objects.remove(tmp)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    mesh.materials.clear()
    mesh.materials.append(mat)
    return obj


def join(name, objects, uv_scale=1.0):
    """Bakes modifiers and transforms, merges objects into one mesh keeping material slots, adds box UVs."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    combined = bmesh.new()
    slots = []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = bpy.data.meshes.new_from_object(evaluated)
        mesh.transform(obj.matrix_world)
        remap = []
        for mat in mesh.materials:
            if mat not in slots:
                slots.append(mat)
            remap.append(slots.index(mat))
        for poly in mesh.polygons:
            poly.material_index = remap[poly.material_index] if remap else 0
        combined.from_mesh(mesh)
        bpy.data.meshes.remove(mesh)
    for obj in objects:
        bpy.data.objects.remove(obj)

    uv = combined.loops.layers.uv.verify()
    for face in combined.faces:
        n = face.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        for loop in face.loops:
            co = loop.vert.co
            if az >= ax and az >= ay:
                loop[uv].uv = (co.x / uv_scale, co.y / uv_scale)
            elif ax >= ay:
                loop[uv].uv = (co.y / uv_scale, co.z / uv_scale)
            else:
                loop[uv].uv = (co.x / uv_scale, co.z / uv_scale)

    mesh = bpy.data.meshes.new(name)
    combined.to_mesh(mesh)
    combined.free()
    for mat in slots:
        mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def export_fbx(path, objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.fbx(
        filepath=path,
        use_selection=True,
        object_types={"MESH"},
        apply_scale_options="FBX_SCALE_UNITS",
        mesh_smooth_type="FACE",
        use_mesh_modifiers=True,
        add_leaf_bones=False,
        bake_anim=False,
        path_mode="COPY",
    )


def preview_render(path, target, distance, height, yaw_degrees, ground_size=60.0, resolution=(1280, 720), lens=40):
    """Cycles render with sun, sky and a grass ground plane. The helpers added here are removed afterwards."""
    scene = bpy.context.scene
    added = []

    ground = box("PreviewGround", -ground_size, ground_size, -ground_size, ground_size, -0.05, 0.0,
                 material("PreviewGrass", (0.07, 0.2, 0.035), 0.9))
    added.append(ground)

    sun_data = bpy.data.lights.new("PreviewSun", "SUN")
    sun_data.energy = 4.0
    sun_data.angle = math.radians(2.0)
    sun = bpy.data.objects.new("PreviewSun", sun_data)
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    scene.collection.objects.link(sun)
    added.append(sun)

    world = bpy.data.worlds.new("PreviewSky")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.45, 0.62, 0.9, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    scene.world = world

    cam_data = bpy.data.cameras.new("PreviewCamera")
    cam_data.lens = lens
    cam = bpy.data.objects.new("PreviewCamera", cam_data)
    yaw = math.radians(yaw_degrees)
    target = Vector(target)
    cam.location = target + Vector((math.cos(yaw) * distance, math.sin(yaw) * distance, height))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(cam)
    scene.camera = cam
    added.append(cam)

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)

    for obj in added:
        bpy.data.objects.remove(obj)
