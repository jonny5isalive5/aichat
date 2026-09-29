#pragma once

#include "CoreMinimal.h"
#include "GolfTypes.generated.h"

UENUM(BlueprintType)
enum class EGolfLie : uint8
{
	Tee,
	Fairway,
	Rough,
	Bunker,
	Green,
	Water,
	OutOfBounds
};

UENUM(BlueprintType)
enum class EGolfShotResult : uint8
{
	Resting,
	Holed,
	Water,
	OutOfBounds
};

UENUM(BlueprintType)
enum class EGolfMatchPhase : uint8
{
	Lobby,
	PlayingHole,
	HoleSummary,
	RoundOver
};

/** Which golfer animation a shot uses. */
UENUM(BlueprintType)
enum class EGolferSwing : uint8
{
	Drive,
	Chip,
	Putt
};

/** Golfer animations played after a shot finishes. */
UENUM(BlueprintType)
enum class EGolferReaction : uint8
{
	None,
	HoleInOne,
	Celebrate,
	PuttVictory,
	PuttMiss,
	BadShot,
	/** Pushing a tee into the ground on the first tee: starts the round. */
	TeeUp
};

USTRUCT(BlueprintType)
struct FGolfClub
{
	GENERATED_BODY()

	/** Label on the club disc, e.g. "1W", "7I", "PT". */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Golf")
	FString ShortName;

	/** Ball speed at 100% power, cm/s. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Golf")
	float LaunchSpeed = 0.f;

	/** Launch angle, degrees. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Golf")
	float LaunchAngle = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Golf")
	float BackspinRpm = 0.f;

	/** Direction error, degrees, at the worst possible impact timing. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Golf")
	float ErrorDegrees = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Golf")
	bool bIsPutter = false;
};

/** Everything the client sends to the server when it swings. The server re-validates all of it. */
USTRUCT(BlueprintType)
struct FGolfShotInput
{
	GENERATED_BODY()

	UPROPERTY()
	float AimYaw = 0.f;

	/** 0..1, up to 1.1 in the overdrive zone. */
	UPROPERTY()
	float Power = 0.f;

	/** -1..1 from the impact tap. 0 is perfect; negative hooks, positive slices. */
	UPROPERTY()
	float Accuracy = 0.f;

	UPROPERTY()
	int32 ClubIndex = 0;

	/** X: side spin (-1 draw .. 1 fade). Y: -1 backspin .. 1 topspin. */
	UPROPERTY()
	FVector2D Spin = FVector2D::ZeroVector;
};
