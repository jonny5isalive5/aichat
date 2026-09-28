#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SkyLinksTree.generated.h"

class UCapsuleComponent;
class USkeletalMesh;
class USkeletalMeshComponent;

/**
 * A tree for painting with Foliage Mode (as Actor Foliage, see Scripts/make_foliage_types.py) or placing by hand.
 * Picks one of its Megaplant variants from where it stands, so a painted forest mixes species and shapes, and
 * keeps a trunk capsule the ball bounces off. The Megaplants are skeletal meshes (for their dynamic wind),
 * which the ordinary static-mesh foliage brush can't paint.
 */
UCLASS()
class SKYLINKS_API ASkyLinksTree : public AActor
{
	GENERATED_BODY()

public:
	ASkyLinksTree();

	virtual void OnConstruction(const FTransform& Transform) override;

	/** Meshes to pick from. */
	UPROPERTY(EditAnywhere, Category = "Tree")
	TArray<TSoftObjectPtr<USkeletalMesh>> Variants;

	/** Which variant to show; -1 picks one from the actor's position (stable when moved back). */
	UPROPERTY(EditAnywhere, Category = "Tree")
	int32 VariantIndex = -1;

	/** Give it a trunk the ball hits (a 30 cm radius, 5 m tall capsule); bushes have none. */
	UPROPERTY(EditAnywhere, Category = "Tree")
	bool bSolidTrunk = true;

	UPROPERTY(VisibleAnywhere, Category = "Tree")
	TObjectPtr<USkeletalMeshComponent> Mesh;

	UPROPERTY(VisibleAnywhere, Category = "Tree")
	TObjectPtr<UCapsuleComponent> Trunk;
};

/** Low shrubs and saplings for painting under and between the trees. No trunk collision. */
UCLASS()
class SKYLINKS_API ASkyLinksBush : public ASkyLinksTree
{
	GENERATED_BODY()

public:
	ASkyLinksBush();
};
