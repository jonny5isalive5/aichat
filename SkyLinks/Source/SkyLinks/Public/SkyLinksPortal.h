#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SkyLinksPortal.generated.h"

class UStaticMeshComponent;
class UTextRenderComponent;

/**
 * A portal between islands: drive the buggy (or walk) through the ring and you come out of its Target portal
 * on the other island, heading the same way relative to it and at the same speed. Pairs point at each other,
 * so they work both ways: through the end-of-hole portal to the next tee, and back again. The actor's origin is
 * on the ground at the foot of the ring; it faces (+X) the way you travel on to the next hole, and whichever way
 * you go through one, you come out of the other on the far side going the same way.
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

	/** Where you come out (the other portal of the pair). None: a portal that goes nowhere. */
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

	/** The hologram sign floating above the ring, e.g. "HOLE 2  THIS WAY" (set by the editor script). */
	UPROPERTY(EditAnywhere, Category = "Portal")
	FString Sign;

	/** The sign reads towards the side you drive in from: the back (-X) for the portal that leads on to the next
	 *  hole, the front (+X) for the one by the tee that leads back. */
	UPROPERTY(EditAnywhere, Category = "Portal")
	bool bSignFacesBack = false;

	/** The stone ring and its swirling surface (looks only, no collision). */
	UPROPERTY(VisibleAnywhere, Category = "Portal")
	TObjectPtr<UStaticMeshComponent> Ring;

	UPROPERTY(VisibleAnywhere, Category = "Portal")
	TObjectPtr<UTextRenderComponent> Hologram;

	/** The portal whose opening the segment From -> To passes through, if any, and which way
	 *  (OutDirection +1: the way it faces, -1: the other way). */
	static ASkyLinksPortal* FindCrossed(const UWorld* World, const FVector& From, const FVector& To, int32& OutDirection);

	/** Where something that went through this portal (Direction as from FindCrossed) at Location with Rotation
	 *  comes out (ground height of the target's base; callers settle it onto the ground themselves). */
	void ExitFor(const FVector& Location, const FRotator& Rotation, int32 Direction, FVector& OutLocation, FRotator& OutRotation) const;

	/** The ground under Location (trees and the like ignored), searched from well above it so a spot on rising
	 *  ground isn't missed. Returns false if there's none; OutGround is on the surface. */
	static bool FindGround(const UWorld* World, const FVector& Location, FVector& OutGround, const AActor* Ignore = nullptr);

	/** True when Location is where something leaving some portal would come out (server check on a driver's hop). */
	static bool IsNearAnExit(const UWorld* World, const FVector& Location, float Tolerance);

protected:
	virtual void BeginPlay() override;
	virtual void OnConstruction(const FTransform& Transform) override;

private:
	/** +1 / -1 if From -> To goes through the opening (with / against the way it faces), else 0. */
	int32 Crossing(const FVector& From, const FVector& To) const;

	void FaceHologram(float DeltaSeconds);
	float HologramTime = 0.f;

	/** Server: where each walking golfer was last tick, to see who stepped through. */
	TMap<TWeakObjectPtr<AActor>, FVector> Walkers;
};
