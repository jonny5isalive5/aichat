# Group voice — Keeping Friends Connected

SkyLinks is designed for four friends sharing a round and a conversation. Voice belongs to the whole room, not to distance from a golfer or whose turn it is.

## Controls

- Open microphone is the default after joining or hosting a room.
- Tap **MIC ON** / **MUTED**, or press **M**, to toggle your microphone.
- **GROUP** opens the four-player panel. Tap a player's **MUTE** to silence them locally; **UNMUTE** reverses it. This does not silence that player for everyone else.
- Green names indicate detected speech. **NO VOICE** and the panel status distinguish unavailable voice from a working microphone.
- Microphone and individual mute choices survive map travel for the current game instance. They reset when the application is restarted.
- Voice continues through lobby, shots, buggy driving and scorecards. No proximity attenuation is applied. The game does not record conversations.

## Backends

`UGolfVoiceSubsystem` owns preferences and uses the online subsystem for its own world, including isolated PIE worlds.

The default Null/LAN backend uses Unreal's `IOnlineVoice` capture, codec and network voice packets. Host/join a real named session through the room controls; direct-IP and editor listen-server launch alone do not establish the named voice session. A microphone supported by Unreal and operating-system microphone access are required.

The EOS backend uses the existing local user's `IVoiceChatUser` from `IOnlineSubsystemEOS`. Hosted lobbies request `bUseLobbiesVoiceChatIfAvailable`; the online subsystem owns channel join/leave and authentication. The application does not mint insecure room tokens or run its own audio relay. `VoiceChat` and `EOSVoiceChat` plugins are enabled. Configure the EOS product, lobby/RTC policy and account setup before internet testing. No EOS credentials were added as part of this change.

See Epic's [EOS voice integration](https://dev.epicgames.com/documentation/unreal-engine/voice-chat-with-epic-online-services) and [voice interface](https://dev.epicgames.com/documentation/unreal-engine/voice-chat-interface-in-unreal-engine).

## Acceptance checks before calling voice production-ready

1. Four separate devices/accounts join one room. Each player speaks and the other three hear clear audio, regardless of turn or course position.
2. Local mute stops outgoing audio immediately, including across hole changes and room replacement. Unmute restores it.
3. Individual mute silences only that person for that listener; the other players still hear them. Rejoining does not undo the listener's choice during the same application session.
4. Leave/rejoin, disconnect, device removal and denied microphone access show an accurate state and do not transmit outside a room.
5. Test speaker echo, headphones, network loss and simultaneous speech. Adjust capture/voice quality only from those results.
6. Test packaged Android/iOS builds, microphone permission prompts and app background/foreground behaviour. Mobile permission integration and device validation remain outstanding.

A successful C++ build or two PIE windows is not evidence of audible four-device voice. Internet EOS voice and native mobile voice are not yet verified.

## Local verification, 27 September 2026

- Development Editor build succeeded on UE 5.8.3 after the final session/mute lifecycle changes. Existing engine-header deprecation and non-preferred compiler warnings remain.
- The rendered 960x540 lobby displayed the tagline, microphone button and group panel.
- In two independent PIE worlds, the first player hosted room 7042 and the second joined through LAN room discovery. The roster showed 2/4 players.
- Touch microphone mute changed the button to MUTED and persisted across hosting/map travel. The group panel reported LAN voice ready; the engine logged local talker registration result `0x00000000`.
- Both peers registered each other with remote voice processing result `0x00000000`. Tapping the other player's MUTE changed its button to UNMUTE and logged `Muting remote talker` in the voice backend.
- Both preview microphones were muted before the second player joined, avoiding feedback from one computer. No audible speech delivery or voice quality result is claimed. An attempted second UI click did not reach the game while focus changed to another application, so individual unmute still requires a controlled follow-up.
- Code review after that test removed repeated idle start/stop calls and applies the stored microphone choice immediately in create/join callbacks and the post-travel voice handshake. The final rebuilt version requires a follow-up runtime check during an agreed desktop test window.
