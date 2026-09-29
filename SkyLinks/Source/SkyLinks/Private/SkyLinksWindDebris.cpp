#include "SkyLinksWindDebris.h"
#include "SkyLinks.h"
#include "GolfGameState.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Camera/PlayerCameraManager.h"

ASkyLinksWindDebris::ASkyLinksWindDebris()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
	LeafMesh = TSoftObjectPtr<UStaticMesh>(FSoftObjectPath(TEXT("/Game/Course/Grass/SM_WindLeaf.SM_WindLeaf")));
	StrawMesh = TSoftObjectPtr<UStaticMesh>(FSoftObjectPath(TEXT("/Game/Course/Grass/SM_WindStraw.SM_WindStraw")));
}

void ASkyLinksWindDebris::BeginPlay()
{
	Super::BeginPlay();
	UStaticMesh* Leaf = LeafMesh.LoadSynchronous();
	UStaticMesh* Straw = StrawMesh.LoadSynchronous();
	if (!Leaf || !Straw)
	{
		UE_LOG(LogSkyLinks, Warning, TEXT("SkyLinksWindDebris: meshes not found (run isl.import_grass() in the editor). No wind debris."));
		SetActorTickEnabled(false);
		return;
	}
	Leaves = MakeComponent(Leaf, LeafCount, LeafFlakes);
	Straws = MakeComponent(Straw, StrawCount, StrawFlakes);
}

UInstancedStaticMeshComponent* ASkyLinksWindDebris::MakeComponent(UStaticMesh* Mesh, int32 Count, TArray<FFlake>& Out)
{
	UInstancedStaticMeshComponent* Component = NewObject<UInstancedStaticMeshComponent>(this);
	Component->SetStaticMesh(Mesh);
	Component->SetMobility(EComponentMobility::Movable);
	Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Component->SetCanEverAffectNavigation(false);
	Component->SetCastShadow(false);
	Component->SetupAttachment(GetRootComponent());
	Component->RegisterComponent();

	TArray<FTransform> Start;
	for (int32 Index = 0; Index < Count; ++Index)
	{
		FFlake Flake;
		Flake.Offset = FVector(FMath::FRandRange(-Extent, Extent), FMath::FRandRange(-Extent, Extent), FMath::FRandRange(-300.f, 1400.f));
		Flake.Axis = FMath::VRand();
		Flake.Phase = FMath::FRandRange(0.f, 2.f * PI);
		Flake.Spin = FMath::FRandRange(2.f, 7.f);
		Flake.Drag = FMath::FRandRange(0.6f, 1.1f);
		Flake.Scale = FMath::FRandRange(1.6f, 2.8f);
		Out.Add(Flake);
		Start.Add(FTransform(FQuat::Identity, Flake.Offset, FVector(Flake.Scale)));
	}
	Component->AddInstances(Start, false, true);
	return Component;
}

void ASkyLinksWindDebris::Step(TArray<FFlake>& Flakes, UInstancedStaticMeshComponent* Component, const FVector& View, const FVector& Wind, float Time, float DeltaSeconds)
{
	if (!Component)
	{
		return;
	}
	Scratch.Reset(Flakes.Num());
	for (FFlake& Flake : Flakes)
	{
		// Carried by the wind, with gusty swirls, a slow sink and a flutter up and down.
		const float T = Time + Flake.Phase * 3.f;
		const FVector Swirl(FMath::Sin(T * 0.9f + Flake.Phase) * 90.f, FMath::Cos(T * 0.7f + Flake.Phase * 1.7f) * 90.f,
			FMath::Sin(T * 2.3f + Flake.Phase) * 70.f - 35.f);
		Flake.Offset += (Wind * Flake.Drag + Swirl) * DeltaSeconds;
		// The box follows the camera; anything that leaves one side comes back in on the other.
		for (int32 Axis = 0; Axis < 2; ++Axis)
		{
			if (Flake.Offset[Axis] > Extent) Flake.Offset[Axis] -= 2.f * Extent;
			if (Flake.Offset[Axis] < -Extent) Flake.Offset[Axis] += 2.f * Extent;
		}
		if (Flake.Offset.Z < -300.f) Flake.Offset.Z += 1700.f;
		if (Flake.Offset.Z > 1400.f) Flake.Offset.Z -= 1700.f;
		const FQuat Tumble(Flake.Axis, T * Flake.Spin * 0.35f + Flake.Phase);
		Scratch.Add(FTransform(Tumble, View + Flake.Offset, FVector(Flake.Scale)));
	}
	Component->BatchUpdateInstancesTransforms(0, Scratch, true, true, true);
}

void ASkyLinksWindDebris::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const APlayerController* Controller = GetWorld()->GetFirstPlayerController();
	if (!Controller || !Controller->PlayerCameraManager)
	{
		return;
	}
	const FVector View = Controller->PlayerCameraManager->GetCameraLocation();
	// Offsets are kept relative to the camera; when the camera moves they stay put in the world.
	const FVector Moved = View - LastView;
	if (LastView.IsZero() || Moved.Size() > 5000.f)
	{
		LastView = View;  // first frame or a camera cut: just carry the box along
	}
	else
	{
		for (FFlake& Flake : LeafFlakes) Flake.Offset -= Moved;
		for (FFlake& Flake : StrawFlakes) Flake.Offset -= Moved;
		LastView = View;
	}

	FVector Wind = FVector::ZeroVector;
	if (const AGolfGameState* State = GetWorld()->GetGameState<AGolfGameState>())
	{
		Wind = State->Wind;
	}
	if (Wind.Size2D() < 120.f)
	{
		Wind = FVector(120.f, 50.f, 0.f);  // a light breeze even on a calm hole
	}
	Wind.Z = 0.f;
	const float Time = GetWorld()->GetTimeSeconds();
	Step(LeafFlakes, Leaves, View, Wind, Time, DeltaSeconds);
	Step(StrawFlakes, Straws, View, Wind * 1.1f, Time, DeltaSeconds);
}
