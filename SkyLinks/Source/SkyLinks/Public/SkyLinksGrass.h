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

	/** Clumps per square metre of rough (beyond NearRadius). */
	UPROPERTY(EditAnywhere, Category = "Grass")
	float RoughDensity = 4.5f;

	/** Within this distance of the camera (cm) the rough is a thick carpet of grass patches. */
	UPROPERTY(EditAnywhere, Category = "Grass")
	float NearRadius = 1500.f;

	/** Grass patches per square metre of rough within NearRadius (each patch is 70 blades, 70 cm across). */
	UPROPERTY(EditAnywhere, Category = "Grass")
	float NearDensity = 2.6f;

	/** Everything above times this (phones and tablets use half of it). */
	UPROPERTY(EditAnywhere, Category = "Grass")
	float DensityScale = 1.f;

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

	UPROPERTY(EditAnywhere, Category = "Grass")
	TSoftObjectPtr<UStaticMesh> PatchMesh;

protected:
	virtual void BeginPlay() override;

private:
	struct FCell
	{
		UInstancedStaticMeshComponent* Clumps = nullptr;
		UInstancedStaticMeshComponent* Tufts = nullptr;
		UInstancedStaticMeshComponent* Patches = nullptr;
		bool bNear = false;
	};

	bool GetViewLocation(FVector& Out) const;
	void FillCell(const FIntPoint& Key, float ViewZ, bool bNear, int32& Traces);
	float Density() const;
	UInstancedStaticMeshComponent* TakeComponent(UStaticMesh* Mesh, TArray<UInstancedStaticMeshComponent*>& Pool);
	void ReleaseCell(FCell& Cell);

	UPROPERTY(Transient)
	TObjectPtr<UStaticMesh> LoadedClump;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMesh> LoadedTuft;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMesh> LoadedPatch;

	/** Every component this actor made, so none is garbage collected while pooled. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UInstancedStaticMeshComponent>> AllComponents;

	TMap<FIntPoint, FCell> Cells;
	TArray<UInstancedStaticMeshComponent*> ClumpPool;
	TArray<UInstancedStaticMeshComponent*> TuftPool;
	TArray<UInstancedStaticMeshComponent*> PatchPool;
};
