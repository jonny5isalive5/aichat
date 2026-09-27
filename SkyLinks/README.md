# Sky Links

An 18-hole golf sim for phones in landscape, for 1–4 players, built in Unreal Engine 5.8 with C++.
The target look is realistic: real turf and trees, natural light, a broadcast-style HUD, and a camera that sits behind the golfer and then follows the ball in flight.

## What's here

| Part | File | What it does |
|---|---|---|
| Ball physics | `GolfPhysics.*`, `GolfBall.*` | Drag, Magnus lift from back/side spin, wind, bounces and rolling that depend on the surface, slopes, cup capture and lip-outs. Runs at a fixed 120 Hz so every device plays out the same flight. |
| Ball camera | `GolfBall.*` | After impact, every player's view cuts to a chase camera that follows the ball from behind. It turns smoothly to stay behind the ball's direction of travel and tilts down once the ball starts rolling. |
| Golfer camera | `GolfCharacter.*` | Before the shot the camera sits low behind the ball looking down the aim line, with the golfer on the left of the frame, as in the reference shot. |
| Rules | `GolfGameMode.*` | Stroke play for up to 4 players. The player with honors tees off first and after that the player farthest from the cup plays. Water or out of bounds costs 1 stroke and you replay from the previous spot. You pick up at double par. The mode handles the hole summary, all 18 holes and the winner. |
| Controls | `GolfPlayerController.*` | Drag the top half of the screen to aim. Swipe up from the bottom half to swing: swipe length sets the distance (the landing ring follows your finger), sideways drift hooks or slices, and lifting your finger hits. There's a club disc, backspin and topspin, and automatic club choice. When putting, an aim line follows the ground and a grid shows which way the green slopes. |
| HUD | `GolfHUD.*` | Drawn straight to the screen, so no UI assets are needed. Hole card, player list, wind compass, club disc, swipe power meter, shot preview, green-reading grid, scorecard (birdies circled, bogeys boxed) and the lobby. |
| Playing with friends | `GolfSessionSubsystem.*` | 4-digit **room codes** with an on-screen keypad, **friend invites** with a join pop-up, and direct IP. It works on the same Wi-Fi out of the box and anywhere once Epic Online Services is set up (see `Docs/MULTIPLAYER.md`). |
| Golf buggies | `GolfBuggy.*` | Every player has a buggy. It parks beside the tee at the start of each hole, and when your ball is more than 30 m away your turn starts with a drive to it. Drag on the left to steer, hold GO/REV, then tap PLAY SHOT within 15 m, or SKIP to go straight there. It follows slopes, stops at trees, buildings and water, and syncs smoothly for everyone watching. |
| Course | `Scripts/build_blockout_course.py` | Builds all 18 holes (par 70) as a playable blockout with surface-tagged materials, imports the Blender models and places the clubhouse. |
| 3D models | `Art/` | The clubhouse and golf buggy, built by Python scripts in Blender. The FBX exports are ready to import (see `Art/README.md`). |

## Getting it running

1. Install **Unreal Engine 5.5** and Visual Studio 2022 (Windows) or Xcode (Mac) with the C++ game workload.
2. Right-click `SkyLinks.uproject` and choose **Generate Visual Studio project files**, then build the `SkyLinksEditor` target, or just open the `.uproject` and let it compile.
3. In the editor, go to **Tools → Execute Python Script** and pick `Scripts/build_blockout_course.py`.
   It creates `/Game/Maps/Course` with all 18 holes and saves it.
4. Press **Play**. Choose **SOLO**, or **HOST** to get a room code friends can **JOIN** with. To test multiplayer on one PC, use **Play → Number of Players: 2** and **Net Mode: Play As Listen Server**. The host taps **TEE OFF**.

Controls in the editor: the mouse acts as a finger. Keyboard: hold **Space** to charge and release to hit, **A/D** aim (or steer), **W/S** drive, **F** play shot from the buggy, **Q/E** change club, **R** changes spin.

## Shipping to phones

The project is already configured for landscape only on Android and iOS, mobile rendering, and a package name/bundle ID (`com.skylinks.golf`).
Use **Platforms → Android → Package Project**. Your machine needs the Android SDK/NDK that UE 5.5 expects, which you install with `SetupAndroid.bat` from the engine.

## Making it look real

The blockout is flat colour. `Docs/ART_DIRECTION.md` covers the realistic art pass: real trees (the course script can place them for you), terrain, turf, water, the golfer model and swing, and ready-to-paste prompts for Aura in the editor.

## Status

Nobody has compiled or play-tested this yet. It was written without an Unreal install, so expect a round of compile fixes on the first build.
Ball distances also need tuning in play: the club speeds in `GolfPhysics.cpp` are a starting point.
