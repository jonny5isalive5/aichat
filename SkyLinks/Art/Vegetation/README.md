# Small broadleaf tree sample

Source: [Tree Small 02](https://polyhaven.com/a/tree_small_02), Rico Cilliers / Poly Haven, [CC0](https://polyhaven.com/license).

`provenance.json` records source download URLs, original MD5/size, and SHA-256 of the texture files. The original 1K Blend is downloaded separately; its MD5 is `d602d9e4df77457454ac427fd37d0b53`. Place its associated files in a sibling `textures/` directory with their original names.

Run only in a fresh background Blender process:

```text
blender --background --disable-autoexec <download-folder>/tree_small_02_1k.blend --python Art/Blender/prepare_small_tree.py
```

The conversion selects the source LOD1, reduces 495,533 triangles to approximately 60,000, preserves UV/material slots, and exports `SM_SmallTree.fbx` plus a rendered preview. Source dimensions are about 2.93 x 4.30 x 4.58 metres. Slots: branches, masked leaves, trunk. The texture set contains DirectX normal maps for Unreal; the Blender preview uses the source OpenGL normals.

This is a visual review sample, not final mobile performance acceptance. All Unreal materials and collision must retain `PM_Rough`. Do not run the whole-course blockout script to place it; that would clear existing course content.

## Current imported sample

`/Game/Course/Vegetation/SmallTree/SM_SmallTree` and its ten textures are imported. The three materials in `/Game/Generated_Materials/M_SkyLinksTree{Branch,Leaf,Trunk}` have `PM_Rough`, as do the mesh body and review actor. The leaf material is masked and two-sided, with a 0.4 mask threshold. Three LODs use reduction fractions 1.0 / 0.4 / 0.12.

Exactly one `ArtReview_SmallTree` is placed in `Course/ArtReview` at `(2500, -2500, 30.998)`, yaw 35, scale 2.4. Placeholder trees remain. Collision currently uses complex-as-simple for this sample; replace it with suitable simple trunk collision before bulk placement/mobile acceptance.

The first in-engine background render is **not visually accepted**: the foliage appears too pale. Imported slot names, base-colour/normal/roughness/alpha bindings and texture compression have been checked. Lighting/foliage appearance still needs refinement and review before replacing the course's placeholders.

`Scripts/import_small_tree.py` imports mesh/textures only. Material graphs were built through Aura's native material tool. `Scripts/finish_small_tree.py` documents the final assignment/placement step; it deliberately refuses to create a duplicate review actor.
