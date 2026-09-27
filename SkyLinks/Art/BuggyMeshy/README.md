# Owner's Meshy golf buggy

Supplied 27 September 2026 as `Meshy_AI_high_detail_4_man_gol_0927165639_texture_fbx.zip`.
Original archive preserved in `Source/`. The owner's Meshy screenshot specifies CC BY 4.0. Attribution: golf buggy generated with Meshy (https://www.meshy.ai/), supplied by the project owner; optimized for SkyLinks. Retain attribution with distributions.

## Prepared assets

- `SM_MeshyBuggy_Review.fbx`: UV-mapped static review mesh, reduced from 511,022 to 45,000 triangles.
- `Buggy_Review.blend`: editable reduced mesh with connected base-colour, roughness, metallic and tangent normal maps.
- `T_Buggy_*.png`: source PBR textures, copied without resampling.
- `Buggy_review.png`: background Blender render, not Unreal gameplay evidence.
- `mesh-report.json`: input hashes, counts and provisional dimensions.

Reproduce in a fresh background Blender process with `--factory-startup --threads 2 --disable-autoexec --python Art/Blender/prepare_meshy_buggy.py -- <extracted-source-directory>`.

## Installed runtime assets

`GameParts/` contains the separated body and hub-centred wheel used by the existing GolfBuggy actor. The actor's existing mesh paths `/Game/Vehicles/Buggy/SM_Buggy_Body` and `SM_Buggy_Wheel` have been replaced, so newly spawned gameplay buggies load the Meshy art without code changes. Previous meshes are recoverable from commit `8164e62`. No humanoid rig is needed.

The source was fused geometry. `install_meshy_buggy_parts.py` extracts wheels spatially while retaining UVs, repeats the rear wheel, turns the body to +X forward and adapts it to the existing 165cm wheelbase, 92cm track and 23cm tyre radius. LOD0 totals 44,981 triangles (24,533 body plus four 5,112-triangle wheels). The full 3.2m review mesh above remains preserved separately.

Unreal assets have three LODs, simple box collision for static uses, and PM_Rough on their body setups and new PBR material `/Game/Generated_Materials/M_MeshyBuggy`. Driving continues to use the existing pawn collision box, wheel animation and replication. Textures live in `/Game/Vehicles/MeshyBuggy` with sRGB disabled on roughness, metallic and normal maps.

The windshield has a separate `M_MeshyBuggyGlass` slot and two-sided translucent material (opacity 0.12, roughness 0.08, refraction 1.0). The frame/body stay opaque. Headless Unreal renders verified visibility through it from an exterior camera and a driver-eye viewpoint. This prepares the artwork for an interior view; it does not add a first-person camera toggle.

A transient instance of the actual GolfBuggy class verified all five runtime parts, wheel positions, material bindings and PM_Rough. The Course file SHA-256 stayed `DBD1734F895D002993BD1723967B68F4DC381F291649FFCF260D4A7CA81A3F9C`. Driving/replication code was unchanged; no interactive PIE session was started.

`Scripts/import_meshy_buggy.py` imports textures; use Aura's native material tool to connect BaseColor, Normal, Roughness and Metallic to M_MeshyBuggy before running `Scripts/install_meshy_buggy.py`. The installation does not rebuild or save Course. Four passenger seats are not implemented by the existing one-driver-per-buggy game; this asset installation does not add passenger networking. Interactive driving and multiplayer acceptance of the new artwork still need a user-coordinated test window.
