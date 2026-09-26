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
 *  - Drag anywhere on the course to turn the aim.
 *  - Tap SWING (or anywhere once the gauge runs) three times: start, set power, set impact.
 *  - Tap the club disc to change club, the spin button to cycle spin.
 *  - Lobby: HOST gives you a room code; JOIN opens a keypad for a friend's code; INVITE lists friends.
 * Keyboard in the editor: Space swings, Q/E change club, A/D aim, R spin.
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

	bool IsKeypadOpen() const { return bKeypadOpen; }
	FString GetEnteredCode() const { return EnteredCode; }
	bool IsFriendsOpen() const { return bFriendsOpen; }

	enum class EGauge : uint8 { Idle, Rising, Returning };

	// Read by the HUD.
	bool IsMyTurn() const;
	AGolfBall* GetMyBall() const;
	EGauge GetGaugeState() const { return Gauge; }
	float GetGaugePosition() const { return GaugePos; }
	float GetGaugePower() const { return GaugePower; }
	int32 GetClubIndex() const { return ClubIndex; }
	float GetClubCarry(int32 Index) const { return ClubCarry.IsValidIndex(Index) ? ClubCarry[Index] : 0.f; }
	FVector2D GetSpin() const { return Spin; }
	FString GetSpinLabel() const;
	bool HasPreview() const { return bHasPreview; }
	const TArray<FVector>& GetPreviewPath() const { return PreviewPath; }
	FVector GetPreviewLanding() const { return PreviewLanding; }
	float GetPerfectFlashTime() const { return PerfectFlashTime; }

	/** Gauge layout: impact point at 0, full power at 1, overdrive to 1.1, miss below -0.15. */
	static constexpr float GaugeMin = -0.15f;
	static constexpr float GaugeMax = 1.1f;
	static constexpr float ImpactWindow = 0.12f;
	static constexpr float PerfectWindow = 0.015f;

private:
	void OnTouchPressed(ETouchIndex::Type FingerIndex, FVector Location);
	void OnTouchMoved(ETouchIndex::Type FingerIndex, FVector Location);
	void OnTouchReleased(ETouchIndex::Type FingerIndex, FVector Location);

	void OnSwingKey() { GaugeTap(); }
	void OnNextClub() { CycleClub(1); }
	void OnPrevClub() { CycleClub(-1); }
	void OnSpinKey() { CycleSpin(); }
	void OnAimLeftPressed() { AimInput -= 1.f; }
	void OnAimLeftReleased() { AimInput += 1.f; }
	void OnAimRightPressed() { AimInput += 1.f; }
	void OnAimRightReleased() { AimInput -= 1.f; }

	void GaugeTap();
	void Fire(float Accuracy);
	void CycleClub(int32 Direction);
	void CycleSpin();
	void SetAim(float Yaw);
	void OnTurnStarted();
	void RefreshPreview();

	AGolfGameState* GetGolfState() const;
	AGolfCharacter* GetMyGolfer() const;

	EGauge Gauge = EGauge::Idle;
	float GaugePos = 0.f;
	float GaugeDirection = 1.f;
	float GaugePower = 0.f;

	int32 ClubIndex = 0;
	int32 SpinPreset = 0;
	FVector2D Spin = FVector2D::ZeroVector;
	float AimYaw = 0.f;
	float AimInput = 0.f;
	TArray<float> ClubCarry;

	bool bKeypadOpen = false;
	FString EnteredCode;
	bool bFriendsOpen = false;

	bool bDragging = false;
	float DragLastX = 0.f;

	bool bWasMyTurn = false;
	FVector LastTurnBall = FVector::ZeroVector;

	bool bPreviewDirty = true;
	bool bHasPreview = false;
	float PreviewCooldown = 0.f;
	TArray<FVector> PreviewPath;
	FVector PreviewLanding = FVector::ZeroVector;
	float PerfectFlashTime = -100.f;
};
