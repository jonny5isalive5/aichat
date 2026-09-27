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

Import into Unreal: run `Scripts/import_golfer.py` in the editor. It creates `/Game/Characters/Golfer/SK_Golfer`
(with skeleton and physics asset) and `/Game/Characters/Golfer/Animations/A_*`, which `AGolfCharacter` loads.
