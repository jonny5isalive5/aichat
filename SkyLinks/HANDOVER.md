# Sky Links: project handover

> **Latest checkpoint:** Read [CURRENT_CHECKPOINT_2026-09-27.md](Docs/CURRENT_CHECKPOINT_2026-09-27.md) for the current pushed work, the provisional tree, unresolved headless physical-material trace results and the owner's desktop-control boundary before continuing.

> **Game thesis:** **SkyLinks — Keeping Friends Connected** is the owner's chosen tagline and guiding purpose. Read [GAME_VISION.md](Docs/GAME_VISION.md). Group voice defaults to open mic, with microphone and individual mute controls; see [VOICE_CHAT.md](Docs/VOICE_CHAT.md) for implementation and the outstanding four-device, EOS and mobile validation.

> **Codex update, 27 September 2026:** Codex now works directly on Boss420 with repository push access and Aura's local MCP bridge. Sections 2, 8 and 9 below describe the earlier cloud handover and are partly superseded. Live inspection found all six landscapes already shaped and layered. The completed terrain pass corrected green slopes, water basins and surface masks and aligned cups/tree bases. See [current verification and next steps](Docs/TERRAIN_STATUS_2026-09-27.md) and [terrain pipeline](Art/Terrain/README.md). Keep this original handover as historical context.

> **Gameplay follow-up:** Session replacement and per-world online services are fixed (`9860703`). LAN room discovery/rehosting, two-player tee shots and turn selection, buggy forward/steering/reverse, mouse swipe, putting guide, slope roll and cup progression have now had controlled smoke tests. Precise short pin distances are fixed (`fd5ca7a`). Read [gameplay evidence](Docs/GAMEPLAY_VERIFICATION_2026-09-27.md) and [multiplayer evidence](Docs/MULTIPLAYER_VERIFICATION_2026-09-27.md) for the limits; mobile touch, EOS/invites and full rounds remain unverified.

Written 27 September 2026 by Claude (Claude Code, cloud session), for whoever takes over the code side (Codex).
It covers where the project is, how the pieces fit, who does what (you, Aura, the owner), where everything lives, and what's next.

---

## 1. The project in one paragraph

**Sky Links** is an 18-hole (par 70) golf sim for phones in landscape, for 1–4 players, built in **Unreal Engine 5.8** with C++. The look is realistic (the owner moved away from an arcade/cartoon style).

Play works like this:
- Players swipe up from the bottom of the screen to swing.
- The camera sits low behind the golfer, then follows the ball from behind in flight.
- Putting shows an aim line laid over the ground and a grid of slope arrows.
- Each player drives their own golf buggy to their ball between shots.
- Friends join with 4-digit room codes, invites, or direct IP.

The code compiles and runs on the owner's PC. Hole play and ball physics have been tested in the editor and work. The buggy, clubhouse, swipe controls and putting guide compile but have **not yet been play-tested**.

---

## 2. People and tools

| Who | Role | Access |
|---|---|---|
| **Owner**: GitHub `jonny5isalive5`, PC `Boss420`, Windows user `mrjph` | Decides direction, runs builds, relays between AIs | Everything on the PC |
| **Code AI** (was Claude, now Codex) | C++, config, Python scripts, Blender scripts, docs | The GitHub repo only. It **cannot** see the PC, the editor or Aura. |
| **Aura** (in-editor AI plugin in Unreal) | Editor work: levels, landscapes, materials, Blueprints, placing assets | Inside the editor. Its file tools can write only `Saved/.Aura/**` and `Config/*.ini`. It **cannot** edit `.uproject`, `Source/`, or run git. |

The owner is the bridge: they paste Aura's reports into the code AI's chat, and the code AI's instructions into Aura.

---

## 3. GitHub

| | |
|---|---|
| Repository | https://github.com/jonny5isalive5/aichat (owner `jonny5isalive5`, repo `aichat`) |
| Working branch | **`claude/admiring-volta-8o59gg`** (everything is here) |
| Other branches | None on GitHub. There's no `main`, so no pull request could be opened. The owner's PC has a local `master` branch from an old reset; ignore it. |
| Game folder in the repo | `SkyLinks/` |
| Also in the repo | `golf/index.html`, an early single-file 2D browser prototype ("Pocket Links"), no longer used. The root `README.md` points at both. |
| Big files | None over 50 MB. `Content/Maps/Course.umap` is about 26 MB. Git LFS is not set up; consider it if maps grow past about 50 MB. |

### Git workflow (the owner uses Git Bash on the PC)

The PC folder is a git clone tracking the working branch. The pager is disabled (`core.pager cat`), and user.name/email are set.

- **The code AI pushes changes.** The owner then runs `git pull` in Git Bash and rebuilds if C++ changed.
- **The owner or Aura changes things in the editor.** The owner closes the editor, then runs `git add -A`, `git commit -m "…"` and `git push`, and tells the code AI "pushed".
- **Conflicts:** they've happened on `SkyLinks.uproject`. Keep the repo version (`git checkout --theirs <file>` during a merge), because PowerShell once reformatted that file badly.
- **`.gitignore`** (in `SkyLinks/`): `Binaries/ Intermediate/ Saved/ DerivedDataCache/ .vs/ .idea/ *.sln *.slnx *.suo *.xcworkspace *.blend1 __pycache__/`. **`Saved/` is ignored.** Aura's files there need `git add -f` to be shared.

---

## 4. Locations on the owner's PC (Boss420)

| What | Path |
|---|---|
| Git clone (repo root) | `C:\Projects\aichat-claude-admiring-volta-8o59gg\` |
| Unreal project folder | `C:\Projects\aichat-claude-admiring-volta-8o59gg\SkyLinks\` |
| Project file | `C:\Projects\aichat-claude-admiring-volta-8o59gg\SkyLinks\SkyLinks.uproject` |
| Game content (maps, assets) | `…\SkyLinks\Content\` |
| Aura's workspace | `…\SkyLinks\Saved\.Aura\` |
| Aura terrain exports (not pushed yet) | `…\SkyLinks\Saved\terrain\heightmaps\raw\Terrain_Hole01..06.raw` + `meta.json` |
| Editor logs | `…\SkyLinks\Saved\Logs\SkyLinks.log` |
| Unreal Engine 5.8 | `C:\Program Files\Epic Games\UE_5.8\` |
| Build tool log | `C:\Users\mrjph\AppData\Local\UnrealBuildTool\Log.txt` |
| Compiler | Visual Studio **18** Build Tools, MSVC 14.51 (`C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\`). UE warns it's newer than preferred; it works. |
| Windows SDK | 10.0.26100.0 |

In Git Bash the same clone is `/c/Projects/aichat-claude-admiring-volta-8o59gg`.

### Build command (PowerShell)
```powershell
& "C:\Program Files\Epic Games\UE_5.8\Engine\Build\BatchFiles\Build.bat" SkyLinksEditor Win64 Development "-Project=C:\Projects\aichat-claude-admiring-volta-8o59gg\SkyLinks\SkyLinks.uproject" -WaitMutex
```
PowerShell needs the leading `&`. The last build **succeeded** with all current code.

---

## 5. Engine and build gotchas (learned the hard way)

- **UE 5.8** is installed, although the code was first written for 5.5. The targets use `BuildSettingsVersion.V7` and `EngineIncludeOrderVersion.Latest`, and the `.uproject` says `"EngineAssociation": "5.8"`.
- **Warning C4458/C4456/C4457 (a variable name hiding another) is a build error in 5.8.** Never name a local or parameter after a member of a base class. Names that already bit: `Score` (APlayerState), `Player` (APlayerController), and parameter names matching your own members (this also applies to RPC parameters, because UHT copies them into `.gen.cpp`). Names like `Location`, `Rotation` and `Controller` as parameters are fine in the current code.
- An engine deprecation warning, `APawn::GetMovementBase` from `Character.h`, is harmless and not ours.
- **Plugins** in the `.uproject`: EnhancedInput, OnlineSubsystem, OnlineSubsystemNull, OnlineSubsystemEOS, EOSShared, OnlineSubsystemUtils, PythonScriptPlugin, EditorScriptingUtilities, and Aura (Win64/Mac only).
- `Config/DefaultEngine.ini` contains an editor-generated Android File Server section. Keep `SecurityToken=` blank in git; the editor fills it locally.

---

## 6. Code map (`SkyLinks/Source/SkyLinks`)

| File | Purpose |
|---|---|
| `SkyLinks.h/.cpp` | Module, log category, trace channel `ECC_GolfBall` (= GameTraceChannel1), surface type macros (`SURFACE_Fairway` = SurfaceType1, Rough 2, Bunker 3, Green 4, Water 5, OutOfBounds 6) |
| `GolfTypes.h` | Enums (`EGolfLie`, `EGolfShotResult`, `EGolfMatchPhase`), `FGolfClub`, `FGolfShotInput` |
| `GolfPhysics.h/.cpp` | Deterministic ball physics at a fixed 120 Hz: drag, Magnus lift from spin, wind, surface table (restitution, friction, roll decel, power scale), club bag (1W 3W 5I 7I 9I PW SW PT), launch from input, sweep helper, carry prediction, flat carry, putt distance |
| `GolfBall.h/.cpp` | Ball actor. The server multicasts the launch; every machine simulates locally (flight, bounce, roll, cup capture, lip-out); the server's rest position is authoritative. Includes the **chase camera** (spring arm that turns to stay behind the ball's travel direction). `VisualScale` = 1 (real size). |
| `GolfHole.h/.cpp` | One per hole, placed in the level: tee = actor origin, `CupRoot` component, par, name, cup radius (5.4 cm, regulation), max wind, `AimPoint` for doglegs, flag and cup meshes |
| `GolfCharacter.h/.cpp` | The golfer. Stands at the ball; low camera behind the ball with the golfer on the left of frame. Placeholder cylinder until a skeletal mesh is assigned. `SwingMontage` slot. Movement disabled; position derived from the replicated ball location and aim. |
| `GolfBuggy.h/.cpp` | Drivable cart pawn. Bicycle-model steering, 4-wheel ground traces (WorldStatic), stops at water, blocked by trees and buildings, chase camera, wheel spin and steer. The driver simulates it and sends `ServerSyncMove` at 20 Hz; other machines interpolate. Loads meshes from `/Game/Vehicles/Buggy/SM_Buggy_Body` and `SM_Buggy_Wheel` (soft paths), falling back to engine shapes. `BodyYawOffset` exists in case the import faces the wrong way. |
| `GolfPlayerState.h/.cpp` | Per-player: `HoleScores[]`, `Strokes`, `bHoledOut`, `bInRound`, `Ball`, `Golfer`, `Buggy` (all replicated), plus server-only last-shot info |
| `GolfGameState.h/.cpp` | Phase, hole index, current hole, active player, `bActiveDriving`, wind, pars, hole names, `RoomCode`, multicast announcements |
| `GolfGameMode.h/.cpp` | Server rules. Stroke play; honors on the tee, then farthest from the cup plays. Water/OB: +1 and replay. Pick up at double par. Hole summary then the next hole. Buggies park beside each tee; a turn starts with a **drive** if the buggy is more than 30 m from the ball (`FinishDriving` within 15 m, or skip). Possession switches between golfer and buggy. |
| `GolfPlayerController.h/.cpp` | Multi-touch input with per-finger roles. **Aim:** drag the top half. **Swing:** swipe up from the bottom half; swipe length sets power (45 % of screen height = full), sideways drift sets hook or slice. **Drive:** drag the left half to steer, hold GO/REV. Club cycle, spin presets, auto club choice, shot preview (carry arc or draped putt line), green slope grid, lobby keypad and friends. Keyboard: Space charge and hit, A/D aim or steer, W/S drive, F play shot, Q/E club, R spin. |
| `GolfHUD.h/.cpp` | Everything drawn on the Canvas (no UMG assets): hole card, players, wind dial, lie, club disc, swipe power meter, preview, green grid, driving HUD (compass to ball, steer pad, pedals, PLAY SHOT/SKIP), scorecard (birdies circled, bogeys boxed), lobby (SOLO/HOST/JOIN, room code, keypad, friends, invite pop-up). All sizes are in units of 1 % of screen height. `HitTest()` feeds touch buttons. |
| `GolfSessionSubsystem.h/.cpp` | Online Subsystem sessions: host (4 players, 4-digit room code in session settings), join by code, friends list and invites (EOS), sign-in (persistentauth, then accountportal). Default platform is Null (LAN). |

Config: `DefaultEngine.ini` (default map `/Game/Maps/Course`, game mode, surface types, the GolfBall trace channel, Null OSS, mobile renderer settings, dynamic lighting with Lumen and VSM on PC, landscape-only on Android/iOS); `DefaultInput.ini` (mouse acts as touch); `DefaultGame.ini` (MaxPlayers 4).

---

## 7. Content pipeline

### Course: `SkyLinks/Scripts/build_blockout_course.py` (run in the editor)
- Defines all **18 holes** (par 70) as metre coordinates: fairway rectangles, green centre and radius, bunkers, water, trees, aim point. Front nine in a row at X = 0; back nine at X = 800 m. Holes are 350 m apart in Y.
- Creates the physical materials `PM_*` and flat-colour materials `M_*` in `/Game/Course/Materials`.
- Builds each hole from thin boxes and cylinders. Surface heights: rough 0, water 0.4, fairway 0.8, tee 1.0, green 1.2, bunker 1.6 cm.
- Spawns `GolfHole` actors, trees (real meshes if `TREE_MESHES` is filled in, otherwise stand-ins), tee boxes, sun, sky, clouds and fog.
- **Imports** `Art/Exports/*.fbx` into `/Game/Vehicles/Buggy` and `/Game/Course/Buildings` if missing, then places the clubhouse at (−110 m, −45 m) from hole 1's tee, yaw −90.
- It has been run on the PC; `/Game/Maps/Course` exists and is committed.

### 3D models: `SkyLinks/Art/`
- `Blender/sl_common.py`, `build_buggy.py` and `build_clubhouse.py` are procedural Blender 4.2+ scripts. They run inside Blender or headless (`blender --background --python …`).
- They write to `Art/Exports`:
  - FBX: `SM_Buggy_Body`, `SM_Buggy_Wheel`, `SM_Clubhouse` (the clubhouse includes `UCX_` collision)
  - `.blend` source files
  - preview PNGs
- Conventions: metres, +X forward, +Z up, box-projected UVs.
- Both are imported on the PC (visible in `Content/Vehicles/Buggy` and `Content/Course/Buildings`).

### The rule every art change must keep
The ball reads the **surface type from each surface's physical material**. Any replacement surface (landscape layers included) must map to `PM_Fairway`, `PM_Rough`, `PM_Green`, `PM_Bunker`, `PM_Water` or `PM_OutOfBounds`. On landscapes that's done with a **Landscape Physical Material Output** node. Without it, the ball treats everything as rough.

---

## 8. What Aura has done so far (from its own reports)

- Ran the course script, which created `/Game/Maps/Course` with 18 holes, and imported the buggy and clubhouse.
- **Landscapes:** created `Terrain_Hole01` … `Terrain_Hole06` (11:01–12:27 on 27 Sep).
- **Paint layers on hole 1 only:** set up 4 layers (Fairway, Green, Bunker, Rough) with the material `M_Hole01_Landscape` (weightmaps `T_Hole01_*`, layer infos `LI_*`). Holes 2–6 have **no layers**, and MapCheck reports stale landscape material instances on Hole02.
- **Terrain shaping stalled.** It exported heightmaps to `Saved/terrain/heightmaps/raw/Terrain_Hole01..06.raw` + `meta.json` (grid W/H, x0/y0, sx/sy per hole), but **never called `update_landscape_heightmap`**. All six landscapes are still flat, with no plan or checkpoint file.
- **Water:** 13 water actors, all at Z −9.6 (box 20 cm thick, so the top is at 0.4 cm, matching the script). Hole02 `Water0` at (8500, 39000), extents (3000, 2000, 10), is saved.
- **Unknown:** whether `M_Hole01_Landscape` has a Landscape Physical Material Output node. Ask Aura, or test by playing hole 1 and watching the lie label.
- **Unknown:** how the landscapes sit relative to the blockout slabs (under them, or replacing them). Ask Aura.

---

## 9. Next steps, in priority order

1. **Finish terrain for holes 1–6.** This is where Claude left off.
   - Get Aura's exports into git: `git add -f SkyLinks/Saved/terrain` and push.
   - Ask Aura the raw format (bit depth, endianness, row order), the raw-to-world-Z mapping per landscape (actor Z and Z scale), and the input format `update_landscape_heightmap` expects.
   - Generate shaped heightmaps from the hole layouts in `build_blockout_course.py`:
     - flat tees,
     - gentle fairway roll,
     - greens with 1–2 % slope (no more than 3 %),
     - bunkers 20–40 cm below grade,
     - banks falling into the water.

     Match Aura's grid exactly.
   - Push them, and have Aura apply them with `update_landscape_heightmap`.
2. **Paint layers on holes 2–6,** like hole 1, then re-save the map to clear the Hole02 material-instance warning. Confirm the physical material mapping.
3. **Decide what happens to the blockout slabs** under or over the new landscapes: delete or hide the flat fairway, green and bunker slabs where landscape paint takes over. Keep water collision with `PM_Water`.
4. **Play-test the new features:** swipe swing, putting line and slope grid, buggy driving (check it faces forward and is about 250 cm long; the course script logs a warning if the size is wrong), the clubhouse, and 2-player listen server in the editor.
5. **Real trees:** add Megascans tree mesh paths to `TREE_MESHES` in the course script and re-run it, or have Aura swap the `TreeCanopy`/`TreeTrunk` actors.
6. **The golfer:** mannequin plus a golf swing montage as `BP_Golfer` (a Blueprint child of `GolfCharacter`) via a `BP_GolfGameMode`. See `Docs/ART_DIRECTION.md`.
7. **Holes 7–18 terrain,** the same as step 1.
8. **Internet multiplayer:** switch the Online Subsystem to EOS (steps in `Docs/MULTIPLAYER.md`; needs the owner's Epic Developer Portal credentials).
9. **Phone build:** package for Android (landscape is already configured, package `com.skylinks.golf`).

### Known rough edges in the code
- The golfer isn't shown in the buggy while driving (it's hidden).
- Putt preview is a straight draped line. Break is shown only by the slope grid (intended as the skill element).
- Buggy handling and club distances are untuned first guesses (`GolfBuggy.h` handling UPROPERTYs, the club table in `GolfPhysics.cpp`).
- The HUD is Canvas-drawn. A UMG reskin is planned later (`Docs/ART_DIRECTION.md`).

---

## 10. Other docs in the repo
- `SkyLinks/README.md`: overview, setup, controls
- `SkyLinks/Docs/ART_DIRECTION.md`: realistic art plan and Aura prompts
- `SkyLinks/Docs/MULTIPLAYER.md`: room codes, invites, LAN, EOS setup
- `SkyLinks/Art/README.md`: Blender pipeline
