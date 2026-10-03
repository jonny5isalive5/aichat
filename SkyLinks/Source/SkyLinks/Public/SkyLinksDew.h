#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SkyLinksDew.generated.h"

class UInstancedStaticMeshComponent;

/**
 * Morning dew trails: where a ball lands on the fairway, green or tee it leaves a splash, and where it rolls a
 * darker line, the dew brushed off the grass. Each trail is a run of thin flat strips (one instanced mesh, so
 * thousands cost one draw call) in M_DewTrail, a Modulate material that darkens what's under it.
 *
 * Every machine simulates the balls itself (AGolfBall), so every machine draws every trail: nothing replicates.
 * One of these is spawned on demand per world (none on a dedicated server). The newest MaxStrips pieces stay;
 * after that the oldest are reused, so the course fills with ball paths as the round goes on.
 */
UCLASS(NotPlaceable, Transient)
class SKYLINKS_API ASkyLinksDew : public AActor
{
	GENERATED_BODY()

public:
	ASkyLinksDew();

	/** Ball (any key, one per ball) touching dewy grass at Point: extends that ball's line. */
	static void Touch(UWorld* World, const void* Ball, const FVector& Point, const FVector& Normal, float Width);

	/** The ball left the dew (bounced up, rolled into the rough, stopped): its next touch starts a new line. */
	static void Lift(UWorld* World, const void* Ball);

	/** A landing: a splash where the ball hit, Size across. */
	static void Splash(UWorld* World, const FVector& Point, const FVector& Normal, float Size);

	/** How many strips are kept before the oldest are reused. */
	UPROPERTY(EditAnywhere, Category = "Dew")
	int32 MaxStrips = 5000;

private:
	static ASkyLinksDew* Get(UWorld* World);
	void AddStrip(const FVector& From, const FVector& To, const FVector& Normal, float Width);

	UPROPERTY()
	TObjectPtr<UInstancedStaticMeshComponent> Strips;

	/** Where each ball's line got to. */
	TMap<const void*, FVector> LineEnds;
	int32 NextReuse = 0;
};
