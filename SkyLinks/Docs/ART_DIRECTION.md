# Art direction: realistic golf sim

The game's thesis is **SkyLinks — Keeping Friends Connected**. See [GAME_VISION.md](GAME_VISION.md) for the social experience that the art, interface and multiplayer features support.

Sky Links aims for a realistic golf-sim look: real turf, real trees, natural light, and a broadcast-style HUD.
The code is already set up for it: regulation cup and flag, a real-size ball, Lumen lighting and virtual shadows on PC, and fully dynamic lighting (so there's never a "lighting needs to be rebuilt" message).
What's left is art, and that's editor work, which suits Aura.

## Who does what

| Job | Tool |
|---|---|
| Rules, physics, controls, HUD, multiplayer | C++ in `Source/SkyLinks` (Claude) |
| Terrain, turf and sand materials, trees, water, golfer model, lighting mood | Unreal Editor (you + Aura) |
| Blockout layout of the 18 holes | `Scripts/build_blockout_course.py` |

## The one rule the art must keep

The ball reads the **surface type** from each surface's **physical material**. Fairway, rough, green, bunker and water each behave differently: how the ball bounces and rolls, the power penalty from rough and sand, and the water penalty.
Whatever you replace, keep each surface's physical material:

| Surface | Physical material (in `/Game/Course/Materials`) |
|---|---|
| Fairway, tee box | `PM_Fairway` |
| Rough, trees, everything else | `PM_Rough` |
| Green | `PM_Green` |
| Bunker | `PM_Bunker` |
| Water | `PM_Water` |
| Out of bounds | `PM_OutOfBounds` |

On a Landscape, give each paint layer its physical material with a **Landscape Physical Material Output** node, and the ball will read the paint.

## Steps, in order

### 1. Real trees (quick win)
1. Download free trees on Fab (search "Megascans trees", e.g. European Beech, Scots Pine, Black Alder) and add them to the project.
2. Import and inspect one review tree, keeping `PM_Rough` on its materials and collision.
3. Replace placeholder trees incrementally at their existing locations after visual review. **Do not rerun `Scripts/build_blockout_course.py` on the current course: it clears and rebuilds the map, destroying the completed terrain work.**

### 2. Terrain
The blockout is flat boxes. A real course needs a **Landscape** with gentle slopes: fairways that roll, greens with break.
The ball physics already handles slopes, and the putting grid shows them (white is flat, amber is a few percent, red is steep).
Sculpt the landscape under each hole, then paint Fairway, Rough, Green and Bunker layers following the blockout, then delete the blockout slabs.
Keep greens between 0.5% and 3% slope; steeper greens become unputtable at real stimp speeds.

### 3. Turf and sand
Use a Landscape material with the Megascans grass surfaces (e.g. "Short Grass", "Lawn"). Add:
- mowing stripes on fairways (a world-aligned stripe mask that changes value slightly),
- a finer, lighter cut on greens and a fringe band around them,
- raked sand with a lip for bunkers.

### 4. Water
Use the **Water** plugin (lakes and rivers) or a simple translucent material. Keep a collision surface with `PM_Water` at water level so the ball still finds the hazard.

### 5. The golfer
Add the **Third Person** content pack (**Add → Add Feature or Content Pack**) to get the Manny/Quinn mannequin. Then:
1. Make a Blueprint child of `GolfCharacter`, set its mesh to `SKM_Manny` and its animation class to the mannequin's anim blueprint.
2. Get a golf swing animation (Mixamo "Golf Drive", or a mocap pack from Fab), retarget it to Manny with IK Retargeter, and make an Anim Montage. Set it as `SwingMontage`.
3. Set that Blueprint as the Default Pawn Class in a Blueprint child of `GolfGameMode`, and set that as the level's GameMode Override.
The grey placeholder cylinder hides itself automatically once the mesh is set.

### 6. Light and atmosphere
The course script adds a sun, sky atmosphere, volumetric clouds, sky light and height fog. For a morning or late-afternoon look, lower the sun's pitch to −20° and warm its colour a little.
Leave auto-exposure off (already off in `DefaultEngine.ini`).

### Phones
Lumen and virtual shadows only run on PC and consoles; phones use the mobile renderer. For phones, bake distant trees into impostors (Fab "Impostor Baker"), keep Nanite off for foliage, and test on a real device early.

## Aura prompts

Paste these into Aura in the Unreal Editor. Each one matches a step above.

1. **Trees:** *"In the Course map, replace every actor whose label starts with TreeCanopy or TreeTrunk with a random mesh from /Game/Megascans/3D_Plants, keep the location, randomise yaw and scale between 0.85 and 1.25, and delete the originals."*
2. **Terrain:** *"Create a Landscape under the actors in the outliner folder Course/Hole01, 600 by 150 metres, with gentle rolling height variation of about 2 metres, and flatten it where the GolfHole01 tee is."*
3. **Layers:** *"Create a landscape material with layers Fairway, Rough, Green and Bunker using Megascans grass and sand textures, and add a Landscape Physical Material Output node mapping them to PM_Fairway, PM_Rough, PM_Green and PM_Bunker in /Game/Course/Materials."*
4. **Stripes:** *"Add alternating mowing stripes, 6 metres wide, to the Fairway layer of the landscape material, varying brightness by 8 percent."*
5. **Golfer:** *"Create a Blueprint child of GolfCharacter called BP_Golfer using SKM_Manny and ABP_Manny, retarget my golf swing animation to Manny, make it a montage and assign it to SwingMontage. Then make BP_GolfGameMode from GolfGameMode with BP_Golfer as Default Pawn Class and set it as the Course map's GameMode Override."*
6. **Water:** *"Replace every actor labelled Water in the Course map with a Water Body Lake of the same size, and add a flat invisible box at water level using PM_Water so the ball detects it."*

Check anything Aura generates against the class and property names in `Source/SkyLinks/Public`, and keep the physical materials in the table above.
