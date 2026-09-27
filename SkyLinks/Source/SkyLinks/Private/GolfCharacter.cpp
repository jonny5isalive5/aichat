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
#include "GolfBuggy.h"
#include "TimerManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Net/UnrealNetwork.h"
#include "UObject/ConstructorHelpers.h"

AGolfCharacter::AGolfCharacter()
{
	bReplicates = true;
	SetReplicateMovement(false);
	// The golfer is posed by code (address, buggy). Following the controller's yaw would turn them away
	// from the ball every frame (flipping while aiming) and walk them past the buggy when climbing in.
	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw = false;
	bUseControllerRotationRoll = false;

	GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_GolfBall, ECR_Ignore);
	GetMesh()->SetCollisionResponseToChannel(ECC_GolfBall, ECR_Ignore);
	GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
	GetMesh()->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);

	PlaceholderBody = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("PlaceholderBody"));
	PlaceholderBody->SetupAttachment(GetCapsuleComponent());
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Capsule(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	if (Capsule.Succeeded())
	{
		PlaceholderBody->SetStaticMesh(Capsule.Object);
	}
	PlaceholderBody->SetRelativeScale3D(FVector(0.5f, 0.5f, 1.7f));
	PlaceholderBody->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	Club = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Club"));
	Club->SetupAttachment(GetMesh());
	Club->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Club->SetCastShadow(true);

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
	EnterBuggyAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_EnterBuggy")));
	ExitBuggyAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_ExitBuggy")));
	IronClubAsset = TSoftObjectPtr<UStaticMesh>(Path(TEXT("SM_Club_Iron")));
	PutterClubAsset = TSoftObjectPtr<UStaticMesh>(Path(TEXT("SM_Club_Putter")));
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
	if (!bPlayingAction)
	{
		ApplyAddress(); // Not while climbing out of the buggy, or it would snap back to the old spot.
	}
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
	// Place the club once the address pose has been evaluated (next frames), so the hands are in place.
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().SetTimer(ClubTimer, this, &AGolfCharacter::PlaceClub, 0.1f, false);
	}
}

FName AGolfCharacter::FindBone(const TCHAR* Suffix) const
{
	const FString Wanted(Suffix);
	for (int32 Index = 0; Index < GetMesh()->GetNumBones(); ++Index)
	{
		const FName Bone = GetMesh()->GetBoneName(Index);
		const FString Name = Bone.ToString();
		if (Name.Equals(Wanted, ESearchCase::IgnoreCase) || Name.EndsWith(TEXT(":") + Wanted, ESearchCase::IgnoreCase)
			|| Name.EndsWith(TEXT("_") + Wanted, ESearchCase::IgnoreCase))
		{
			return Bone;
		}
	}
	return NAME_None;
}

void AGolfCharacter::PlaceClub()
{
	UStaticMesh* ClubMesh = (bPuttingStance ? PutterClubAsset : IronClubAsset).LoadSynchronous();
	if (!bHasBody || !ClubMesh)
	{
		Club->SetVisibility(false);
		return;
	}
	if (bPlayingAction)
	{
		return; // Mid-swing or reaction: leave the club where the hand has it.
	}
	Club->SetStaticMesh(ClubMesh);
	Club->SetVisibility(true);

	// Make sure the bones are in the address pose now, not last frame's (or a hidden golfer's) pose.
	GetMesh()->TickAnimation(0.f, false);
	GetMesh()->RefreshBoneTransforms();

	const FName RightHand = FindBone(*ClubHandBone);
	const FName LeftHand = FindBone(TEXT("LeftHand"));
	if (RightHand.IsNone() || LeftHand.IsNone())
	{
		UE_LOG(LogSkyLinks, Warning, TEXT("Golfer: no hand bones found; the club stays hidden."));
		Club->SetVisibility(false);
		return;
	}
	// The club head rests just behind the ball on the ground; the shaft points at the middle of the hands.
	const FVector Forward = FRotator(0.f, AimYaw, 0.f).Vector();
	const FVector Head = BallLocation - FVector(0.f, 0.f, GolfPhysics::BallRadius) - Forward * 4.f;
	const FVector Grip = (GetMesh()->GetBoneLocation(RightHand) + GetMesh()->GetBoneLocation(LeftHand)) * 0.5f;
	const FVector Shaft = (Grip - Head).GetSafeNormal();
	if (Shaft.IsNearlyZero())
	{
		return;
	}
	// Club mesh: origin at the sole, shaft up +Z, face towards +X (the target).
	const FRotator Rotation = FRotationMatrix::MakeFromZX(Shaft, Forward).Rotator();

	// Fix it to the right hand, keeping this world placement (and real-world size despite the body scale).
	Club->AttachToComponent(GetMesh(), FAttachmentTransformRules(EAttachmentRule::KeepWorld, EAttachmentRule::KeepWorld, EAttachmentRule::KeepWorld, false), RightHand);
	Club->SetWorldLocationAndRotation(Head, Rotation);
	// Stretch the shaft (not the head) so the grip reaches the hands of the scaled-up golfer.
	const float MeshLength = ClubMesh->GetBounds().BoxExtent.Z * 2.f;
	const float Reach = FVector::Dist(Head, Grip) + ClubGripOverhang;
	const float Stretch = MeshLength > 1.f ? FMath::Clamp(Reach / MeshLength, 0.7f, 1.8f) : 1.f;
	Club->SetWorldScale3D(FVector(1.f, 1.f, Stretch));
}

float AGolfCharacter::GetBuggyTransitionDuration(bool bEnter) const
{
	const UAnimSequence* Clip = bHasBody ? (bEnter ? EnterBuggyAnim : ExitBuggyAnim).LoadSynchronous() : nullptr;
	return Clip ? Clip->GetPlayLength() / FMath::Max(BuggyAnimRate, 0.1f) : 0.f;
}

void AGolfCharacter::MulticastBuggyTransition_Implementation(AGolfBuggy* Buggy, bool bEnter)
{
	UAnimSequence* Clip = bHasBody ? (bEnter ? EnterBuggyAnim : ExitBuggyAnim).LoadSynchronous() : nullptr;
	if (!Clip || !Buggy)
	{
		return;
	}
	// Measured from the Mixamo clips: "Entering Car" starts about 1.9 m to the left of the seat facing
	// the buggy and ends seated; "Exiting Car" starts seated facing forward.
	const FTransform BuggyFrame(FRotator(0.f, Buggy->GetActorRotation().Yaw, 0.f), Buggy->GetActorLocation() - FVector(0.f, 0.f, AGolfBuggy::RideHeight));
	const FVector Local = bEnter ? DriverSeat + EnterStartFromSeat : DriverSeat;
	const FVector Ground = BuggyFrame.TransformPosition(Local);
	const float Yaw = Buggy->GetActorRotation().Yaw + (bEnter ? 90.f : 0.f);
	SetActorLocationAndRotation(Ground + FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight()), FRotator(0.f, Yaw, 0.f));

	bPlayingAction = true;
	Club->SetVisibility(false);
	GetMesh()->PlayAnimation(Clip, false);
	GetMesh()->SetPosition(0.f, false);
	GetMesh()->SetPlayRate(BuggyAnimRate);
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
	const bool bNewAddress = BallLocation != LastPosedBall || bPuttingStance != bLastPosedPutting;
	// The aiming player already turned locally; an echo of an older aim from the server would snap
	// the golfer back and forth. Only take the server's aim when it's a new address.
	if (IsLocallyControlled() && !bNewAddress)
	{
		return;
	}
	ApplyAddress();
	// A new ball position or stance means a new shot: go back to the address pose.
	if (bNewAddress)
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
	const FVector Feet = BallLocation - Right * StanceDistance - Aim.Vector() * AddressBackOffset - FVector(0.f, 0.f, GolfPhysics::BallRadius);
	// The Mixamo golf clips are authored a quarter turn from the body's forward (the buggy clips are not):
	// with the actor facing down the aim line, the swing faces the ball.
	SetActorLocationAndRotation(Feet + FVector(0.f, 0.f, HalfHeight), FRotator(0.f, AimYaw, 0.f));

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
