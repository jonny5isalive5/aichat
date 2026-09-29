#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SkyLinksGrass.generated.h"

class UInstancedStaticMeshComponent;
class UStaticMesh;

/**
 * Real 3D grass, grown at runtime around the camera: blade clumps on the rough, and taller tufts along the lips
 * of the bunkers. The ground is split into square cells; as a cell comes into range it is filled by tracing
 * down onto the islands and keeping the points whose physical surface is rough (or fairway / green right next to
 * sand), and when it falls out of range its instances go back to a pool. Nothing is stored in the level and the
 * grass never touches the ball or the buggy. Spawned by the HUD on every machine (it is purely visual).
 */
UCLASS()
class SKYLINKS_API ASkyLinksGrass : public AActor
{
	GENERATED_BODY()

public:
	ASkyLinksGrass();
	virtual void Tick(float DeltaSeconds) override;

	/** Clumps per square metre of rough. */
	UPROPERTY(EditAnywhere, Category = "Grass")
	float RoughDensity = 4.5f;

	/** Tufts per metre of bunker edge (they sit on the grass just outside the sand). */
	UPROPERTY(EditAnywhere, Category = "Grass")
	float LipDensity = 8.f;

	/** Grass is grown within this distance of the camera (cm). */
	UPROPERTY(EditAnywhere, Category = "Grass")
	float Radius = 6000.f;

	UPROPERTY(EditAnywhere, Category = "Grass")
	float CellSize = 800.f;

	/** Line traces allowed per frame while filling cells. */
	UPROPERTY(EditAnywhere, Category = "Grass")
	int32 TraceBudget = 4000;

	UPROPERTY(EditAnywhere, Category = "Grass")
	TSoftObjectPtr<UStaticMesh> ClumpMesh;

	UPROPERTY(EditAnywhere, Category = "Grass")
	TSoftObjectPtr<UStaticMesh> TuftMesh;

protected:
	virtual void BeginPlay() override;

private:
	struct FCell
	{
		UInstancedStaticMeshComponent* Clumps = nullptr;
		UInstancedStaticMeshComponent* Tufts = nullptr;
	};

	bool GetViewLocation(FVector& Out) const;
	void FillCell(const FIntPoint& Key, float ViewZ, int32& Traces);
	UInstancedStaticMeshComponent* TakeComponent(UStaticMesh* Mesh, TArray<UInstancedStaticMeshComponent*>& Pool);
	void ReleaseCell(FCell& Cell);

	UPROPERTY(Transient)
	TObjectPtr<UStaticMesh> LoadedClump;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMesh> LoadedTuft;

	/** Every component this actor made, so none is garbage collected while pooled. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UInstancedStaticMeshComponent>> AllComponents;

	TMap<FIntPoint, FCell> Cells;
	TArray<UInstancedStaticMeshComponent*> ClumpPool;
	TArray<UInstancedStaticMeshComponent*> TuftPool;
};
