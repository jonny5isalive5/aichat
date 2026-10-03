#include "SkyLinksGrass.h"
#include "SkyLinks.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Camera/PlayerCameraManager.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "Kismet/GameplayStatics.h"

namespace
{
	constexpr float GrassProbeSpacing = 60.f;   // cm between the bunker-finding probes
	constexpr float GrassTraceUp = 20000.f;     // traces run from well above the camera...
	constexpr float GrassTraceDown = 60000.f;   // ...to well below it (islands float at different heights)
	constexpr int32 PathUVChannel = 3;          // island tops: UV3.x = signed metres to the buggy path's edge (negative on it)
	constexpr float PathClearance = 0.3f;       // m: keep the grass this far off the path's edge

	/** True where the hit is on (or right beside) a buggy path, read from the island's path UV (needs
	 *  bSupportUVFromHitResults in DefaultEngine.ini; without it nothing counts as path). */
	bool OnPath(const FHitResult& Hit)
	{
		FVector2D UV;
		return UGameplayStatics::FindCollisionUV(Hit, PathUVChannel, UV) && UV.X < PathClearance;
	}
}

ASkyLinksGrass::ASkyLinksGrass()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
	ClumpMesh = TSoftObjectPtr<UStaticMesh>(FSoftObjectPath(TEXT("/Game/Course/Grass/SM_GrassClump.SM_GrassClump")));
	TuftMesh = TSoftObjectPtr<UStaticMesh>(FSoftObjectPath(TEXT("/Game/Course/Grass/SM_GrassTuft.SM_GrassTuft")));
	PatchMesh = TSoftObjectPtr<UStaticMesh>(FSoftObjectPath(TEXT("/Game/Course/Grass/SM_GrassPatch.SM_GrassPatch")));
}

void ASkyLinksGrass::BeginPlay()
{
	Super::BeginPlay();
	LoadedClump = ClumpMesh.LoadSynchronous();
	LoadedTuft = TuftMesh.LoadSynchronous();
	LoadedPatch = PatchMesh.LoadSynchronous();  // optional: without it the near rough gets extra clumps instead
	if (!LoadedClump)
	{
		UE_LOG(LogSkyLinks, Warning, TEXT("SkyLinksGrass: %s not found (run isl.import_grass() in the editor). No 3D grass."), *ClumpMesh.ToString());
		SetActorTickEnabled(false);
	}
}

bool ASkyLinksGrass::GetViewLocation(FVector& Out) const
{
	const APlayerController* Controller = GetWorld()->GetFirstPlayerController();
	if (!Controller || !Controller->PlayerCameraManager)
	{
		return false;
	}
	Out = Controller->PlayerCameraManager->GetCameraLocation();
	return true;
}

void ASkyLinksGrass::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	FVector View;
	if (!GetViewLocation(View))
	{
		return;
	}

	// Drop cells that have fallen well out of range (a margin so they don't flicker at the boundary).
	const float Keep = Radius + CellSize * 1.5f;
	for (auto It = Cells.CreateIterator(); It; ++It)
	{
		const FVector2D Centre = (FVector2D(It.Key()) + FVector2D(0.5f, 0.5f)) * CellSize;
		if (FVector2D::Distance(Centre, FVector2D(View)) > Keep)
		{
			ReleaseCell(It.Value());
			It.RemoveCurrent();
		}
	}

	// Fill missing cells nearest first, within this frame's trace budget. A cell that has come within NearRadius
	// (or gone back out past it, with a cell's width of slack so it doesn't flip back and forth) is grown again.
	const int32 Reach = FMath::CeilToInt(Radius / CellSize);
	const FIntPoint Here(FMath::FloorToInt(View.X / CellSize), FMath::FloorToInt(View.Y / CellSize));
	TArray<TPair<float, FIntPoint>> Missing;
	for (int32 DY = -Reach; DY <= Reach; ++DY)
	{
		for (int32 DX = -Reach; DX <= Reach; ++DX)
		{
			const FIntPoint Key(Here.X + DX, Here.Y + DY);
			const FVector2D Centre = (FVector2D(Key) + FVector2D(0.5f, 0.5f)) * CellSize;
			const float Distance = FVector2D::Distance(Centre, FVector2D(View));
			if (const FCell* Existing = Cells.Find(Key))
			{
				const bool bRegrow = Existing->bNear ? Distance > NearRadius + CellSize * 1.5f : Distance < NearRadius;
				if (bRegrow)
				{
					Missing.Add({ Distance, Key });
				}
				continue;
			}
			if (Distance < Radius + CellSize * 0.7f)
			{
				Missing.Add({ Distance, Key });
			}
		}
	}
	Missing.Sort([](const TPair<float, FIntPoint>& A, const TPair<float, FIntPoint>& B) { return A.Key < B.Key; });
	int32 Traces = 0;
	for (const TPair<float, FIntPoint>& Entry : Missing)
	{
		if (Traces >= TraceBudget)
		{
			break;
		}
		if (FCell* Existing = Cells.Find(Entry.Value))
		{
			ReleaseCell(*Existing);
			Cells.Remove(Entry.Value);
		}
		FillCell(Entry.Value, View.Z, Entry.Key < NearRadius + CellSize * 0.5f, Traces);
	}
}

UInstancedStaticMeshComponent* ASkyLinksGrass::TakeComponent(UStaticMesh* Mesh, TArray<UInstancedStaticMeshComponent*>& Pool)
{
	if (Pool.Num() > 0)
	{
		return Pool.Pop(EAllowShrinking::No);
	}
	UInstancedStaticMeshComponent* Component = NewObject<UInstancedStaticMeshComponent>(this);
	Component->SetStaticMesh(Mesh);
	Component->SetMobility(EComponentMobility::Movable);
	Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Component->SetCanEverAffectNavigation(false);
	Component->SetCastShadow(false);
	Component->SetCullDistances(0, FMath::RoundToInt(Radius + CellSize));
	Component->SetupAttachment(GetRootComponent());
	Component->RegisterComponent();
	AllComponents.Add(Component);
	return Component;
}

void ASkyLinksGrass::ReleaseCell(FCell& Cell)
{
	if (Cell.Clumps)
	{
		Cell.Clumps->ClearInstances();
		ClumpPool.Add(Cell.Clumps);
	}
	if (Cell.Tufts)
	{
		Cell.Tufts->ClearInstances();
		TuftPool.Add(Cell.Tufts);
	}
	if (Cell.Patches)
	{
		Cell.Patches->ClearInstances();
		PatchPool.Add(Cell.Patches);
	}
	Cell = FCell();
}

float ASkyLinksGrass::Density() const
{
#if PLATFORM_ANDROID || PLATFORM_IOS
	return DensityScale * 0.5f;  // phones: half as thick
#else
	return DensityScale;
#endif
}

void ASkyLinksGrass::FillCell(const FIntPoint& Key, float ViewZ, bool bNear, int32& Traces)
{
	UWorld* World = GetWorld();
	FRandomStream Random(static_cast<int32>(HashCombineFast(GetTypeHash(Key), 0x5EEDu)));
	const FVector2D Origin = FVector2D(Key) * CellSize;

	FCollisionQueryParams Params(SCENE_QUERY_STAT(SkyLinksGrass), true);
	Params.bReturnPhysicalMaterial = true;
	Params.bReturnFaceIndex = true; // FindCollisionUV (OnPath) needs the hit's face; without it every hit reads "not on a path"
	const FCollisionObjectQueryParams Objects(ECC_WorldStatic);
	auto Ground = [&](float X, float Y, FHitResult& Hit, EPhysicalSurface& Surface)
	{
		++Traces;
		if (!World->LineTraceSingleByObjectType(Hit, FVector(X, Y, ViewZ + GrassTraceUp), FVector(X, Y, ViewZ - GrassTraceDown), Objects, Params))
		{
			return false;
		}
		Surface = UPhysicalMaterial::DetermineSurfaceType(Hit.PhysMaterial.Get());
		return true;
	};
	auto Place = [&Random](const FHitResult& Hit, float Scale, float Stretch)
	{
		// Stand on the ground, mostly upright but leaning a little with the slope, any way round.
		const FVector Up = FMath::Lerp(FVector::UpVector, Hit.ImpactNormal, 0.5f).GetSafeNormal();
		const float Yaw = Random.FRand() * 2.f * PI;
		const FRotator Rotation = FRotationMatrix::MakeFromZX(Up, FVector(FMath::Cos(Yaw), FMath::Sin(Yaw), 0.f)).Rotator();
		const float Size = Scale * Random.FRandRange(0.7f, 1.3f);
		return FTransform(Rotation, Hit.ImpactPoint - FVector(0.f, 0.f, 1.f), FVector(Size, Size, Size * Stretch * Random.FRandRange(0.8f, 1.25f)));
	};

	TArray<FTransform> Clumps;
	TArray<FTransform> Tufts;
	TArray<FTransform> Patches;

	// Rough: near the camera a thick carpet of wide patches; further out, clumps scattered at random.
	const bool bPatches = bNear && LoadedPatch;
	const float PerSquareMetre = (bNear ? (LoadedPatch ? NearDensity : RoughDensity * 2.f) : RoughDensity) * Density();
	const int32 Count = FMath::RoundToInt(PerSquareMetre * CellSize * CellSize / 10000.f);
	for (int32 Index = 0; Index < Count; ++Index)
	{
		FHitResult Hit;
		EPhysicalSurface Surface;
		if (Ground(Origin.X + Random.FRand() * CellSize, Origin.Y + Random.FRand() * CellSize, Hit, Surface) && Surface == SURFACE_Rough && !OnPath(Hit))
		{
			(bPatches ? Patches : Clumps).Add(Place(Hit, 1.f, 1.f));
		}
	}

	// Bunker lips: probe a fine grid for sand; every grass probe beside a sand probe gets a few tufts.
	if (LoadedTuft)
	{
		const int32 Side = FMath::CeilToInt(CellSize / GrassProbeSpacing);
		TArray<uint8> Sand;
		Sand.SetNumZeroed((Side + 2) * (Side + 2));
		// Probes include a ring just outside the cell, so edges on the cell border are found from both sides.
		for (int32 Y = -1; Y <= Side; ++Y)
		{
			for (int32 X = -1; X <= Side; ++X)
			{
				FHitResult Hit;
				EPhysicalSurface Surface;
				const bool bHit = Ground(Origin.X + (X + 0.5f) * GrassProbeSpacing, Origin.Y + (Y + 0.5f) * GrassProbeSpacing, Hit, Surface);
				Sand[(Y + 1) * (Side + 2) + (X + 1)] = !bHit ? 2 : Surface == SURFACE_Bunker ? 1 : 0;
			}
		}
		const int32 PerProbe = FMath::Max(1, FMath::RoundToInt(LipDensity * GrassProbeSpacing / 100.f));
		for (int32 Y = 0; Y < Side; ++Y)
		{
			for (int32 X = 0; X < Side; ++X)
			{
				auto At = [&](int32 PX, int32 PY) { return Sand[(PY + 1) * (Side + 2) + (PX + 1)]; };
				if (At(X, Y) != 0 || (At(X - 1, Y) != 1 && At(X + 1, Y) != 1 && At(X, Y - 1) != 1 && At(X, Y + 1) != 1))
				{
					continue;
				}
				for (int32 Tuft = 0; Tuft < PerProbe; ++Tuft)
				{
					FHitResult Hit;
					EPhysicalSurface Surface;
					const float PX = Origin.X + (X + Random.FRand()) * GrassProbeSpacing;
					const float PY = Origin.Y + (Y + Random.FRand()) * GrassProbeSpacing;
					if (Ground(PX, PY, Hit, Surface) && (Surface == SURFACE_Rough || Surface == SURFACE_Fairway || Surface == SURFACE_Green) && !OnPath(Hit))
					{
						Tufts.Add(Place(Hit, 1.f, 1.f));
					}
				}
			}
		}
	}

	FCell Cell;
	Cell.bNear = bNear;
	if (Patches.Num() > 0)
	{
		Cell.Patches = TakeComponent(LoadedPatch, PatchPool);
		Cell.Patches->AddInstances(Patches, false, true);
	}
	if (Clumps.Num() > 0)
	{
		Cell.Clumps = TakeComponent(LoadedClump, ClumpPool);
		Cell.Clumps->AddInstances(Clumps, false, true);
	}
	if (Tufts.Num() > 0)
	{
		Cell.Tufts = TakeComponent(LoadedTuft, TuftPool);
		Cell.Tufts->AddInstances(Tufts, false, true);
	}
	Cells.Add(Key, Cell);
}
