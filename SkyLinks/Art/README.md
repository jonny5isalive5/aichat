# Art

Models are built with Python in Blender, so they can be changed by editing numbers and re-running.

| Model | Script | Exports |
|---|---|---|
| Golf buggy (2-seat electric cart, 2.45 m) | `Blender/build_buggy.py` | `SM_Buggy_Body.fbx`, `SM_Buggy_Wheel.fbx`, `Buggy.blend`, `Buggy_preview.png` |
| Clubhouse (two-storey colonial, pro shop wing, deck) | `Blender/build_clubhouse.py` | `SM_Clubhouse.fbx` (with `UCX_` collision), `Clubhouse.blend`, `Clubhouse_preview.png` |

The exports in `Exports/` are already built, so you only need Blender to change the models.

## Rebuilding in Blender (4.2 or newer)

1. Open Blender and switch to the **Scripting** tab.
2. Click **Open** and pick `Art/Blender/build_buggy.py` (or `build_clubhouse.py`). Keep `sl_common.py` in the same folder.
3. Click **Run Script** (▶). It replaces the current scene, then writes the FBX, `.blend` and preview render into `Art/Exports`.

Or run it without opening Blender:
```
blender --background --python Art/Blender/build_buggy.py
```

## Getting them into Unreal

`Scripts/build_blockout_course.py` imports anything in `Art/Exports` that isn't in the project yet:

- The buggy goes to `/Game/Vehicles/Buggy`, which is where the game's buggy looks for its meshes.
- The clubhouse goes to `/Game/Course/Buildings` and is placed beside the first tee.

To re-import after changing a model, delete the old asset in the Content Browser and run the course script again.

## Conventions

- Size is real, in metres. Front is +X and up is +Z, so models face +X in Unreal.
- The buggy body's origin is on the ground between the axles. The wheel's origin is its hub, with the axle along Y.
- UVs are box-projected at 1 unit per metre (2 m for the clubhouse), so tiling textures from Fab or Megascans fit without unwrapping.
- Each material slot has a plain realistic colour. Swap in textured materials in Unreal and keep the slots.
