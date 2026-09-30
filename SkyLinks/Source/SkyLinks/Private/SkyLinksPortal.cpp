#include "SkyLinksPortal.h"
#include "SkyLinks.h"
#include "GolfCharacter.h"
#include "GolfPhysics.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "GameFramework/PlayerController.h"
#include "Camera/PlayerCameraManager.h"
#include "EngineUtils.h"
#include "Engine/World.h"

ASkyLinksPortal::ASkyLinksPortal()
{
	PrimaryActorTick.bCanEverTick = true;
	Ring = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Ring"));
	SetRootComponent(Ring);
	Ring->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Ring->SetCanEverAffectNavigation(false);
	Ring->SetMobility(EComponentMobility::Static);

	Hologram = CreateDefaultSubobject<UTextRenderComponent>(TEXT("Hologram"));
	Hologram->SetupAttachment(Ring);
	Hologram->SetMobility(EComponentMobility::Movable);
	Hologram->SetRelativeLocation(FVector(0.f, 0.f, HologramHeight));
	Hologram->SetHorizontalAlignment(EHTA_Center);
	Hologram->SetVerticalAlignment(EVRTA_TextCenter);
	Hologram->SetWorldSize(120.f);
	Hologram->SetTextRenderColor(FColor(90, 230, 255));
	Hologram->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Hologram->SetCastShadow(false);
}

void ASkyLinksPortal::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	Hologram->SetText(FText::FromString(Sign));
	Hologram->SetVisibility(!Sign.IsEmpty());
	Hologram->SetWorldRotation(FRotator(0.f, GetActorRotation().Yaw + (bSignFacesBack ? 180.f : 0.f), 0.f));
}

void ASkyLinksPortal::BeginPlay()
{
	Super::BeginPlay();
	Hologram->SetText(FText::FromString(Sign));
	Hologram->SetVisibility(!Sign.IsEmpty());
	// Ticks for the hologram everywhere but a dedicated server, and on the server for people walking through.
	SetActorTickEnabled(!IsRunningDedicatedServer() || (HasAuthority() && Target != nullptr));
}

int32 ASkyLinksPortal::Crossing(const FVector& From, const FVector& To) const
{
	const FVector Base = GetActorLocation();
	const FVector Normal = GetActorForwardVector().GetSafeNormal2D();
	const float Before = FVector::DotProduct(From - Base, Normal);
	const float After = FVector::DotProduct(To - Base, Normal);
	int32 Direction = 0;
	if (Before < 0.f && After >= 0.f)
	{
		Direction = 1;   // through the way the portal faces
	}
	else if (Before > 0.f && After <= 0.f)
	{
		Direction = -1;  // through the other way
	}
	if (Direction == 0)
	{
		return 0;
	}
	const float T = Before / (Before - After);
	const FVector Hit = FMath::Lerp(From, To, T) - Base;
	const FVector Side = FVector::CrossProduct(FVector::UpVector, Normal);
	const float Lateral = FMath::Abs(FVector::DotProduct(Hit, Side));
	return Lateral <= OpeningRadius && Hit.Z > -150.f && Hit.Z < OpeningHeight ? Direction : 0;
}

ASkyLinksPortal* ASkyLinksPortal::FindCrossed(const UWorld* World, const FVector& From, const FVector& To, int32& OutDirection)
{
	OutDirection = 0;
	if (!World)
	{
		return nullptr;
	}
	for (TActorIterator<ASkyLinksPortal> It(World); It; ++It)
	{
		if (!It->Target)
		{
			continue;
		}
		OutDirection = It->Crossing(From, To);
		if (OutDirection != 0)
		{
			return *It;
		}
	}
	return nullptr;
}

bool ASkyLinksPortal::FindGround(const UWorld* World, const FVector& Location, FVector& OutGround, const AActor* Ignore)
{
	if (!World)
	{
		return false;
	}
	FCollisionQueryParams Params(SCENE_QUERY_STAT(PortalGround), false, Ignore);
	Params.bReturnPhysicalMaterial = true;
	TArray<FHitResult> Hits;
	const FVector Top = Location + FVector(0.f, 0.f, 3000.f);
	World->LineTraceMultiByObjectType(Hits, Top, Location - FVector(0.f, 0.f, 4000.f), FCollisionObjectQueryParams(ECC_WorldStatic), Params);
	for (const FHitResult& Hit : Hits)
	{
		if (Hit.bBlockingHit && !GolfPhysics::IsFoliageHit(Hit) && Hit.ImpactNormal.Z > 0.5f)
		{
			OutGround = Hit.ImpactPoint;
			return true;
		}
	}
	return false;
}

bool ASkyLinksPortal::IsNearAnExit(const UWorld* World, const FVector& Location, float Tolerance)
{
	if (!World)
	{
		return false;
	}
	for (TActorIterator<ASkyLinksPortal> It(World); It; ++It)
	{
		const FVector Out = It->GetActorForwardVector().GetSafeNormal2D() * It->ExitDistance;
		if (FVector::Dist2D(Location, It->GetActorLocation() + Out) < Tolerance
			|| FVector::Dist2D(Location, It->GetActorLocation() - Out) < Tolerance)
		{
			return true;
		}
	}
	return false;
}

void ASkyLinksPortal::ExitFor(const FVector& Location, const FRotator& Rotation, int32 Direction, FVector& OutLocation, FRotator& OutRotation) const
{
	check(Target);
	// Keep the heading relative to the portal: straight in, straight out, whichever way you went through.
	const float Turn = Target->GetActorRotation().Yaw - GetActorRotation().Yaw;
	OutRotation = FRotator(0.f, Rotation.Yaw + Turn, 0.f);
	// And the sideways offset from the middle of the opening.
	const FVector Side = FVector::CrossProduct(FVector::UpVector, GetActorForwardVector().GetSafeNormal2D());
	const float Lateral = FMath::Clamp(FVector::DotProduct(Location - GetActorLocation(), Side), -OpeningRadius, OpeningRadius);
	const FVector TargetForward = Target->GetActorForwardVector().GetSafeNormal2D();
	const FVector TargetSide = FVector::CrossProduct(FVector::UpVector, TargetForward);
	OutLocation = Target->GetActorLocation() + TargetForward * (ExitDistance * Direction) + TargetSide * Lateral;
}

void ASkyLinksPortal::FaceHologram(float DeltaSeconds)
{
	if (Sign.IsEmpty())
	{
		return;
	}
	// Fixed facing the side you drive in from (so it reads as "through here"), bobbing gently with a faint
	// flicker, like a projection.
	HologramTime += DeltaSeconds;
	const FVector Base = GetActorLocation() + FVector(0.f, 0.f, HologramHeight + 18.f * FMath::Sin(HologramTime * 1.6f));
	const FRotator Facing(0.f, GetActorRotation().Yaw + (bSignFacesBack ? 180.f : 0.f), 0.f);
	Hologram->SetWorldLocationAndRotation(Base, Facing);
	// Only from the side it faces: from behind (across the gap on the other island) it would read backwards.
	if (const APlayerController* Controller = GetWorld()->GetFirstPlayerController())
	{
		if (Controller->PlayerCameraManager)
		{
			const FVector ToCamera = Controller->PlayerCameraManager->GetCameraLocation() - Base;
			Hologram->SetVisibility(FVector::DotProduct(ToCamera, Facing.Vector()) > 0.f);
		}
	}
	const uint8 Glow = static_cast<uint8>(215 + 40 * FMath::Abs(FMath::Sin(HologramTime * 7.3f) * FMath::Sin(HologramTime * 2.1f)));
	Hologram->SetTextRenderColor(FColor(Glow / 3, Glow, 255));
}

void ASkyLinksPortal::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!IsRunningDedicatedServer())
	{
		FaceHologram(DeltaSeconds);
	}
	if (!HasAuthority() || !Target)
	{
		return;
	}
	// Golfers on foot (not riding a buggy): the server sees them step through and moves them.
	for (TActorIterator<AGolfCharacter> It(GetWorld()); It; ++It)
	{
		AGolfCharacter* Golfer = *It;
		if (Golfer->GetAttachParentActor() != nullptr)
		{
			Walkers.Remove(Golfer);
			continue;
		}
		const FVector Now = Golfer->GetActorLocation();
		const FVector* Before = Walkers.Find(Golfer);
		// A jump of more than 10 m in one tick is someone arriving through a portal, not walking: ignore it
		// (otherwise the line from the old island to the new one could look like a step through this portal).
		if (Before && FVector::Dist(*Before, Now) < 1000.f)
		{
			// Characters' origins are at the middle of the capsule: compare their feet.
			const FVector Drop(0.f, 0.f, Golfer->GetSimpleCollisionHalfHeight());
			const int32 Direction = Crossing(*Before - Drop, Now - Drop);
			if (Direction != 0)
			{
				FVector Exit;
				FRotator Facing;
				ExitFor(Now, Golfer->GetActorRotation(), Direction, Exit, Facing);
				FVector Ground = Exit;
				FindGround(GetWorld(), Exit, Ground, Golfer);
				Golfer->TeleportTo(Ground + Drop + FVector(0.f, 0.f, 20.f), Facing);
				Walkers.Remove(Golfer);
				continue;
			}
		}
		Walkers.Add(Golfer, Golfer->GetActorLocation());
	}
}
