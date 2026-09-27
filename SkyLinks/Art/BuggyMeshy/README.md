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

## Integration remains pending

The imported source is one combined mesh. No humanoid rig was added. The existing GolfBuggy actor animates separate wheel components, so do not replace its body with this complete mesh: that would leave fixed wheels plus duplicate animated wheels.

Separate wheel geometry, establish wheel-centred pivots and +X forward orientation, and fit the body to the existing vehicle dimensions before integration. The current 3.2m length (1.66m wide, 2.10m tall) is provisional. Four usable seat positions have not been verified or authored. Create simple vehicle collision and retain the project's physical-material assignments. Import to a new asset folder first; preserve the current buggy and Course map until the new parts are verified. Final visual, wheel-motion and multiplayer gameplay validation remains outstanding.
