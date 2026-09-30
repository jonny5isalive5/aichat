#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SkyLinksPortal.generated.h"

class UStaticMeshComponent;
class UTextRenderComponent;

/**
 * A portal between islands: drive the buggy (or walk) through the ring and you come out of the Target portal
 * on the next island, heading the same way relative to it and at the same speed. The actor's origin is on the
 * ground at the foot of the ring and it faces (+X) the way you drive through it. Entry portals have a Target;
 * arrival portals don't (they are one-way, so you can't bounce straight back).
 *
 * The buggy checks for portals itself while it drives (it is simulated on the driver's machine); players on foot
 * are teleported by the portal on the server. Placed by Scripts/apply_floating_islands.py (isl.portals()).
 */
UCLASS()
class SKYLINKS_API ASkyLinksPortal : public AActor
{
	GENERATED_BODY()

public:
	ASkyLinksPortal();
	virtual void Tick(float DeltaSeconds) override;

	/** Where you come out. None: an arrival portal (nothing happens when you go through it). */
	UPROPERTY(EditAnywhere, Category = "Portal")
	TObjectPtr<ASkyLinksPortal> Target;

	/** Half the width of the opening (cm). */
	UPROPERTY(EditAnywhere, Category = "Portal")
	float OpeningRadius = 260.f;

	/** Height of the opening above the ground (cm). */
	UPROPERTY(EditAnywhere, Category = "Portal")
	float OpeningHeight = 520.f;

	/** Height of the hologram sign above the ground (cm). */
	UPROPERTY(EditAnywhere, Category = "Portal")
	float HologramHeight = 700.f;

	/** How far in front of the target portal you come out (cm). */
	UPROPERTY(EditAnywhere, Category = "Portal")
	float ExitDistance = 450.f;

	/** The hologram sign floating above the ring, e.g. "HOLE 2 >" (set by the editor script). */
	UPROPERTY(EditAnywhere, Category = "Portal")
	FString Sign;

	/** The stone ring and its swirling surface (looks only, no collision). */
	UPROPERTY(VisibleAnywhere, Category = "Portal")
	TObjectPtr<UStaticMeshComponent> Ring;

	UPROPERTY(VisibleAnywhere, Category = "Portal")
	TObjectPtr<UTextRenderComponent> Hologram;

	/** The entry portal whose opening the segment From -> To passes through going forward, if any. */
	static ASkyLinksPortal* FindCrossed(const UWorld* World, const FVector& From, const FVector& To);

	/** Where something that entered this portal at Location with Rotation comes out (ground height of the
	 *  target's base; callers settle it onto the ground themselves). */
	void ExitFor(const FVector& Location, const FRotator& Rotation, FVector& OutLocation, FRotator& OutRotation) const;

	/** True when Location is where something leaving some portal would come out (server check on a driver's hop). */
	static bool IsNearAnExit(const UWorld* World, const FVector& Location, float Tolerance);

protected:
	virtual void BeginPlay() override;
	virtual void OnConstruction(const FTransform& Transform) override;

private:
	bool Crossed(const FVector& From, const FVector& To) const;

	void FaceHologram(float DeltaSeconds);
	float HologramTime = 0.f;

	/** Server: where each walking golfer was last tick, to see who stepped through. */
	TMap<TWeakObjectPtr<AActor>, FVector> Walkers;
};
