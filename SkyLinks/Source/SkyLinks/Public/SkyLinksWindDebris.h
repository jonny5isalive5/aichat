#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SkyLinksWindDebris.generated.h"

class UInstancedStaticMeshComponent;
class UStaticMesh;

/**
 * Leaves and bits of dry grass carried on the wind around the camera: they drift with the hole's wind (a light
 * breeze when it is calm), bob, swirl and tumble, and wrap round a box that follows the camera so there are
 * always some in view. Purely visual; spawned by the HUD on every machine.
 */
UCLASS()
class SKYLINKS_API ASkyLinksWindDebris : public AActor
{
	GENERATED_BODY()

public:
	ASkyLinksWindDebris();
	virtual void Tick(float DeltaSeconds) override;

	UPROPERTY(EditAnywhere, Category = "Wind")
	int32 LeafCount = 140;

	UPROPERTY(EditAnywhere, Category = "Wind")
	int32 StrawCount = 90;

	/** Half-size of the box round the camera the debris lives in (cm). */
	UPROPERTY(EditAnywhere, Category = "Wind")
	float Extent = 2600.f;

	UPROPERTY(EditAnywhere, Category = "Wind")
	TSoftObjectPtr<UStaticMesh> LeafMesh;

	UPROPERTY(EditAnywhere, Category = "Wind")
	TSoftObjectPtr<UStaticMesh> StrawMesh;

protected:
	virtual void BeginPlay() override;

private:
	struct FFlake
	{
		FVector Offset;      // from the camera
		FVector Axis;        // tumble axis
		float Phase = 0.f;
		float Spin = 0.f;    // radians a second
		float Drag = 1.f;    // how fully it follows the wind
		float Scale = 1.f;
	};

	UInstancedStaticMeshComponent* MakeComponent(UStaticMesh* Mesh, int32 Count, TArray<FFlake>& Out);
	void Step(TArray<FFlake>& Flakes, UInstancedStaticMeshComponent* Component, const FVector& View, const FVector& Wind, float Time, float DeltaSeconds);

	UPROPERTY(Transient)
	TObjectPtr<UInstancedStaticMeshComponent> Leaves;

	UPROPERTY(Transient)
	TObjectPtr<UInstancedStaticMeshComponent> Straws;

	TArray<FFlake> LeafFlakes;
	TArray<FFlake> StrawFlakes;
	FVector LastView = FVector::ZeroVector;
	TArray<FTransform> Scratch;
};
