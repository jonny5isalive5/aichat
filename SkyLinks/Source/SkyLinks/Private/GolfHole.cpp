#include "GolfHole.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
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

	CupMesh = MakePart(TEXT("CupMesh"), Cylinder.Object, FVector(0.f, 0.f, 0.2f), FVector(0.108f, 0.108f, 0.004f));
	FlagPole = MakePart(TEXT("FlagPole"), Cylinder.Object, FVector(0.f, 0.f, 107.f), FVector(0.025f, 0.025f, 2.13f));
	Flag = MakePart(TEXT("Flag"), Cube.Object, FVector(0.f, 40.f, 185.f), FVector(0.01f, 0.8f, 0.55f));
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
	UMaterialInterface* Base = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	auto Tint = [this, Base](UStaticMeshComponent* Part, const FLinearColor& Color)
	{
		if (Part && Part->GetStaticMesh() && Base)
		{
			UMaterialInstanceDynamic* Material = UMaterialInstanceDynamic::Create(Base, this);
			Material->SetVectorParameterValue(TEXT("Color"), Color);
			Part->SetMaterial(0, Material);
		}
	};
	Tint(CupMesh, FLinearColor(0.01f, 0.01f, 0.01f));
	Tint(FlagPole, FLinearColor(0.95f, 0.95f, 0.9f));
	Tint(Flag, FLinearColor(1.f, 0.8f, 0.f));
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
