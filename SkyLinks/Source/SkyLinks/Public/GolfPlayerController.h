#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "GolfTypes.h"
#include "GolfPlayerController.generated.h"

class AGolfBall;
class AGolfCharacter;
class AGolfGameState;

/**
 * Touch controls, landscape:
 *  - Drag sideways in the upper part of the screen to aim.
 *  - Swipe up from the lower part of the screen to swing. Swipe length sets power (the landing
 *    marker follows your finger); lift your finger to hit. Drifting left or right while swiping
 *    hooks or slices the shot.
 *  - Tap the club disc to change club, the spin button to cycle spin.
 *  - Lobby: HOST gives you a room code; JOIN opens a keypad for a friend's code; INVITE lists friends.
 * Keyboard in the editor: hold Space to charge and release to hit, Q/E club, A/D aim, R spin.
 */
UCLASS()
class SKYLINKS_API AGolfPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	AGolfPlayerController();

	virtual void Tick(float DeltaSeconds) override;
	virtual void SetupInputComponent() override;

	UFUNCTION(Server, Reliable)
	void ServerTakeShot(const FGolfShotInput& Input);

	UFUNCTION(Server, Reliable)
	void ServerRequestStart();

	/** Console: host an online (LAN by default) game. */
	UFUNCTION(Exec)
	void HostGame();

	/** Console: join the game with this room code (or the first open game if empty). */
	UFUNCTION(Exec)
	void JoinGame(const FString& RoomCode);

	// Read by the HUD.
	bool IsMyTurn() const;
	AGolfBall* GetMyBall() const;
	bool IsSwinging() const { return bSwiping || bKeyCharging; }
	float GetSwingPower() const { return SwingPower; }
	float GetSwingAccuracy() const { return SwingAccuracy; }
	bool IsPutting() const;
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
	/** Sideways drift for a full hook or slice, as a fraction of screen height. */
	static constexpr float FullErrorDrift = 0.12f;
	/** Drift inside this fraction of FullErrorDrift still counts as dead straight. */
	static constexpr float StraightDeadzone = 0.15f;

private:
	void OnTouchPressed(ETouchIndex::Type FingerIndex, FVector Location);
	void OnTouchMoved(ETouchIndex::Type FingerIndex, FVector Location);
	void OnTouchReleased(ETouchIndex::Type FingerIndex, FVector Location);
	bool HandleButton(const FVector2D& Screen);

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
	bool bAiming = false;
	float AimLastX = 0.f;

	// Lobby
	bool bKeypadOpen = false;
	FString EnteredCode;
	bool bFriendsOpen = false;

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
	float PerfectFlashTime = -100.f;
};
