# Holes 1-6 terrain

`Holes01-06/` contains reproducible 16-bit height PNGs, four normalized 8-bit weightmaps per hole, a manifest with SHA-256 hashes, and world-space acceptance probes.

## Regenerate outside Unreal

Requires Python, NumPy and Pillow. From `SkyLinks`:

```powershell
python Scripts/generate_golf_terrain.py
python Scripts/generate_terrain_probes.py
python Scripts/test_golf_terrain.py
```

The generator reads the first six layouts from `Scripts/build_blockout_course.py` without running its editor operations, and preserves the existing grids from `Saved/terrain/heightmaps/raw/meta.json`.

Aura moved hole 2's water to world centre `(8500, 39000)`, with XY half-extents `(3000, 2000)`. An explicit generator override preserves that saved placement rather than moving it back to the older blockout layout.

## Apply in the existing Course editor

Save/back up current work first. Use Aura's `execute_unreal_python` with the contents of `Scripts/apply_golf_terrain.py`, followed by `apply_holes([1])` or another explicit subset of 1-6. The script asserts the map, transforms and layer configuration before each update. It uses Aura's `update_landscape_heightmap`, keeps the existing landscape material and physical-material bindings, imports the four weights, and aligns cups and placeholder tree bases. It does not rebuild the course or change water actors. Aura's normal transaction/auto-save wrapper must surround execution.

Then run `Scripts/validate_golf_terrain.py` plus `validate_holes([1,2,3,4,5,6])` through the read-only Python tool. Inspect the returned error list; tool execution success alone is not a passing result. The 74 positions are tested with simple and complex collision (148 probes), plus six cup-alignment checks.

## Encoding and geometry

PNG columns increase world X; rows increase world Y. Height decoding in centimetres is:

`world_z = (uint16 - 32768) / 128 * 0.4296875 - 0.4296875`

The actor Z and scale Z are deliberately unchanged. No post-import blur is applied. Greens have approximately 1.5% planar slope through a cup height of 30 cm; tees are flat at 0 cm. Bunkers subtract a smooth 30 cm bowl from local grade. Water basin centres are -60 cm under existing water tops at 0.4 cm. Outer terrain edges taper to 0 cm. Adjacent rough/aprons and banks can be steeper than the putting surface.

The native importer refreshes `Saved/terrain/heightmaps/*_source.png` as sidecar copies. Original Aura sources remain in Git commit `7f0d5b2`; `heightmaps/raw/*.raw` remain the original **8-bit** row-major exports, not current 16-bit terrain.

The original handover's claims that all landscapes were flat and only hole 1 had layers were contradicted by live inspection: all six already had terrain variation and four material layers. The actual defects were flat greens, missing water depressions and incorrect rough classification at sampled points on holes 2 and 6.

This is a terrain integration milestone. It does not establish completed multiplayer, production mobile rendering, real vegetation, or a final golfer model. The existing repo has no Ruff/ty/basedpyright check configuration; a Python toolchain migration is deferred from this Unreal content change.
