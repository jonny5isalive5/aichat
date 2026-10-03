#include "SkyLinksDew.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
	constexpr float StripStep = 10.f;   // cm of roll per strip
	constexpr float StripLift = 0.6f;   // cm above the grass (no flicker against it)
}

ASkyLinksDew::ASkyLinksDew()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = false;

	Strips = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Strips"));
	SetRootComponent(Strips);
	Strips->SetMobility(EComponentMobility::Movable);
	Strips->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Strips->SetCastShadow(false);
	Strips->SetCanEverAffectNavigation(false);
	Strips->bHiddenInSceneCapture = true;  // not in the minimap / landing views

	static ConstructorHelpers::FObjectFinder<UStaticMesh> Plane(TEXT("/Engine/BasicShapes/Plane.Plane"));
	if (Plane.Succeeded())
	{
		Strips->SetStaticMesh(Plane.Object);
	}
	// Made by Scripts/apply_floating_islands.py (isl.dew()); without it the trails aren't drawn.
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> Trail(TEXT("/Game/Course/Materials/M_DewTrail.M_DewTrail"));
	if (Trail.Succeeded())
	{
		Strips->SetMaterial(0, Trail.Object);
	}
	else
	{
		Strips->SetVisibility(false);
	}
}

ASkyLinksDew* ASkyLinksDew::Get(UWorld* World)
{
	if (!World || IsRunningDedicatedServer() || !World->IsGameWorld())
	{
		return nullptr;
	}
	for (TActorIterator<ASkyLinksDew> It(World); It; ++It)
	{
		return *It;
	}
	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	return World->SpawnActor<ASkyLinksDew>(FVector::ZeroVector, FRotator::ZeroRotator, Params);
}

void ASkyLinksDew::Touch(UWorld* World, const void* Ball, const FVector& Point, const FVector& Normal, float Width)
{
	ASkyLinksDew* Dew = Get(World);
	if (!Dew)
	{
		return;
	}
	FVector* End = Dew->LineEnds.Find(Ball);
	if (!End)
	{
		Dew->LineEnds.Add(Ball, Point);
		return;
	}
	if (FVector::DistSquared(*End, Point) >= StripStep * StripStep)
	{
		Dew->AddStrip(*End, Point, Normal, Width);
		*End = Point;
	}
}

void ASkyLinksDew::Lift(UWorld* World, const void* Ball)
{
	if (ASkyLinksDew* Dew = Get(World))
	{
		Dew->LineEnds.Remove(Ball);
	}
}

void ASkyLinksDew::Splash(UWorld* World, const FVector& Point, const FVector& Normal, float Size)
{
	ASkyLinksDew* Dew = Get(World);
	if (!Dew)
	{
		return;
	}
	// A short wide strip: the material fades it out at both sides, so it reads as a soft smudge.
	const FVector Along = FVector::VectorPlaneProject(FVector::ForwardVector, Normal).GetSafeNormal();
	Dew->AddStrip(Point - Along * Size * 0.35f, Point + Along * Size * 0.35f, Normal, Size);
}

void ASkyLinksDew::AddStrip(const FVector& From, const FVector& To, const FVector& Normal, float Width)
{
	const FVector Along = To - From;
	const float Length = Along.Size();
	if (Length < KINDA_SMALL_NUMBER)
	{
		return;
	}
	const FVector Up = Normal.GetSafeNormal();
	const FRotator Facing = FRotationMatrix::MakeFromXZ(Along / Length, Up).Rotator();
	// The engine plane is 1 m square, lying flat: stretch it along the roll (a touch long, so strips overlap
	// and the line has no gaps) and squeeze it to the width.
	const FTransform Strip(Facing, (From + To) * 0.5f + Up * StripLift,
	                       FVector((Length + 2.f) / 100.f, Width / 100.f, 1.f));
	if (Strips->GetInstanceCount() < MaxStrips)
	{
		Strips->AddInstance(Strip, true);
	}
	else
	{
		Strips->UpdateInstanceTransform(NextReuse, Strip, true, true, true);
		NextReuse = (NextReuse + 1) % MaxStrips;
	}
}
