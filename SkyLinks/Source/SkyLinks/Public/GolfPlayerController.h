#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "GolfTypes.h"
#include "GolfPlayerController.generated.h"

class AGolfBall;
class USceneCaptureComponent2D;
class UTextureRenderTarget2D;
class AGolfBuggy;
class AGolfCharacter;
class AGolfGameState;

/**
 * Touch controls, landscape:
 *  - Drag sideways in the upper part of the screen to aim.
 *  - Swipe up from the lower part of the screen to swing. Swipe length sets power (the landing
 *    marker follows your finger); lift your finger to hit. Drifting left or right while swiping
 *    hooks or slices the shot.
 *  - Tap the club disc to change club, the spin button to cycle spin.
 *  - Walking (lobby, and between shots): drag on the left half to walk; GET IN by a buggy.
 *  - Driving: drag on the left half to steer, hold GO / REV on the right, GET OUT to climb out.
 *    PLAY SHOT appears once you are within 15 m of your ball; SKIP takes you there instantly.
 *  - Lobby: HOST gives you a room code; JOIN opens a keypad for a friend's code; INVITE lists friends.
 * Keyboard in the editor: hold Space to charge and release to hit, Q/E club (at the ball), A/D aim or
 * steer, W/A/S/D walk or drive, E get in / out of a buggy, F play shot, R spin.
 */
UCLASS()
class SKYLINKS_API AGolfPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	AGolfPlayerController();

	virtual void Tick(float DeltaSeconds) override;
	virtual void SetupInputComponent() override;
	virtual void ClientEnableNetworkVoice_Implementation(bool bEnable) override;
	UFUNCTION(Exec)
	void ToggleMicrophone();
	UFUNCTION(Exec)
	void TogglePlayerVoiceMute(int32 PlayerId);
	bool IsVoicePanelOpen() const { return bVoicePanelOpen; }

	UFUNCTION(Server, Reliable)
	void ServerTakeShot(const FGolfShotInput& Input);

	UFUNCTION(Server, Reliable)
	void ServerRequestStart();

	UFUNCTION(Server, Reliable)
	void ServerFinishDriving(bool bSkip);

	/** E: get into the buggy you're standing next to, or out of the one you're driving. */
	UFUNCTION(Server, Reliable)
	void ServerToggleBuggy();

	/** Console: host an online (LAN by default) game. */
	UFUNCTION(Exec)
	void HostGame();

	/** Console: join the game with this room code (or the first open game if empty). */
	UFUNCTION(Exec)
	void JoinGame(const FString& RoomCode);

	// Read by the HUD.
	bool IsMyTurn() const;
	/** In my buggy with the controls (lobby or on the way to my ball). */
	bool IsDriving() const;
	/** On foot and free to walk (lobby, or on the way to my ball). */
	bool IsWalking() const;
	/** My turn, and I'm on my way to my ball (walking or driving) rather than at it. */
	bool IsTravelling() const;
	/** A buggy close enough to get into with E (mine, or a free one before the round), or null. */
	AGolfBuggy* GetBuggyInReach() const;
	FVector2D GetWalkStick() const { return TouchWalk; }
	/** On foot: the GO bar is held (or W / the stick is pushed), and how fast, 0 walk .. 1 run. */
	bool IsPaceHeld() const { return PaceFingers > 0; }
	float GetWalkPace() const { return CurrentPace; }
	/** Lobby, host on foot by the first tee: E tees up and starts the round. */
	bool CanTeeUp() const;
	/** Only the host can start the round (listen server's own player, or playing solo). */
	bool IsHost() const { return GetNetMode() != NM_Client; }
	bool IsLobbyPanelHidden() const { return bLobbyPanelHidden; }
	AGolfBuggy* GetMyBuggy() const;
	float GetDriveSteer() const { return FMath::Clamp(TouchSteer + (IsDriving() ? AimInput : 0.f), -1.f, 1.f); }
	/** Metres from me (on foot or in the buggy) to my ball, or -1. */
	float GetDistanceToBall() const;
	/** Close enough to my ball to play it (PLAY / F). */
	bool CanPlayShot() const;
	AGolfBall* GetMyBall() const;
	bool IsSwinging() const { return bSwiping || bKeyCharging; }
	float GetSwingPower() const { return SwingPower; }
	float GetSwingAccuracy() const { return SwingAccuracy; }
	bool IsPutting() const;
	/** True while a short wedge shot shows the overhead landing view (a window on the HUD). */
	bool IsLandingView() const { return bLandingView; }
	/** Live overhead picture of the landing area, or null when there isn't one. */
	UTextureRenderTarget2D* GetLandingViewTexture() const;
	float GetAimYaw() const { return AimYaw; }
	/** Landing window: ground point at its middle, the capture height above it (cm), horizontal FOV (degrees). */
	FVector GetLandingViewCenter() const { return LandingViewCenter; }
	float GetLandingViewHeight() const { return LandingViewHeight; }
	static constexpr float LandingViewFOV = 60.f;
	/** Overhead picture of the whole current hole (tee at the bottom, green at the top), or null. */
	UTextureRenderTarget2D* GetMiniMapTexture() const;
	/** Mini map framing: ground point at its middle, heading that points up the map, width in cm. */
	FVector GetMiniMapCenter() const { return MiniMapCenter; }
	float GetMiniMapYaw() const { return MiniMapYaw; }
	float GetMiniMapWidth() const { return MiniMapWidth; }
	int32 GetClubIndex() const { return ClubIndex; }
	float GetClubCarry(int32 Index) const { return ClubCarry.IsValidIndex(Index) ? ClubCarry[Index] : 0.f; }
	FString GetSpinLabel() const;
	bool HasPreview() const { return bHasPreview; }
	const TArray<FVector>& GetPreviewPath() const { return PreviewPath; }
	FVector GetPreviewLanding() const { return PreviewLanding; }
	const TArray<FVector>& GetGreenGridPoints() const { return GridPoints; }
	/** Downhill direction at each grid point, scaled by slope (sine of the angle). */
	const TArray<FVector>& GetGreenGridSlopes() const { return GridSlopes; }
	float GetPerfectFlashTime() const { return PerfectFlashTime; }
	bool IsKeypadOpen() const { return bKeypadOpen; }
	FString GetEnteredCode() const { return EnteredCode; }
	bool IsFriendsOpen() const { return bFriendsOpen; }

	/** Touches starting below this fraction of the screen height swing; above it they aim. */
	static constexpr float SwipeZoneTop = 0.5f;
	/** Swipe length for full power, as a fraction of screen height. */
	static constexpr float FullPowerSwipe = 0.45f;

private:
	enum class ETouchRole : uint8 { None, Aim, Swipe, Steer, Gas, Reverse, Walk, Pace };

	void OnTouchPressed(ETouchIndex::Type FingerIndex, FVector Location);
	void OnTouchMoved(ETouchIndex::Type FingerIndex, FVector Location);
	void OnTouchReleased(ETouchIndex::Type FingerIndex, FVector Location);
	bool HandleButton(const FVector2D& Screen, int32 Finger);

	void OnThrottleForwardPressed() { KeyThrottle += 1.f; }
	void OnThrottleForwardReleased() { KeyThrottle -= 1.f; }
	void OnThrottleBackPressed() { KeyThrottle -= 1.f; }
	void OnThrottleBackReleased() { KeyThrottle += 1.f; }
	void OnPlayShotKey();
	/** E: next club while addressing the ball, otherwise in / out of the buggy. */
	void OnUseKey();
	void UpdateWalking();

	void OnSwingKeyPressed();
	void OnSwingKeyReleased();
	void OnNextClub() { CycleClub(1); }
	void OnPrevClub() { CycleClub(-1); }
	void OnSpinKey() { CycleSpin(); }
	void OnAimLeftPressed() { AimInput -= 1.f; }
	void OnAimLeftReleased() { AimInput += 1.f; }
	void OnAimRightPressed() { AimInput += 1.f; }
	void OnAimRightReleased() { AimInput -= 1.f; }

	void UpdateSwipe(const FVector2D& Screen);
	void ReleaseSwing();
	void Fire(float Power, float Accuracy);
	void CancelSwing();
	void CycleClub(int32 Direction);
	void CycleSpin();
	void SetAim(float Yaw);
	void OnTurnStarted();
	void RefreshPreview();
	void RefreshGreenGrid();
	float GetIdlePreviewPower() const;

	AGolfGameState* GetGolfState() const;
	AGolfCharacter* GetMyGolfer() const;
	float ViewportHeight() const;

	// Swing
	bool bSwiping = false;
	bool bKeyCharging = false;
	float KeyChargeDirection = 1.f;
	FVector2D SwipeStart = FVector2D::ZeroVector;
	float SwingPower = 0.f;
	float SwingAccuracy = 0.f;

	// Aim and club
	int32 ClubIndex = 0;
	int32 SpinPreset = 0;
	FVector2D Spin = FVector2D::ZeroVector;
	float AimYaw = 0.f;
	float AimInput = 0.f;
	TArray<float> ClubCarry;
	// Touch fingers: what each one is doing and where it went down.
	ETouchRole TouchRoles[ETouchIndex::MAX_TOUCHES] = {};
	FVector2D TouchStarts[ETouchIndex::MAX_TOUCHES];
	float AimLastX = 0.f;

	// Driving
	float TouchSteer = 0.f;
	float KeyThrottle = 0.f;
	int32 GasFingers = 0;
	int32 ReverseFingers = 0;

	// Walking: the left-thumb stick (-1..1, +Y forward).
	FVector2D TouchWalk = FVector2D::ZeroVector;
	/** Fingers holding the GO bar, how far up it they've slid (0..1), and the pace being used this frame. */
	int32 PaceFingers = 0;
	float TouchPace = 0.f;
	float CurrentPace = 0.f;
	bool bRunKey = false;
	void OnRunKeyPressed() { bRunKey = true; }
	void OnRunKeyReleased() { bRunKey = false; }

	// Lobby
	bool bLobbyPanelHidden = false;
	bool bKeypadOpen = false;
	FString EnteredCode;
	bool bFriendsOpen = false;
	bool bVoicePanelOpen = false;

	bool bWasMyTurn = false;
	FVector LastTurnBall = FVector::ZeroVector;

	// Preview
	bool bPreviewDirty = true;
	bool bGridDirty = true;
	bool bHasPreview = false;
	float PreviewCooldown = 0.f;
	float GridCooldown = 0.f;
	float PreviewPower = 1.f;
	TArray<FVector> PreviewPath;
	FVector PreviewLanding = FVector::ZeroVector;
	TArray<FVector> GridPoints;
	TArray<FVector> GridSlopes;
	bool bLandingView = false;
	FVector LandingViewCenter = FVector::ZeroVector;
	float LandingViewHeight = 3500.f;
	void UpdateLandingCapture();

	UPROPERTY(Transient)
	TObjectPtr<USceneCaptureComponent2D> LandingCapture;

	UPROPERTY(Transient)
	TObjectPtr<UTextureRenderTarget2D> LandingTarget;

	// Mini map of the hole: captured once per hole (and once more shortly after).
	void UpdateMiniMap(float DeltaSeconds);
	UPROPERTY(Transient)
	TObjectPtr<USceneCaptureComponent2D> MiniMapCapture;
	UPROPERTY(Transient)
	TObjectPtr<UTextureRenderTarget2D> MiniMapTarget;
	TWeakObjectPtr<class AGolfHole> MiniMapHole;
	FVector MiniMapCenter = FVector::ZeroVector;
	float MiniMapYaw = 0.f;
	float MiniMapWidth = 30000.f;
	float MiniMapRecapture = 0.f;
	float PerfectFlashTime = -100.f;
};
