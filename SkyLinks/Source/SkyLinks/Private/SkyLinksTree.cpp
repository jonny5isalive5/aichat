#include "SkyLinksTree.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/SkeletalMesh.h"

namespace
{
	TSoftObjectPtr<USkeletalMesh> Megaplant(const TCHAR* Folder, const TCHAR* Name)
	{
		return TSoftObjectPtr<USkeletalMesh>(FSoftObjectPath(FString::Printf(TEXT("/Game/Megaplant_Library/%s/%s.%s"), Folder, Name, Name)));
	}
}

ASkyLinksTree::ASkyLinksTree()
{
	PrimaryActorTick.bCanEverTick = false;

	// The root is the point on the ground, so foliage painting and hand placement both plant it there.
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Ground"));

	Mesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(RootComponent);
	Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	Trunk = CreateDefaultSubobject<UCapsuleComponent>(TEXT("Trunk"));
	Trunk->SetupAttachment(RootComponent);
	Trunk->InitCapsuleSize(30.f, 250.f);
	Trunk->SetRelativeLocation(FVector(0.f, 0.f, 250.f));
	Trunk->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
	Trunk->SetHiddenInGame(true);

	for (const TCHAR* V : { TEXT("A"), TEXT("B"), TEXT("C"), TEXT("D") })
	{
		Variants.Add(Megaplant(TEXT("Tree_Black_Alder/Tree_Black_Alder_01"), *FString::Printf(TEXT("SK_Black_Alder_01_%s"), V)));
		Variants.Add(Megaplant(TEXT("Tree_European_Aspen/Tree_European_Aspen_01"), *FString::Printf(TEXT("SK_European_Aspen_01_%s"), V)));
		Variants.Add(Megaplant(TEXT("Tree_Goat_Willow/Tree_Goat_Willow_01"), *FString::Printf(TEXT("SK_Goat_Willow_01_%s"), V)));
	}
}

ASkyLinksBush::ASkyLinksBush()
{
	bSolidTrunk = false;
	Variants.Reset();
	for (const TCHAR* V : { TEXT("A"), TEXT("B"), TEXT("C"), TEXT("D") })
	{
		Variants.Add(Megaplant(TEXT("Tree_Elder/Tree_Elder_01"), *FString::Printf(TEXT("Tree_Elder_01_%s"), V)));
		Variants.Add(Megaplant(TEXT("Tree_European_Aspen/Tree_European_Aspen_Sapling_01"), *FString::Printf(TEXT("SK_Aspen_Sapling_01_%s"), V)));
	}
}

void ASkyLinksTree::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);

	Trunk->SetCollisionEnabled(bSolidTrunk ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
	if (Variants.IsEmpty())
	{
		return;
	}
	// Painted instances all share the defaults, so vary them by where they stand (1 m grid).
	const FVector Where = Transform.GetLocation() / 100.f;
	const uint32 Hash = HashCombine(GetTypeHash(FMath::FloorToInt(Where.X)), GetTypeHash(FMath::FloorToInt(Where.Y)));
	const int32 Index = Variants.IsValidIndex(VariantIndex) ? VariantIndex : static_cast<int32>(Hash % static_cast<uint32>(Variants.Num()));
	if (USkeletalMesh* Chosen = Variants[Index].LoadSynchronous())
	{
		Mesh->SetSkeletalMeshAsset(Chosen);
	}
}
