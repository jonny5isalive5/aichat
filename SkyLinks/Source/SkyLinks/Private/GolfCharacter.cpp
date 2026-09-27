#include "GolfCharacter.h"
#include "SkyLinks.h"
#include "GolfPhysics.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Animation/AnimSequence.h"
#include "Engine/SkeletalMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Net/UnrealNetwork.h"
#include "UObject/ConstructorHelpers.h"

AGolfCharacter::AGolfCharacter()
{
	bReplicates = true;
	SetReplicateMovement(false);

	GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_GolfBall, ECR_Ignore);
	GetMesh()->SetCollisionResponseToChannel(ECC_GolfBall, ECR_Ignore);

	PlaceholderBody = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("PlaceholderBody"));
	PlaceholderBody->SetupAttachment(GetCapsuleComponent());
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Capsule(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	if (Capsule.Succeeded())
	{
		PlaceholderBody->SetStaticMesh(Capsule.Object);
	}
	PlaceholderBody->SetRelativeScale3D(FVector(0.5f, 0.5f, 1.7f));
	PlaceholderBody->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	// Camera: low, behind the ball, looking down the aim line. Placed in world space by ApplyAddress.
	CameraArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraArm"));
	CameraArm->SetupAttachment(GetCapsuleComponent());
	CameraArm->SetUsingAbsoluteLocation(true);
	CameraArm->SetUsingAbsoluteRotation(true);
	CameraArm->TargetArmLength = 380.f;
	CameraArm->SocketOffset = FVector(0.f, 45.f, 80.f);
	CameraArm->bDoCollisionTest = false;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(CameraArm);
	Camera->SetFieldOfView(70.f);

	auto Path = [](const TCHAR* Name) { return FSoftObjectPath(FString::Printf(TEXT("/Game/Characters/Golfer/%s.%s"), Name, Name)); };
	auto Anim = [](const TCHAR* Name) { return FSoftObjectPath(FString::Printf(TEXT("/Game/Characters/Golfer/Animations/%s.%s"), Name, Name)); };
	GolferMeshAsset = TSoftObjectPtr<USkeletalMesh>(Path(TEXT("SK_Golfer")));
	DriveAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_Drive")));
	ChipAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_Chip")));
	PuttAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_Putt")));
	HoleInOneAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_HoleInOne")));
	CelebrateAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_Celebrate")));
	PuttVictoryAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_PuttVictory")));
	PuttMissAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_PuttMiss")));
	BadShotAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_BadShot")));
}

void AGolfCharacter::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AGolfCharacter, BallLocation);
	DOREPLIFETIME(AGolfCharacter, AimYaw);
	DOREPLIFETIME(AGolfCharacter, bPuttingStance);
}

void AGolfCharacter::BeginPlay()
{
	Super::BeginPlay();
	GetCharacterMovement()->DisableMovement();

	LoadBody();
	const bool bHasRealMesh = GetMesh()->GetSkeletalMeshAsset() != nullptr;
	PlaceholderBody->SetVisibility(!bHasRealMesh);
	if (!bHasRealMesh)
	{
		if (UMaterialInstanceDynamic* Material = PlaceholderBody->CreateAndSetMaterialInstanceDynamic(0))
		{
			Material->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.9f, 0.3f, 0.2f));
		}
	}
}

void AGolfCharacter::Restart()
{
	Super::Restart();
	// Possession resets the movement mode; the golfer is placed by code, never walks.
	GetCharacterMovement()->DisableMovement();
	ApplyAddress();
}

void AGolfCharacter::LoadBody()
{
	if (!GetMesh()->GetSkeletalMeshAsset())
	{
		if (USkeletalMesh* Body = GolferMeshAsset.LoadSynchronous())
		{
			GetMesh()->SetSkeletalMesh(Body);
		}
	}
	bHasBody = GetMesh()->GetSkeletalMeshAsset() != nullptr;
	if (!bHasBody)
	{
		return;
	}
	// Feet on the ground at the bottom of the capsule, facing the actor's forward.
	GetMesh()->SetRelativeLocationAndRotation(FVector(0.f, 0.f, -GetCapsuleComponent()->GetScaledCapsuleHalfHeight()), FRotator(0.f, MeshYawOffset, 0.f));
	GetMesh()->SetRelativeScale3D(FVector(GolferScale));
	GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
	GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
	HoldAddressPose();
}

UAnimSequence* AGolfCharacter::SwingAsset(EGolferSwing Swing) const
{
	switch (Swing)
	{
	case EGolferSwing::Putt: return PuttAnim.LoadSynchronous();
	case EGolferSwing::Chip: return ChipAnim.LoadSynchronous();
	default:                 return DriveAnim.LoadSynchronous();
	}
}

UAnimSequence* AGolfCharacter::ReactionAsset(EGolferReaction Reaction) const
{
	switch (Reaction)
	{
	case EGolferReaction::HoleInOne:   return HoleInOneAnim.LoadSynchronous();
	case EGolferReaction::Celebrate:   return CelebrateAnim.LoadSynchronous();
	case EGolferReaction::PuttVictory: return PuttVictoryAnim.LoadSynchronous();
	case EGolferReaction::PuttMiss:    return PuttMissAnim.LoadSynchronous();
	case EGolferReaction::BadShot:     return BadShotAnim.LoadSynchronous();
	default:                           return nullptr;
	}
}

void AGolfCharacter::HoldAddressPose()
{
	// The first frame of each swing is a clean address position; hold it while the player aims.
	if (!bHasBody)
	{
		return;
	}
	bPlayingAction = false;
	if (UAnimSequence* Pose = SwingAsset(bPuttingStance ? EGolferSwing::Putt : EGolferSwing::Drive))
	{
		GetMesh()->PlayAnimation(Pose, false);
		GetMesh()->SetPosition(0.f, false);
		GetMesh()->SetPlayRate(0.f);
	}
}

float AGolfCharacter::GetImpactDelay(EGolferSwing Swing) const
{
	if (!bHasBody || !SwingAsset(Swing))
	{
		return 0.f;
	}
	switch (Swing)
	{
	case EGolferSwing::Putt: return PuttImpactTime;
	case EGolferSwing::Chip: return ChipImpactTime;
	default:                 return DriveImpactTime;
	}
}

float AGolfCharacter::GetReactionDuration(EGolferReaction Reaction) const
{
	const UAnimSequence* Clip = bHasBody ? ReactionAsset(Reaction) : nullptr;
	// Long Mixamo clips are cut short so the round keeps moving.
	return Clip ? FMath::Min(Clip->GetPlayLength(), 4.f) : 0.f;
}

void AGolfCharacter::MulticastPlayReaction_Implementation(EGolferReaction Reaction)
{
	if (UAnimSequence* Clip = bHasBody ? ReactionAsset(Reaction) : nullptr)
	{
		bPlayingAction = true;
		GetMesh()->SetPlayRate(1.f);
		GetMesh()->PlayAnimation(Clip, false);
	}
}

void AGolfCharacter::SetAddress(const FVector& InBallLocation, float InAimYaw, bool bPutting)
{
	bPuttingStance = bPutting;
	BallLocation = InBallLocation;
	AimYaw = InAimYaw;
	ApplyAddress();
	HoldAddressPose();
}

void AGolfCharacter::SetLocalAim(float InAimYaw)
{
	AimYaw = InAimYaw;
	ApplyAddress();
	ServerSetAim(InAimYaw);
}

void AGolfCharacter::SetPreviewCamera(const FVector& LandingLocation, bool bUseLandingView)
{
	if (!bUseLandingView)
	{
		ApplyAddress();
		return;
	}

	// A 45 m high camera keeps the landing ring and its surrounding green readable on a phone.
	CameraArm->TargetArmLength = 0.f;
	CameraArm->SocketOffset = FVector::ZeroVector;
	CameraArm->SetWorldLocationAndRotation(LandingLocation + FVector(0.f, 0.f, 4500.f), FRotator(-89.f, AimYaw, 0.f));
	Camera->SetFieldOfView(70.f);
}

void AGolfCharacter::ServerSetAim_Implementation(float InAimYaw)
{
	AimYaw = InAimYaw;
	ApplyAddress();
}

void AGolfCharacter::OnRep_Address()
{
	ApplyAddress();
	// A new ball position or stance means a new shot: go back to the address pose.
	if (BallLocation != LastPosedBall || bPuttingStance != bLastPosedPutting)
	{
		LastPosedBall = BallLocation;
		bLastPosedPutting = bPuttingStance;
		HoldAddressPose();
	}
}

void AGolfCharacter::ApplyAddress()
{
	const FRotator Aim(0.f, AimYaw, 0.f);
	const FVector Right = FRotationMatrix(Aim).GetUnitAxis(EAxis::Y);
	const float HalfHeight = GetCapsuleComponent()->GetScaledCapsuleHalfHeight();

	// A right-handed golfer stands on the left of the target line, facing the ball.
	const FVector Feet = BallLocation - Right * StanceDistance - FVector(0.f, 0.f, GolfPhysics::BallRadius);
	SetActorLocationAndRotation(Feet + FVector(0.f, 0.f, HalfHeight), FRotator(0.f, AimYaw + 90.f, 0.f));

	CameraArm->TargetArmLength = 380.f;
	CameraArm->SocketOffset = FVector(0.f, 45.f, 80.f);
	CameraArm->SetWorldLocationAndRotation(BallLocation + FVector(0.f, 0.f, 60.f), FRotator(-8.f, AimYaw, 0.f));
	Camera->SetFieldOfView(70.f);
}

void AGolfCharacter::MulticastPlaySwing_Implementation(EGolferSwing Swing)
{
	if (UAnimSequence* Clip = bHasBody ? SwingAsset(Swing) : nullptr)
	{
		bPlayingAction = true;
		GetMesh()->PlayAnimation(Clip, false);
		GetMesh()->SetPosition(0.f, false);
		GetMesh()->SetPlayRate(1.f);
	}
}
