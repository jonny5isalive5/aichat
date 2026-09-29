#include "SkyLinksForest.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "FoliageType_InstancedStaticMesh.h"
#include "InstancedFoliage.h"
#include "InstancedFoliageActor.h"

ASkyLinksForest::ASkyLinksForest()
{
	PrimaryActorTick.bCanEverTick = false;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent->SetMobility(EComponentMobility::Static);
}

UHierarchicalInstancedStaticMeshComponent* ASkyLinksForest::ComponentFor(UStaticMesh* Mesh)
{
	TArray<UHierarchicalInstancedStaticMeshComponent*> Existing;
	GetComponents(Existing);
	for (UHierarchicalInstancedStaticMeshComponent* Component : Existing)
	{
		if (Component->GetStaticMesh() == Mesh)
		{
			return Component;
		}
	}

	UHierarchicalInstancedStaticMeshComponent* Component = NewObject<UHierarchicalInstancedStaticMeshComponent>(
		this, MakeUniqueObjectName(this, UHierarchicalInstancedStaticMeshComponent::StaticClass(), Mesh->GetFName()), RF_Transactional);
	Component->SetMobility(EComponentMobility::Static);
	Component->SetupAttachment(RootComponent);
	Component->SetStaticMesh(Mesh);
	Component->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
	Component->SetCullDistances(static_cast<int32>(CullDistance * 0.8f), static_cast<int32>(CullDistance));
	AddInstanceComponent(Component);
	Component->RegisterComponent();
	return Component;
}

int32 ASkyLinksForest::AddTrees(UStaticMesh* Mesh, const TArray<FTransform>& WorldTransforms)
{
	if (!Mesh || WorldTransforms.IsEmpty())
	{
		return 0;
	}
	Modify();
	UHierarchicalInstancedStaticMeshComponent* Component = ComponentFor(Mesh);
	Component->Modify();
	Component->AddInstances(WorldTransforms, false, true);
	return WorldTransforms.Num();
}

void ASkyLinksForest::ClearTrees()
{
	Modify();
	TArray<UHierarchicalInstancedStaticMeshComponent*> Existing;
	GetComponents(Existing);
	for (UHierarchicalInstancedStaticMeshComponent* Component : Existing)
	{
		RemoveInstanceComponent(Component);
		Component->DestroyComponent();
	}
}

int32 ASkyLinksForest::GetTreeCount() const
{
	int32 Count = 0;
	TArray<UHierarchicalInstancedStaticMeshComponent*> Existing;
	GetComponents(Existing);
	for (const UHierarchicalInstancedStaticMeshComponent* Component : Existing)
	{
		Count += Component->GetInstanceCount();
	}
	return Count;
}

int32 ASkyLinksForest::ConvertToFoliage(const TArray<UFoliageType*>& Types)
{
#if WITH_EDITOR
	int32 Moved = 0;
	TArray<UHierarchicalInstancedStaticMeshComponent*> Existing;
	GetComponents(Existing);
	for (UHierarchicalInstancedStaticMeshComponent* Component : Existing)
	{
		UFoliageType* const* Found = Types.FindByPredicate([Component](const UFoliageType* Type)
		{
			const UFoliageType_InstancedStaticMesh* MeshType = Cast<UFoliageType_InstancedStaticMesh>(Type);
			return MeshType && MeshType->GetStaticMesh() == Component->GetStaticMesh();
		});
		if (!Found)
		{
			continue;
		}
		// Same behaviour as the forest had: trunks block the ball and the buggy, trees fade out far away.
		UFoliageType* Type = *Found;
		Type->Modify();
		Type->BodyInstance.SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
		Type->CullDistance = FInt32Interval(static_cast<int32>(CullDistance * 0.8f), static_cast<int32>(CullDistance));

		// The same calls Foliage mode's paint brush makes (the level's foliage actor, the type's info, instances).
		AInstancedFoliageActor* Foliage = AInstancedFoliageActor::GetInstancedFoliageActorForCurrentLevel(GetWorld(), true);
		if (!Foliage)
		{
			continue;
		}
		Foliage->Modify();
		FFoliageInfo* Info = nullptr;
		UFoliageType* Settings = Foliage->AddFoliageType(Type, &Info);
		if (!Info || !Settings)
		{
			continue;
		}
		TArray<FFoliageInstance> Instances;
		Instances.Reserve(Component->GetInstanceCount());
		for (int32 Index = 0; Index < Component->GetInstanceCount(); ++Index)
		{
			FTransform Transform;
			Component->GetInstanceTransform(Index, Transform, true);
			FFoliageInstance& Instance = Instances.AddDefaulted_GetRef();
			Instance.Location = Transform.GetLocation();
			Instance.Rotation = Transform.Rotator();
			Instance.PreAlignRotation = Instance.Rotation;
			Instance.DrawScale3D = FVector3f(Transform.GetScale3D());
		}
		TArray<const FFoliageInstance*> Pointers;
		Pointers.Reserve(Instances.Num());
		for (const FFoliageInstance& Instance : Instances)
		{
			Pointers.Add(&Instance);
		}
		Info->AddInstances(Settings, Pointers);
		Moved += Instances.Num();
	}
	Destroy();
	return Moved;
#else
	return 0;
#endif
}

void ASkyLinksForest::ClearFoliage(UObject* WorldContextObject, const TArray<UFoliageType*>& Types)
{
#if WITH_EDITOR
	UWorld* World = WorldContextObject ? WorldContextObject->GetWorld() : nullptr;
	if (!World)
	{
		return;
	}
	for (TActorIterator<AInstancedFoliageActor> It(World); It; ++It)
	{
		for (UFoliageType* Type : Types)
		{
			if (Type)
			{
				UFoliageType* Remove = Type;
				It->RemoveFoliageType(&Remove, 1);
			}
		}
	}
#endif
}

int32 ASkyLinksForest::ClearFoliageInside(UObject* WorldContextObject, const TArray<UFoliageType*>& Types, const TArray<FVector2D>& Outline)
{
	int32 Removed = 0;
#if WITH_EDITOR
	UWorld* World = WorldContextObject ? WorldContextObject->GetWorld() : nullptr;
	if (!World || Outline.Num() < 3)
	{
		return 0;
	}
	auto Inside = [&Outline](const FVector& P)
	{
		// Even-odd ray test in XY.
		bool bIn = false;
		for (int32 I = 0, J = Outline.Num() - 1; I < Outline.Num(); J = I++)
		{
			const FVector2D& A = Outline[I];
			const FVector2D& B = Outline[J];
			if ((A.Y > P.Y) != (B.Y > P.Y) && P.X < (B.X - A.X) * (P.Y - A.Y) / (B.Y - A.Y) + A.X)
			{
				bIn = !bIn;
			}
		}
		return bIn;
	};
	for (TActorIterator<AInstancedFoliageActor> It(World); It; ++It)
	{
		for (UFoliageType* Type : Types)
		{
			FFoliageInfo* Info = Type ? It->FindInfo(Type) : nullptr;
			if (!Info)
			{
				continue;
			}
			TArray<int32> Doomed;
			for (int32 Index = 0; Index < Info->Instances.Num(); ++Index)
			{
				if (Inside(Info->Instances[Index].Location))
				{
					Doomed.Add(Index);
				}
			}
			if (Doomed.Num() > 0)
			{
				It->Modify();
				Info->RemoveInstances(Doomed, true);
				Removed += Doomed.Num();
			}
		}
	}
#endif
	return Removed;
}
