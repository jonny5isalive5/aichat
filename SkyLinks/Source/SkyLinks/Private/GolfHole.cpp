#include "GolfHole.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"

AGolfHole::AGolfHole()
{
	PrimaryActorTick.bCanEverTick = false;

	TeeRoot = CreateDefaultSubobject<USceneComponent>(TEXT("TeeRoot"));
	RootComponent = TeeRoot;

	CupRoot = CreateDefaultSubobject<USceneComponent>(TEXT("CupRoot"));
	CupRoot->SetupAttachment(TeeRoot);
	CupRoot->SetRelativeLocation(FVector(30000.f, 0.f, 0.f));

	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));

	auto MakePart = [this](const TCHAR* Name, UStaticMesh* PartMesh, const FVector& Location, const FVector& Scale)
	{
		UStaticMeshComponent* Part = CreateDefaultSubobject<UStaticMeshComponent>(Name);
		Part->SetupAttachment(CupRoot);
		Part->SetStaticMesh(PartMesh);
		Part->SetRelativeLocation(Location);
		Part->SetRelativeScale3D(Scale);
		Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		return Part;
	};

	CupMesh = MakePart(TEXT("CupMesh"), Cylinder.Object, FVector(0.f, 0.f, 0.2f), FVector(0.22f, 0.22f, 0.004f));
	FlagPole = MakePart(TEXT("FlagPole"), Cylinder.Object, FVector(0.f, 0.f, 120.f), FVector(0.03f, 0.03f, 2.4f));
	Flag = MakePart(TEXT("Flag"), Cube.Object, FVector(0.f, 32.f, 215.f), FVector(0.02f, 0.6f, 0.4f));
	CupMesh->SetCastShadow(false);
}

void AGolfHole::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	ApplyColors();
}

void AGolfHole::BeginPlay()
{
	Super::BeginPlay();
	ApplyColors();
}

void AGolfHole::ApplyColors()
{
	auto Tint = [](UStaticMeshComponent* Part, const FLinearColor& Color)
	{
		if (Part && Part->GetStaticMesh())
		{
			if (UMaterialInstanceDynamic* Material = Part->CreateAndSetMaterialInstanceDynamic(0))
			{
				Material->SetVectorParameterValue(TEXT("Color"), Color);
			}
		}
	};
	Tint(CupMesh, FLinearColor(0.01f, 0.01f, 0.01f));
	Tint(FlagPole, FLinearColor(0.95f, 0.95f, 0.9f));
	Tint(Flag, FLinearColor(0.95f, 0.15f, 0.1f));
}

FVector AGolfHole::GetTeeLocation() const
{
	return TeeRoot->GetComponentLocation();
}

FVector AGolfHole::GetCupLocation() const
{
	return CupRoot->GetComponentLocation();
}

float AGolfHole::GetDefaultAimYaw(const FVector& From) const
{
	const bool bFromTee = FVector::Dist2D(From, GetTeeLocation()) < 500.f;
	const FVector Target = bFromTee ? GetActorTransform().TransformPosition(AimPoint) : GetCupLocation();
	return (Target - From).GetSafeNormal2D().Rotation().Yaw;
}
