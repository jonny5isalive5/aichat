#include "SkyLinksPortal.h"
#include "SkyLinks.h"
#include "GolfCharacter.h"
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
}

void ASkyLinksPortal::BeginPlay()
{
	Super::BeginPlay();
	Hologram->SetText(FText::FromString(Sign));
	Hologram->SetVisibility(!Sign.IsEmpty());
	// Ticks for the hologram everywhere but a dedicated server, and for walkers through entry portals on the server.
	SetActorTickEnabled(!IsRunningDedicatedServer() || (HasAuthority() && Target != nullptr));
}

bool ASkyLinksPortal::Crossed(const FVector& From, const FVector& To) const
{
	const FVector Base = GetActorLocation();
	const FVector Normal = GetActorForwardVector().GetSafeNormal2D();
	const float Before = FVector::DotProduct(From - Base, Normal);
	const float After = FVector::DotProduct(To - Base, Normal);
	if (Before >= 0.f || After < 0.f)
	{
		return false; // Only going through forwards counts.
	}
	const float T = Before / (Before - After);
	const FVector Hit = FMath::Lerp(From, To, T) - Base;
	const FVector Side = FVector::CrossProduct(FVector::UpVector, Normal);
	const float Lateral = FMath::Abs(FVector::DotProduct(Hit, Side));
	return Lateral <= OpeningRadius && Hit.Z > -150.f && Hit.Z < OpeningHeight;
}

ASkyLinksPortal* ASkyLinksPortal::FindCrossed(const UWorld* World, const FVector& From, const FVector& To)
{
	if (!World)
	{
		return nullptr;
	}
	for (TActorIterator<ASkyLinksPortal> It(World); It; ++It)
	{
		if (It->Target && It->Crossed(From, To))
		{
			return *It;
		}
	}
	return nullptr;
}

bool ASkyLinksPortal::IsNearAnExit(const UWorld* World, const FVector& Location, float Tolerance)
{
	if (!World)
	{
		return false;
	}
	for (TActorIterator<ASkyLinksPortal> It(World); It; ++It)
	{
		const ASkyLinksPortal* Exit = It->Target;
		if (Exit && FVector::Dist2D(Location, Exit->GetActorLocation() + Exit->GetActorForwardVector() * It->ExitDistance) < Tolerance)
		{
			return true;
		}
	}
	return false;
}

void ASkyLinksPortal::ExitFor(const FVector& Location, const FRotator& Rotation, FVector& OutLocation, FRotator& OutRotation) const
{
	check(Target);
	// Keep the heading relative to the portal: straight in, straight out.
	const float Turn = Target->GetActorRotation().Yaw - GetActorRotation().Yaw;
	OutRotation = FRotator(0.f, Rotation.Yaw + Turn, 0.f);
	// And the sideways offset from the middle of the opening.
	const FVector Side = FVector::CrossProduct(FVector::UpVector, GetActorForwardVector().GetSafeNormal2D());
	const float Lateral = FMath::Clamp(FVector::DotProduct(Location - GetActorLocation(), Side), -OpeningRadius, OpeningRadius);
	const FVector TargetSide = FVector::CrossProduct(FVector::UpVector, Target->GetActorForwardVector().GetSafeNormal2D());
	OutLocation = Target->GetActorLocation() + Target->GetActorForwardVector().GetSafeNormal2D() * ExitDistance + TargetSide * Lateral;
}

void ASkyLinksPortal::FaceHologram(float DeltaSeconds)
{
	if (Sign.IsEmpty())
	{
		return;
	}
	// Bob gently and always turn to face this player's camera, with a faint flicker, like a projection.
	HologramTime += DeltaSeconds;
	const FVector Base = GetActorLocation() + FVector(0.f, 0.f, HologramHeight + 18.f * FMath::Sin(HologramTime * 1.6f));
	FRotator Facing = GetActorRotation();
	if (const APlayerController* Controller = GetWorld()->GetFirstPlayerController())
	{
		if (Controller->PlayerCameraManager)
		{
			const FVector ToCamera = Controller->PlayerCameraManager->GetCameraLocation() - Base;
			Facing = FRotator(0.f, ToCamera.Rotation().Yaw, 0.f);
		}
	}
	Hologram->SetWorldLocationAndRotation(Base, Facing);
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
		if (const FVector* Before = Walkers.Find(Golfer))
		{
			// Characters' origins are at the middle of the capsule: compare their feet.
			const FVector Drop(0.f, 0.f, Golfer->GetSimpleCollisionHalfHeight());
			if (Crossed(*Before - Drop, Now - Drop))
			{
				FVector Exit;
				FRotator Facing;
				ExitFor(Now, Golfer->GetActorRotation(), Exit, Facing);
				Golfer->TeleportTo(Exit + Drop + FVector(0.f, 0.f, 20.f), Facing);
				Walkers.Remove(Golfer);
				continue;
			}
		}
		Walkers.Add(Golfer, Golfer->GetActorLocation());
	}
}
