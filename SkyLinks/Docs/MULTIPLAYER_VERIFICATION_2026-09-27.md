# Multiplayer verification — 2026-09-27

UE 5.8 Development Editor build succeeded after a clean editor restart.

Two independent standalone PIE worlds (960 x 540 requested) were used; they were not preconnected by PIE net mode. Invoked the existing HostGame and JoinGame console functions through Aura's live actor interface.

- Host created LAN room 6820.
- HostGame again closed the existing session and created room 7147.
- Second independent player joined code 7147 through LAN discovery. The log recorded a connection to port 7777 and `Join succeeded`; both rendered lobbies displayed the same two-player roster and room code. Host displayed 2/4 players; client displayed waiting for host.
- Clicked TEE OFF in the host HUD. The hole-one HUD displayed both players at zero strokes.

Changes: session replacement now waits for DestroySession completion; concurrent host/search/join operations are guarded; immediate join failures and failed searches clear busy state; shutdown removes outstanding delegates. Online interfaces resolve against the current world to isolate PIE players.

Scope: same-machine LAN verification, not internet/EOS, invitations, mobile devices, four-player capacity or full-round replication. Existing OnlineSession warnings about player registration remain to investigate. Mouse swipe did not launch a shot during this run and is being investigated separately.

## Connected gameplay follow-up

A fresh listen-server PIE session with host/client was then tested using normal Space key charge/release input.

- Host shot: both worlds reported GolfBall_0 at (20092.361842,1244.121109,23.544416), Fairway, and the host at one stroke. Turn transferred to the client.
- Host key input during the client's turn left the host at one stroke (client input gating; this does not independently test rejection of a forged network RPC).
- Client shot: both worlds reported GolfBall_1 at (15221.685947,841.271671,22.077808), Fairway. Both players had one stroke. The farther client ball correctly retained the next turn, with bActiveDriving=true on both worlds.
- PlayerState object numbering differs between worlds; players were matched using PlayerNamePrivate and Ball references, not object suffix alone.
- Client buggy: W for 3 seconds with D for 2 seconds moved it from (-1200,-175) to about (-1352,2074), turning from 0 to 106.6 degrees. After S for 2 seconds, it moved back to about (-1198.5,1560.9). Host/client final positions agreed to sub-centimetre XY precision; transient reads while coasting differed by several centimetres.

These checks establish a two-player tee-shot/turn/buggy smoke test, not full-round, internet, disconnect or adverse-latency acceptance.
