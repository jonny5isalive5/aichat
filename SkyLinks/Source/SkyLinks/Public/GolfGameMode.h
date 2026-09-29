#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GolfTypes.h"
#include "GolfGameMode.generated.h"

class AGolfBall;
class AGolfBuggy;
class AGolfHole;
class AGolfCharacter;
class AGolfPlayerState;
class AGolfGameState;

/**
 * Server-side rules for a stroke-play round of up to 4 players.
 * Tee order follows honors (best score on the previous hole goes first); after that the player
 * farthest from the cup plays next. Water and out of bounds cost one stroke and replay from the
 * previous spot. A player picks up at double par.
 *
 * Players start at the clubhouse and pick a buggy from the car park (E to get in and out). Buggies
 * park beside the tee at the start of a hole; after the tee shot each turn starts on foot: walk, or
 * get in the buggy and drive, to the ball and play it (PLAY within 15 m, or SKIP to go straight there).
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

	/** The active player is at their ball (on foot or in the buggy) and plays it, or skips the trip there. */
	void FinishDriving(APlayerController* Driver, bool bSkip);

	/** E: climb out of the buggy you're driving, or into a buggy you're standing next to. */
	void ToggleBuggy(APlayerController* Player);

	/** How close (cm) to the first tee the host must walk to tee up and start the round with E. */
	static constexpr float TeeUpReach = 900.f;

	/** Can this player walk and drive freely right now (lobby, round over, or on the way to their ball)? */
	bool CanRoam(const class AGolfPlayerState* Player) const;

	/** Actor tag on the car park's buggy bays (TargetPoints placed by Scripts/apply_floating_islands.py). */
	static const FName BuggyBayTag;

	UPROPERTY(EditDefaultsOnly, Category = "Golf")
	TSubclassOf<AGolfBall> BallClass;

	UPROPERTY(EditDefaultsOnly, Category = "Golf")
	TSubclassOf<AGolfBuggy> BuggyClass;

	/** Turns start on foot when the golfer is further than this from the ball (cm); closer, they step straight up. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf")
	float WalkUpDistance = 250.f;

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
	/** The active player walks (and drives, if they get in their buggy) to their ball. */
	void StartTravel(AGolfPlayerState* Player);
	void EnterBuggy(AGolfPlayerState* Player, AGolfBuggy* Buggy);
	/** Climb out; then walk on (roam) or step up to the ball. */
	void ExitBuggy(AGolfPlayerState* Player, bool bThenAddress);
	/** Buggy this player may get into from where they stand (their own, or a free one in the car park). */
	AGolfBuggy* FindBuggyToEnter(AGolfPlayerState* Player) const;
	bool IsBuggyFree(const AGolfBuggy* Buggy) const;
	/** Give a player without a buggy the nearest free one (or a new one if the car park is empty). */
	void AssignBuggy(AGolfPlayerState* Player);
	/** Everyone watches during a turn; in the lobby only the player's own camera moves. */
	void ViewFor(AGolfPlayerState* Player, AActor* Target, float BlendTime);
	void SpawnCarPark();
	/** Everyone on foot at the end of a round (or back in the lobby). */
	void ReleaseToRoam();
	/** Show (and let collide) only this player's golfer. */
	void ShowOnly(AGolfPlayerState* Player);
	void AddressBall(AGolfPlayerState* Player);
	void PossessGolfer(AGolfPlayerState* Player);
	void EndHole();
	void OnBallStopped(AGolfBall* Ball, EGolfShotResult Result);

	void ViewAll(AActor* Target, float BlendTime);
	AGolfGameState* GetGolfState() const;
	AGolfCharacter* GetGolfer(AGolfPlayerState* Player) const;
	AGolfPlayerState* FindBallOwner(const AGolfBall* Ball) const;
	TArray<AGolfPlayerState*> GetRoundPlayers() const;

	UPROPERTY()
	TArray<TObjectPtr<AGolfHole>> Holes;

	/** Buggies parked in the car park bays, free to pick until someone gets in. */
	UPROPERTY()
	TArray<TObjectPtr<AGolfBuggy>> CarPark;

	TArray<TWeakObjectPtr<AGolfPlayerState>> TeeOrder;
	bool bShotInFlight = false;
	FTimerHandle FlowTimer;
	FTimerHandle CameraTimer;
	FTimerHandle StrikeTimer;
	/** The host is teeing up on the first tee; the round starts when the animation ends. */
	bool bTeeingUp = false;
	FTimerHandle TeeUpTimer;
	void BeginRound();

	/** Golfers climbing into or out of a buggy; their E / PLAY / SKIP presses wait until it finishes. */
	TSet<TWeakObjectPtr<AGolfPlayerState>> InTransition;
};
