# Sky Links

An 18-hole arcade golf game for phones in landscape, for 1–4 players, built in Unreal Engine 5.5 with C++.
The target look is bright, stylised fantasy golf: chunky trees, giant mushrooms, a lighthouse on the horizon,
and a chibi golfer standing over the ball with the camera low behind them.

## What's here

| Part | File | What it does |
|---|---|---|
| Ball physics | `GolfPhysics.*`, `GolfBall.*` | Drag, Magnus lift from back/side spin, wind, bounces and rolling that depend on the surface, slopes, cup capture and lip-outs. Runs at a fixed 120 Hz so every device plays out the same flight. |
| Ball camera | `GolfBall.*` | After impact, every player's view cuts to a chase camera that follows the ball from behind. It turns smoothly to stay behind the ball's direction of travel and tilts down once the ball starts rolling. |
| Golfer camera | `GolfCharacter.*` | Before the shot the camera sits low behind the ball looking down the aim line, with the golfer on the left of the frame, as in the reference shot. |
| Rules | `GolfGameMode.*` | Stroke play for up to 4 players. The player with honors tees off first and after that the player farthest from the cup plays. Water or out of bounds costs 1 stroke and you replay from the previous spot. You pick up at double par. The mode handles the hole summary, all 18 holes and the winner. |
| Controls | `GolfPlayerController.*` | Drag to aim. The swing is three taps: start the gauge, set the power (with an overdrive zone past 100%), then time the impact to control slice or hook, with a "Perfect" window. There's a club disc, backspin and topspin, automatic club choice, and a preview arc with a landing ring. |
| HUD | `GolfHUD.*` | Drawn straight to the screen, so no UI assets are needed. Hole card, player list, wind compass, club disc, power gauge, swing button, scorecard (birdies circled, bogeys boxed) and the lobby. |
| Playing with friends | `GolfSessionSubsystem.*` | 4-digit **room codes** with an on-screen keypad, **friend invites** with a join pop-up, and direct IP. It works on the same Wi-Fi out of the box and anywhere once Epic Online Services is set up (see `Docs/MULTIPLAYER.md`). |
| Course | `Scripts/build_blockout_course.py` | Builds all 18 holes (par 70) as a playable blockout with surface-tagged materials. |

## Getting it running

1. Install **Unreal Engine 5.5** and Visual Studio 2022 (Windows) or Xcode (Mac) with the C++ game workload.
2. Right-click `SkyLinks.uproject` and choose **Generate Visual Studio project files**, then build the `SkyLinksEditor` target, or just open the `.uproject` and let it compile.
3. In the editor, go to **Tools → Execute Python Script** and pick `Scripts/build_blockout_course.py`.
   It creates `/Game/Maps/Course` with all 18 holes and saves it.
4. Press **Play**. Choose **SOLO**, or **HOST** to get a room code friends can **JOIN** with. To test multiplayer on one PC, use **Play → Number of Players: 2** and **Net Mode: Play As Listen Server**. The host taps **TEE OFF**.

Controls in the editor: the mouse acts as a finger. Keyboard: **Space** swings, **A/D** aim, **Q/E** change club, **R** changes spin.

## Shipping to phones

The project is already configured for landscape only on Android and iOS, mobile rendering, and a package name/bundle ID (`com.skylinks.golf`).
Use **Platforms → Android → Package Project**. Your machine needs the Android SDK/NDK that UE 5.5 expects, which you install with `SetupAndroid.bat` from the engine.

## Making it look like the reference

The blockout is flat colour. `Docs/ART_DIRECTION.md` covers the full art pass: palette, the toon shading setup, sky, props, the character pipeline, the HUD reskin, and ready-to-paste prompts if you use Aura in the editor.

## Status

Nobody has compiled or play-tested this yet. It was written without an Unreal install, so expect a round of compile fixes on the first build.
Ball distances also need tuning in play: the club speeds in `GolfPhysics.cpp` are a starting point.
