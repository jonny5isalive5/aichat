# Art direction: matching the reference

The reference is classic anime-style fantasy golf. The rules below get the blockout there.

## The shot

- The camera is low, about 1 m above the ball and 4 m behind it, looking down the aim line. The golfer stands on the **left third** of the frame, facing right.
  This is already set up in `AGolfCharacter` (`CameraArm`: length 380, socket offset Y 45 / Z 80, pitch −8°).
- The horizon sits high, around 40% from the top, so the fairway fills the frame.
- After impact the view cuts to the ball's chase camera (`AGolfBall::ChaseArm`). Tune `ChaseDistance`, `ChasePitch` and `ChaseTurnSpeed` on the ball Blueprint.
- The tee pad is a round teal/blue platform with a crest in the middle. In the blockout it's the `M_TeePad` disc; replace it with a decal on a raised disc.

## Palette

| Role | Colour |
|---|---|
| Sky top / horizon | `#1E6BE0` / `#9FD8FF` |
| Clouds | `#FFFFFF` with `#D6E9FF` shadow |
| Fairway / rough / green | `#52C13A` / `#2E8B2E` / `#7EDC4A` (mow stripes ±6% value) |
| Sand | `#F2DC97` |
| Water | `#2E9BD6` |
| Mushroom caps | `#E0483A` with `#F7E6C4` spots |
| HUD navy / cyan / gold | `#08143D` / `#33D9FF` / `#FFD140` |

The colours are saturated and the shadows lean blue, never grey.

## Rendering on mobile

1. **Toon shading.** Use a post-process material that quantises lighting into two or three bands, with a soft outline from a depth/normal edge. On mobile, prefer an unlit material with lighting baked into a 2-tone ramp (Material Parameter Collection holding the sun direction). It's cheaper and reads better.
2. **Sky.** Use a painted sky-dome texture with drifting cloud cards, not Volumetric Clouds (too costly on phones).
3. **Grass.** Use stripe masks on the fairway material rather than grass meshes. Add a few cheap card-grass clumps only at the edges of the rough.
4. **Lighting.** A single stationary sun with baked lightmaps for the course and dynamic shadows only for the golfer and ball. Turn auto-exposure off; it's already off in `DefaultEngine.ini`.
5. **Scale.** Props are cartoonishly large: trees 12–16 m tall with round canopies, mushrooms 10 m tall. The blockout script already uses these sizes.

## Assets to source or build

| Asset | Approach |
|---|---|
| Golfer (chibi, big head, oversized hat) | Model in Blender or VRoid Studio and import with VRM4U; retarget the UE5 Mannequin with IK Retargeter. |
| Swing animation | Get a golf-swing animation (e.g. Mixamo "Golf Drive") and turn it into a montage. Assign it to `SwingMontage` on a Blueprint child of `GolfCharacter`. |
| Trees, mushrooms, lighthouse, palm trees | Search Fab for "stylized nature" or "toon fantasy" packs, or model low-poly versions with vertex colour. |
| Clubs | One stylised mesh per club family (wood, iron, wedge, putter), attached to a hand socket. |
| HUD | Move to UMG when you reskin: circular club icon bottom-left, curved gauge, wind dial. `AGolfHUD` shows exactly which data each widget needs. |

Swap the blockout pieces in place so the physical materials stay the same. Each surface's material has to keep its `PM_*` physical material, because the ball physics reads the surface type from it.

## Aura prompts

If you use the Aura assistant in the Unreal Editor, these prompts line up with this project's structure:

1. *"Create a Blueprint child of GolfCharacter called BP_Golfer, assign my imported skeletal mesh and the golf swing montage, and set it as the Default Pawn Class in a Blueprint child of GolfGameMode."*
2. *"Create a mobile-friendly toon post-process material with 3 lighting bands and a 1-pixel dark outline from scene depth, and add it to an unbound post-process volume in the Course map."*
3. *"In the Course map, replace every static mesh actor labelled TreeCanopy with a random pick from my stylized tree meshes, keeping location and scale."*
4. *"Build a UMG widget WBP_GolfHUD that matches this layout: circular club selector bottom-left, horizontal power gauge bottom-centre with a gold impact zone near the left, wind dial top-right, hole number and par top-left."*
5. *"Create a painted sky sphere material with a blue gradient and scrolling cloud textures, and use it in place of SkyAtmosphere in the Course map."*

Check any Blueprint or material Aura generates against the class and property names in `Source/SkyLinks/Public`.
