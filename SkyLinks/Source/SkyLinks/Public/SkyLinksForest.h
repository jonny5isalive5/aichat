#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SkyLinksForest.generated.h"

class UHierarchicalInstancedStaticMeshComponent;
class UStaticMesh;
class UFoliageType;

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

	/**
	 * Editor: hand every tree to the level's foliage, then delete this actor. In Foliage mode (Select tool) each
	 * tree can then be picked and moved on its own, and the brush paints more; they stay instanced. Types are
	 * the foliage types (Scripts/import_trees.py, FT_*) whose meshes match the trees. Returns trees moved.
	 */
	UFUNCTION(BlueprintCallable, Category = "SkyLinks|Forest")
	int32 ConvertToFoliage(const TArray<UFoliageType*>& Types);

	/** Editor: remove every foliage instance of these types from the world (before replanting the course). */
	UFUNCTION(BlueprintCallable, Category = "SkyLinks|Forest", meta = (WorldContext = "WorldContextObject"))
	static void ClearFoliage(UObject* WorldContextObject, const TArray<UFoliageType*>& Types);

	/** Editor: remove the foliage instances of these types that stand inside an outline (world XY, cm), e.g. one
	 * island, leaving every other island's trees alone. Returns how many were removed. */
	UFUNCTION(BlueprintCallable, Category = "SkyLinks|Forest", meta = (WorldContext = "WorldContextObject"))
	static int32 ClearFoliageInside(UObject* WorldContextObject, const TArray<UFoliageType*>& Types, const TArray<FVector2D>& Outline);

	/** Trees fade out beyond this distance (cm). */
	UPROPERTY(EditAnywhere, Category = "SkyLinks|Forest")
	float CullDistance = 90000.f;

private:
	UHierarchicalInstancedStaticMeshComponent* ComponentFor(UStaticMesh* Mesh);
};
