#pragma once

#include "CoreMinimal.h"
#include "GolfTypes.h"

class UWorld;
class AActor;
struct FHitResult;

/** Simulation state of a ball in flight or rolling. Units: cm, cm/s, rad/s. */
struct FGolfBallState
{
	FVector Location = FVector::ZeroVector;
	FVector Velocity = FVector::ZeroVector;
	FVector SpinAxis = FVector::ZeroVector;
	float SpinRate = 0.f;
};

struct FGolfSurfaceParams
{
	float Restitution;
	float BounceFriction;
	/** Rolling resistance, cm/s^2. */
	float RollDecel;
	/** Multiplier on shot power when hitting from this lie. */
	float PowerScale;
};

/**
 * Deterministic ball physics shared by the server, every client and the aim preview.
 * Everything runs at a fixed step so all machines trace the same flight.
 */
namespace GolfPhysics
{
	constexpr float BallRadius = 2.135f;
	constexpr float Gravity = 980.f;
	/** 0.5 * air density * Cd * area / mass, per cm. */
	constexpr float DragK = 4.77e-5f;
	constexpr float DragCoefficient = 0.25f;
	constexpr float SpinDecaySeconds = 5.f;
	constexpr float FixedStep = 1.f / 120.f;
	constexpr float KillZ = -5000.f;

	SKYLINKS_API const TArray<FGolfClub>& GetClubBag();
	SKYLINKS_API int32 GetPutterIndex();
	SKYLINKS_API const FGolfSurfaceParams& GetSurface(EGolfLie Lie);
	SKYLINKS_API EGolfLie LieFromHit(const FHitResult& Hit);
	SKYLINKS_API FString LieName(EGolfLie Lie);

	SKYLINKS_API void StepFlight(FGolfBallState& State, const FVector& Wind, float Dt);
	SKYLINKS_API FGolfBallState MakeLaunch(const FGolfClub& Club, const FGolfShotInput& Input, EGolfLie Lie, const FVector& Start);

	SKYLINKS_API bool SweepBall(const UWorld* World, const FVector& From, const FVector& To, FHitResult& OutHit, const AActor* Ignore);

	/** Flies the ball through the world with no wind and returns where it first touches something. */
	SKYLINKS_API bool PredictCarry(const UWorld* World, FGolfBallState State, const AActor* Ignore, TArray<FVector>& OutPath, FVector& OutLanding);

	/** Full-power carry over flat ground with no wind, in cm. Used for club labels and auto club choice. */
	SKYLINKS_API float FlatCarry(const FGolfClub& Club, EGolfLie Lie);

	/** How far a putt at this speed rolls on a flat green, in cm. */
	SKYLINKS_API float PuttDistance(float Speed);
}
