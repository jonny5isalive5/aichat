# Golfer

**The player is now the Meshy "Eccentric Golfer"** (`Meshy_Eccentric_Golfer/`, the owner's Meshy export).
`Art/Blender/build_eccentric_golfer.py` turns it into `Eccentric/Golfer.fbx` (about 171 cm, 32k triangles,
Mixamo bone names) and retargets every clip listed below onto him (`Eccentric/Animations/`).
`Scripts/import_golfer.py` imports those to `/Game/Characters/Eccentric`, which `AGolfCharacter` loads; the game
scales the body to `GolferHeight` (180 cm). The old Tripo golfer below is kept as the source of the clips.

# Golfer

The owner's golfer: a Tripo-generated model, rigged in Mixamo (33-bone `mixamorig` skeleton, no finger
bones), with golf animations downloaded from Mixamo on that same character.

| File | Use in game |
|---|---|
| `Golfer.fbx` | Body (Mixamo "With Skin"). About 95 cm tall as rigged; `AGolfCharacter::GolferScale` 1.9 makes it about 180 cm. |
| `Golf Drive` | Swing for woods and long irons (impact at 1.67 s) |
| `Golf Chip` | Swing for wedges, launch angle 28 degrees or more (impact at 1.77 s) |
| `Golf Putt` | Putter (impact at 0.60 s) |
| `Golf Putt Victory`, `Silly Dancing celebrate`, `Hokey Pokey hole in one` | Holed putt, chip-in, hole in one |
| `Golf Putt Failure missed putt`, `Golf Bad Shot` | Putt stopping within 3 m, water or out of bounds |
| `Golf Drive alt1`, `Golf Drive Setup`, `Golf Tee Up`, `Golf Chip (replay…)`, `Silly Dancing celebrate alt1`, `Golf Putt Victory on long putt`, `Entering Car`, `Exiting Car` | Imported for later use (variety, tee-up, buggy) |
| `Idle`, `Walking` | Downloaded on a different Mixamo character (65 bones). Re-download on the golfer, then run `import_golfer(include_idle_walk=True)`. |

Impact times were measured from the clips (the right hand's fastest point near the bottom of the swing).
The first frame of each swing is used as the address pose while the player aims.

Clubs: `Art/Blender/build_clubs.py` makes `SM_Club_Iron` (full shots and chips) and `SM_Club_Putter`.
At address the game stands the club head behind the ball, points the shaft at the hands and fixes it to
the right hand, so it follows the swing.

Buggy: `Entering Car` starts about 1.9 m left of the driver's seat facing the buggy and ends seated;
`Exiting Car` is the reverse. Both play at 1.5x speed.

Import into Unreal: run `Scripts/import_golfer.py` in the editor. It creates `/Game/Characters/Golfer/SK_Golfer`
(with skeleton and physics asset) and `/Game/Characters/Golfer/Animations/A_*`, which `AGolfCharacter` loads.
