#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SkyLinksForest.generated.h"

class UHierarchicalInstancedStaticMeshComponent;
class UStaticMesh;

/**
 * All the trees and bushes of one island as instances: one instanced component per mesh, so a whole wood
 * draws in a handful of calls (the only way hundreds of trees run on a phone). Filled by the course scripts
 * (Scripts/apply_floating_islands.py); the trees' UCX_ trunk boxes give the ball something to hit.
 */
UCLASS()
class SKYLINKS_API ASkyLinksForest : public AActor
{
	GENERATED_BODY()

public:
	ASkyLinksForest();

	/** Add instances of Mesh at world transforms. */
	UFUNCTION(BlueprintCallable, Category = "SkyLinks|Forest")
	int32 AddTrees(UStaticMesh* Mesh, const TArray<FTransform>& WorldTransforms);

	/** Remove every tree this forest holds. */
	UFUNCTION(BlueprintCallable, Category = "SkyLinks|Forest")
	void ClearTrees();

	UFUNCTION(BlueprintCallable, Category = "SkyLinks|Forest")
	int32 GetTreeCount() const;

	/** Trees fade out beyond this distance (cm). */
	UPROPERTY(EditAnywhere, Category = "SkyLinks|Forest")
	float CullDistance = 90000.f;

private:
	UHierarchicalInstancedStaticMeshComponent* ComponentFor(UStaticMesh* Mesh);
};
