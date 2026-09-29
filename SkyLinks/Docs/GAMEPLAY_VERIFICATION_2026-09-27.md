# Gameplay verification — 2026-09-27

## Swipe and buggy

Tested in UE 5.8 standalone PIE through real mouse input and Aura key input. Temporary C++ diagnostic logs were removed after diagnosis; swing behaviour was not changed.

- Mouse drag from client coordinates (657,480) to (657,275): power 0.840508, accuracy 0; shot launched and stroke count increased. Ball settled on Fairway at (18665.217256,1253.829929,22.077834).
- Some automated drags arrived with identical press/release positions, producing zero power and no stroke. This explains observed automation failures; it does not validate native mobile touch behaviour.
- W held for 1.5 seconds moved the buggy from (-1200,-525,110.51) to approximately (-197.01,-525,85.37). Later rendered speed returned to 0 km/h.

## Arranged putting test

The live PIE ball was repositioned to (35500,0,26.24), with RestLocation and RestLie=Green set explicitly, five metres from hole one's cup. This was test setup, not proof of a natural approach landing. No map or asset was saved from this setup.

- Clicking Skip Drive addressed the ball, selected PT and rendered the green slope arrows and ground-following aim line.
- A 90-pixel upward mouse swipe produced power 0.369004 and zero sideways error. The ball rolled uphill and broke sideways, settling at (35960.112395,-26.242596,31.583729), Green, about 47.8 cm from the cup.
- A 0.16-second Space charge then holed out. The score became -1 for the arranged three-stroke hole; gameplay advanced to hole 2, Oak Grove, par 3.
- The HUD had displayed PIN 0 m at 47.8 cm. It now displays centimetres below 1 m, one decimal below 10 m, and whole metres beyond that. Live Coding compilation succeeded. A separate arranged 48 cm RestLocation rendered PIN 48 cm in the updated HUD.

Still unverified: native touchscreen devices, full natural six-hole playthrough, steering/reverse/arrival edge cases, complete multiplayer rounds, EOS/invites. Art remains provisional, including primitive trees/golfer and missing SM6 project-setting warnings.
