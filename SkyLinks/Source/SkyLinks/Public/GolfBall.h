#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GolfTypes.h"
#include "GolfPhysics.h"
#include "GolfBall.generated.h"

class UStaticMeshComponent;
class USpringArmComponent;
class UCameraComponent;

DECLARE_MULTICAST_DELEGATE_TwoParams(FOnGolfBallStopped, class AGolfBall*, EGolfShotResult);

/**
 * A player's ball. The server multicasts the launch; every machine then runs the same
 * fixed-step simulation locally so flight is smooth, and the server's final rest position
 * is authoritative.
 *
 * The ball carries a chase camera that sits behind the ball along its direction of travel.
 */
UCLASS()
class SKYLINKS_API AGolfBall : public AActor
{
	GENERATED_BODY()

public:
	AGolfBall();

	virtual void Tick(float DeltaSeconds) override;
	virtual void BeginPlay() override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Server only. */
	void Launch(const FGolfBallState& State, const FVector& Wind, const FVector& CupLocation, float CupRadius);

	/** Server only: put the ball at rest somewhere (tee, or a drop after a penalty). */
	void PlaceAt(const FVector& Location, bool bOnTee);

	bool IsAtRest() const { return Mode == EMode::Rest; }
	EGolfLie GetLie() const { return RestLie; }
	FVector GetRestLocation() const { return RestLocation; }

	/** Server only: fires when the ball stops, holes out or finds a hazard. */
	FOnGolfBallStopped OnStopped;

	UPROPERTY(VisibleAnywhere, Category = "Golf")
	TObjectPtr<USceneComponent> Root;

	UPROPERTY(VisibleAnywhere, Category = "Golf")
	TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(VisibleAnywhere, Category = "Golf")
	TObjectPtr<USpringArmComponent> ChaseArm;

	UPROPERTY(VisibleAnywhere, Category = "Golf")
	TObjectPtr<UCameraComponent> ChaseCamera;

	/** Drawn size relative to a regulation ball. This is deliberately oversized for readable phone play; physics size is unchanged. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf")
	float VisualScale = 3.f;

	/** How far behind the ball the chase camera trails. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Camera")
	float ChaseDistance = 550.f;

	/** Chase camera pitch, degrees (negative looks down). */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Camera")
	float ChasePitch = -10.f;

	/** How quickly the camera swings round to stay behind the ball. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Camera")
	float ChaseTurnSpeed = 4.f;

protected:
	UFUNCTION(NetMulticast, Reliable)
	void MulticastLaunch(FVector Start, FVector Velocity, FVector SpinAxis, float SpinRate, FVector Wind, FVector CupLocation, float InCupRadius);

	UFUNCTION(NetMulticast, Reliable)
	void MulticastSettle(FVector Location);

	UFUNCTION()
	void OnRep_RestLocation();

	UPROPERTY(ReplicatedUsing = OnRep_RestLocation)
	FVector RestLocation = FVector::ZeroVector;

	UPROPERTY(Replicated)
	EGolfLie RestLie = EGolfLie::Tee;

private:
	enum class EMode : uint8 { Rest, Flight, Roll, Holing };

	void Simulate(float Dt);
	void StepFlightMode(float Dt);
	void StepRollMode(float Dt);
	void StepHoling(float Dt);
	void BeginHoling();
	void Finish(EGolfShotResult Result);
	bool IsOverCup() const;
	EGolfLie ProbeLie(const FVector& At) const;
	void UpdateChaseCamera(float DeltaSeconds, bool bSnap);

	EMode Mode = EMode::Rest;
	FGolfBallState Sim;
	/** Below this height (60 m under the shot's start) the ball has fallen off the islands. */
	float FallLimit = -6000.f;
	FVector SimWind = FVector::ZeroVector;

	/** After landing on top of a canopy the ball drops through that tree's leaves for a moment. */
	TWeakObjectPtr<const AActor> PassThrough;
	float PassThroughUntil = 0.f;
	FVector Cup = FVector::ZeroVector;
	float CupRadius = 8.f;
	float Accumulator = 0.f;
	float SimTime = 0.f;
	float RestTimer = 0.f;
	float HolingTime = 0.f;
	FVector HolingStart = FVector::ZeroVector;
	float ChaseYaw = 0.f;
};
