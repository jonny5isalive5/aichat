#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GolfTypes.h"
#include "GolfGameMode.generated.h"

class AGolfBall;
class AGolfHole;
class AGolfCharacter;
class AGolfPlayerState;
class AGolfGameState;

/**
 * Server-side rules for a stroke-play round of up to 4 players.
 * Tee order follows honors (best score on the previous hole goes first); after that the player
 * farthest from the cup plays next. Water and out of bounds cost one stroke and replay from the
 * previous spot. A player picks up at double par.
 */
UCLASS()
class SKYLINKS_API AGolfGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AGolfGameMode();

	virtual void BeginPlay() override;
	virtual void PostLogin(APlayerController* NewPlayer) override;
	virtual void Logout(AController* Exiting) override;

	void RequestStartRound(APlayerController* Requester);
	void HandleShot(APlayerController* Shooter, const FGolfShotInput& Input);

	UPROPERTY(EditDefaultsOnly, Category = "Golf")
	TSubclassOf<AGolfBall> BallClass;

	UPROPERTY(EditDefaultsOnly, Category = "Golf")
	float TurnDelay = 1.8f;

	UPROPERTY(EditDefaultsOnly, Category = "Golf")
	float HoleSummarySeconds = 7.f;

	/** Seconds after impact before everyone's camera cuts to the ball chase camera. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf")
	float ChaseCameraDelay = 0.25f;

protected:
	void StartHole(int32 Index);
	void NextTurn();
	void BeginTurn(AGolfPlayerState* Player);
	void EndHole();
	void OnBallStopped(AGolfBall* Ball, EGolfShotResult Result);

	void ViewAll(AActor* Target, float BlendTime);
	AGolfGameState* GetGolfState() const;
	AGolfCharacter* GetGolfer(AGolfPlayerState* Player) const;
	AGolfPlayerState* FindBallOwner(const AGolfBall* Ball) const;
	TArray<AGolfPlayerState*> GetRoundPlayers() const;

	UPROPERTY()
	TArray<TObjectPtr<AGolfHole>> Holes;

	TArray<TWeakObjectPtr<AGolfPlayerState>> TeeOrder;
	bool bShotInFlight = false;
	FTimerHandle FlowTimer;
	FTimerHandle CameraTimer;
};
