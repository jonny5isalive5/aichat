# Playing with friends

There are three ways to get friends into your game:

| Way | How | Needs |
|---|---|---|
| **Room code** | The host taps **HOST** and gets a 4-digit code on the lobby screen. Friends tap **JOIN**, type the code and tap **GO**. | Same Wi-Fi with the default setup; anywhere once EOS is on |
| **Invite** | The host taps **INVITE** and then **+** next to a friend's name. The friend gets a "… invited you to play" pop-up with **JOIN**. | EOS (friends come from Epic accounts) |
| **Direct IP** | Open the console and type `open 192.168.1.20`. | Same network, or the host's port 7777 reachable |

Games take up to 4 players. Anyone who joins mid-round watches until the next round.

## How the netcode works

- There's one **listen server**: the host's phone runs the game and plays at the same time.
- It's turn-based, so bandwidth is tiny. A shot is one reliable call from the player to the server. The server sends the launch to everyone, and each device simulates the flight locally with the same fixed-step physics, so the chase camera stays smooth. When the ball stops, the server sends its final position, which is authoritative.
- The server re-checks every shot: that it's your turn, that the ball is at rest, and that power, accuracy, spin and club are in range.

## Default: same Wi-Fi (LAN)

`DefaultPlatformService=Null` in `Config/DefaultEngine.ini`. Room codes and HOST/JOIN work between phones on the same network.
In the editor, test with **Play → Number of Players: 2–4** and **Net Mode: Play As Listen Server**.

## Anywhere: Epic Online Services (free)

EOS gives you internet matchmaking, NAT traversal (no port forwarding), Epic friends lists and invites on Android, iOS and PC. The plugins are already enabled in `SkyLinks.uproject`.

1. Sign in at https://dev.epicgames.com/portal and create a product. Under **Product Settings**, create:
   - a **Client** with the "GameClient" policy,
   - an **Application**, linked to that client, with the brand review and permissions (basic profile, online presence, friends) filled in.
   Note the Product, Sandbox, Deployment and Client IDs and the client secret.
2. In **Project Settings → Plugins → Epic Online Services**, add an Artifact with those IDs. Set **Encryption Key** to 64 hex characters.
3. Change `Config/DefaultEngine.ini`:
   ```ini
   [OnlineSubsystem]
   DefaultPlatformService=EOS

   [OnlineSubsystemEOS]
   bEnabled=true

   [/Script/OnlineSubsystemEOS.EOSSettings]
   DefaultArtifactName=SkyLinks
   bUseEAS=True
   bUseEOSConnect=True
   bUseEOSSessions=True
   bMirrorStatsToEOS=False

   [/Script/OnlineSubsystemEOS.NetDriverEOS]
   bIsUsingP2PSockets=true
   ```
   and replace the `GameNetDriver` line with:
   ```ini
   !NetDriverDefinitions=ClearArray
   +NetDriverDefinitions=(DefName="GameNetDriver",DriverClassName="/Script/OnlineSubsystemEOS.NetDriverEOS",DriverClassNameFallback="/Script/OnlineSubsystemUtils.IpNetDriver")
   ```
4. Build and play. The first time a player taps HOST, JOIN or INVITE, the game signs them in. It tries a saved Epic login first, then opens the Epic sign-in page. After that, the INVITE button and friends list appear in the host's lobby.

The code for all of this is in `UGolfSessionSubsystem` (`Source/SkyLinks/*/GolfSessionSubsystem.*`).
Sign-in, room-code search, friend list and invites all go through the standard Online Subsystem interfaces, so Steam or platform services can replace EOS later without touching the game code.
