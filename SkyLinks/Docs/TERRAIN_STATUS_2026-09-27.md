# Terrain status — 27 September 2026

Codex is the implementation lead on Boss420, with local Unreal/Aura access and push access to `claude/admiring-volta-8o59gg`.

## Completed

- Preserved Aura's 48 terrain export files in commit `7f0d5b2` and pushed them before editor edits.
- Audited the actual saved Course map. Contrary to the original handover, all six landscapes already had height variation and four layers. The actual gaps included flat greens, terrain obstructing water, and rough regions classified as fairway.
- Generated and applied deterministic 16-bit heightmaps for holes 1–6, preserving all six landscape transforms and resolutions. Added gentle fairway roll, approximately 1.5% greens, flat tees, smooth 30 cm bunker bowls, and submerged water basins.
- Reimported normalized Fairway/Green/Bunker/Rough masks, retaining the existing physical-material mappings. Preserved Aura's saved hole 2 water position `(8500, 39000, -9.6)` and all water actors.
- Aligned cups to the new greens and re-seated the placeholder trees. No full-course regeneration or slab deletion was needed; the surveyed first-six-hole layouts already used landscapes in place of the old slabs.
- Added generation, application, live validation and offline acceptance scripts under `Scripts/`. See `Art/Terrain/README.md` for exact commands and encoding.

## Verification

- **148 live collision probes passed**: 74 world positions in both simple and complex collision modes, with height tolerance 2 cm and exact expected physical material. Six cup-alignment checks also passed (1 cm tolerance). Full results: `Docs/Verification/terrain-holes01-06.json`.
- Two offline acceptance tests passed: all PNG dimensions, 16-bit height depth and hash integrity; weights sum to 255; tee/green/water constraints. Python source compilation checks passed.
- In standalone PIE, the SOLO Canvas button started hole 1. A keyboard-charged shot registered one stroke, flew, landed on the fairway and triggered the buggy phase. The ball was read at approximately `(27131.87, 897.16, 26.39)` cm; the HUD reported FAIRWAY and 89 m to the pin. This verifies a basic play sequence, not a full-round or physics-tuning pass.
- A native mouse drag did **not** produce a swipe shot in this test. Do not label swipe controls verified; distinguish mouse-for-touch handling from native touchscreen behavior in the next pass.
- Buggy possession and its rendered model were observed. Controlled driving/steering verification remains open: user input was detected during this phase, so automation relinquished the play-window controls. PIE was left running for the owner; the background capture was stopped separately.
- No C++ changes were made and no new C++ build was needed. The repo has no configured Ruff/ty/basedpyright gates; toolchain migration remains outside this content milestone.

## Recovery and evidence

- Original exports and pre-pass tracked content are available at Git commit `7f0d5b2`.
- A separate local pre-pass map copy and hash are under this Codex chat's `work/baseline/`.
- Aura refreshed `Saved/terrain/heightmaps/*_source.png` with the applied 16-bit maps. The old `.raw` exports remain unchanged 8-bit files and must not be read as uint16.
- Live editor materials and probes provide the physical-surface evidence; build success or import status alone was not used as proof.
- Aura's repair helper initially returned a DeepSeek API error; retry succeeded and added undo registration before cup/tree moves. Terrain application completed successfully afterward.
- Local play capture: `Saved/AuraVerify/rec_1790519819845947300_1/recording.h264` with `recording_index.json`. Its wall/game time and video time differ because of capture pacing/dropped stages; use the index rather than treating video duration as simulation time.

## Next work

1. Verify/fix swipe handling with real input; test the putting preview and slope grid on the new greens.
2. Controlled buggy steering/braking/arrival test, then a two-player listen-server test. Room-code/EOS invites remain unverified.
3. Review the new terrain visually with the owner; flat-colour turf, placeholder trees and the cylinder golfer remain provisional art.
4. Real vegetation and golfer/swing assets, then terrain for holes 7–18. Avoid regenerating Course wholesale because the blockout script clears course folders.
5. EOS/internet and mobile packaging follow the original handover; credentials and device acceptance are still required.

Saved Course SHA-256 at checkpoint: `7c9bf69b7f26f4c9f00faa5fee938d2b697b62f684a408e1fdae50bf8c672214`. Last save preceded PIE. A later read-only dirty-package query during active PIE was rejected by Aura as a mutation and reported an automatic revert; it did not change the saved map file (last write remained 15:34:50). Avoid generic read-only Python inspection during active play; prefer Aura's dedicated PIE queries. The 148-probe acceptance pass ran before PIE.
