#include "SkyLinksForest.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"

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
