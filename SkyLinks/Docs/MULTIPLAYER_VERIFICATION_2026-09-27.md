# Multiplayer verification — 2026-09-27

UE 5.8 Development Editor build succeeded after a clean editor restart.

Two independent standalone PIE worlds (960 x 540 requested) were used; they were not preconnected by PIE net mode. Invoked the existing HostGame and JoinGame console functions through Aura's live actor interface.

- Host created LAN room 6820.
- HostGame again closed the existing session and created room 7147.
- Second independent player joined code 7147 through LAN discovery. The log recorded a connection to port 7777 and `Join succeeded`; both rendered lobbies displayed the same two-player roster and room code. Host displayed 2/4 players; client displayed waiting for host.
- Clicked TEE OFF in the host HUD. The hole-one HUD displayed both players at zero strokes.

Changes: session replacement now waits for DestroySession completion; concurrent host/search/join operations are guarded; immediate join failures and failed searches clear busy state; shutdown removes outstanding delegates. Online interfaces resolve against the current world to isolate PIE players.

Scope: same-machine LAN verification, not internet/EOS, invitations, mobile devices, four-player capacity or full-round replication. Existing OnlineSession warnings about player registration remain to investigate. Mouse swipe did not launch a shot during this run and is being investigated separately.
