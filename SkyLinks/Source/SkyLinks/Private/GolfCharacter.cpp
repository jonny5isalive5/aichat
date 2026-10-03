#include "GolfCharacter.h"
#include "SkyLinks.h"
#include "GolfPhysics.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Camera/PlayerCameraManager.h"
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

	PointAssetsAt(0);

	// Walking between shots: turn toward where you're going (the camera follows behind).
	UCharacterMovementComponent* Movement = GetCharacterMovement();
	Movement->bOrientRotationToMovement = false;
	Movement->RotationRate = FRotator(0.f, 540.f, 0.f);
	Movement->MaxWalkSpeed = WalkSpeed;
	Movement->BrakingDecelerationWalking = 1400.f;
}

namespace
{
	/** The golfers a player can be. Speeds are measured from each one's own walk and run clips (feet don't skate). */
	struct FGolferBodyInfo
	{
		const TCHAR* Folder;   // /Game/Characters/<Folder>: SK_Golfer, clubs, Animations/A_*
		float Height;          // cm in game
		float WalkAnimSpeed;   // cm/s each clip covers at play rate 1 (measured from its planted feet)
		float JogAnimSpeed;
		float RunAnimSpeed;
		float WalkSpeed;       // cm/s at each gait of the GO bar
		float FastWalkSpeed;
		float JogSpeed;
		float RunSpeed;
		float DriveImpact;     // s from the start of each swing to club on ball (the Y-Bot male / female swings)
		float ChipImpact;
		float PuttImpact;
	};
	// Clip speeds are the SPEED lines printed by build_eccentric_golfer.py (planted feet locked to them). The Meshy
	// jogs are jogs on the spot, so the jog gait plays the run clip, slowed (JogAnimSpeed = RunAnimSpeed). Impact times:
	// when the club head, fixed in the right hand at address, comes back closest to the ball (measured in the editor).
	const FGolferBodyInfo GolferBodies[] = {
		{ TEXT("Eccentric"), 180.f, 101.f, 295.f, 295.f, 110.f, 160.f, 185.f, 300.f, 1.19f, 1.43f, 1.33f },  // the man
		{ TEXT("Diva"), 172.f, 118.f, 286.f, 286.f, 125.f, 170.f, 200.f, 320.f, 1.14f, 1.02f, 1.22f },       // his wife
		{ TEXT("Teen"), 163.f, 112.f, 373.f, 373.f, 120.f, 170.f, 200.f, 320.f, 1.14f, 1.01f, 1.22f },       // the teenage girl
		{ TEXT("Lad"), 178.f, 60.f, 304.f, 304.f, 110.f, 160.f, 185.f, 300.f, 1.19f, 1.43f, 1.33f },        // the lad (Flamingo Fairway)
	};
}

int32 AGolfCharacter::NumBodies()
{
	return UE_ARRAY_COUNT(GolferBodies);
}

void AGolfCharacter::PointAssetsAt(uint8 InBody)
{
	const FGolferBodyInfo& Info = GolferBodies[FMath::Clamp<int32>(InBody, 0, NumBodies() - 1)];
	const FString Folder = FString::Printf(TEXT("/Game/Characters/%s"), Info.Folder);
	auto Path = [&Folder](const TCHAR* Name) { return FSoftObjectPath(FString::Printf(TEXT("%s/%s.%s"), *Folder, Name, Name)); };
	auto Anim = [&Folder](const TCHAR* Name) { return FSoftObjectPath(FString::Printf(TEXT("%s/Animations/%s.%s"), *Folder, Name, Name)); };
	GolferMeshAsset = TSoftObjectPtr<USkeletalMesh>(Path(TEXT("SK_Golfer")));
	DriveAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_Drive")));
	ChipAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_Chip")));
	PuttAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_Putt")));
	HoleInOneAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_HoleInOne")));
	CelebrateAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_Celebrate")));
	PuttVictoryAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_PuttVictoryLong")));
	PuttMissAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_PuttMiss")));
	BadShotAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_BadShot")));
	TeeUpAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_TeeUp")));
	EnterBuggyAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_EnterBuggy")));
	ExitBuggyAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_ExitBuggy")));
	IdleAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_Idle")));
	WalkAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_Walk")));
	JogAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_Run")));  // A_Jog jogs on the spot: its feet would skate
	RunAnim = TSoftObjectPtr<UAnimSequence>(Anim(TEXT("A_Run")));
	IronClubAsset = TSoftObjectPtr<UStaticMesh>(Path(TEXT("SM_Club_Iron")));
	PutterClubAsset = TSoftObjectPtr<UStaticMesh>(Path(TEXT("SM_Club_Putter")));
	GolferHeight = Info.Height;
	WalkAnimSpeed = Info.WalkAnimSpeed;
	JogAnimSpeed = Info.JogAnimSpeed;
	RunAnimSpeed = Info.RunAnimSpeed;
	WalkSpeed = Info.WalkSpeed;
	FastWalkSpeed = Info.FastWalkSpeed;
	JogSpeed = Info.JogSpeed;
	RunSpeed = Info.RunSpeed;
	DriveImpactTime = Info.DriveImpact;
	ChipImpactTime = Info.ChipImpact;
	PuttImpactTime = Info.PuttImpact;
}

void AGolfCharacter::ChooseBody(uint8 InBody)
{
	InBody = static_cast<uint8>(FMath::Clamp<int32>(InBody, 0, NumBodies() - 1));
	if (!HasAuthority())
	{
		ServerChooseBody(InBody);
		return;
	}
	Body = InBody;
	ApplyBody(); // (the listen server's own copy; everyone else through OnRep_Body)
}

void AGolfCharacter::ServerChooseBody_Implementation(uint8 InBody)
{
	ChooseBody(InBody);
}

void AGolfCharacter::OnRep_Body()
{
	ApplyBody();
}

void AGolfCharacter::ApplyBody()
{
	PointAssetsAt(Body);
	GetMesh()->SetSkeletalMesh(nullptr);
	LocomotionClip.Reset();
	LoadBody();
	ApplyPace();
	if (bRoaming)
	{
		UpdateLocomotion();
	}
	else
	{
		PlaceClub();
	}
}

void AGolfCharacter::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AGolfCharacter, BallLocation);
	DOREPLIFETIME(AGolfCharacter, AimYaw);
	DOREPLIFETIME(AGolfCharacter, bPuttingStance);
	DOREPLIFETIME(AGolfCharacter, bRoaming);
	DOREPLIFETIME(AGolfCharacter, Body);
}

void AGolfCharacter::BeginPlay()
{
	Super::BeginPlay();
	GetCharacterMovement()->DisableMovement();

	LoadBody();
	if (bRoaming)
	{
		ApplyRoaming(); // Replicated before BeginPlay on a late joiner.
	}
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
	// Possession resets the movement mode: walking only while roaming, otherwise placed by code.
	if (bRoaming)
	{
		ApplyRoaming();
		return;
	}
	GetCharacterMovement()->DisableMovement();
	// Not while climbing out of the buggy (it would snap back to the old spot), nor before any address exists.
	if (!bPlayingAction && !BallLocation.IsZero())
	{
		ApplyAddress();
	}
}

void AGolfCharacter::LoadBody()
{
	if (!GetMesh()->GetSkeletalMeshAsset())
	{
		if (USkeletalMesh* BodyMesh = GolferMeshAsset.LoadSynchronous())
		{
			GetMesh()->SetSkeletalMesh(BodyMesh);
		}
	}
	bHasBody = GetMesh()->GetSkeletalMeshAsset() != nullptr;
	if (!bHasBody)
	{
		return;
	}
	// Feet on the ground at the bottom of the capsule, facing the actor's forward.
	GetMesh()->SetRelativeLocationAndRotation(FVector(0.f, 0.f, -GetCapsuleComponent()->GetScaledCapsuleHalfHeight()), FRotator(0.f, MeshYawOffset, 0.f));
	const float BodyHeight = GetMesh()->GetSkeletalMeshAsset()->GetImportedBounds().BoxExtent.Z * 2.f;
	GetMesh()->SetRelativeScale3D(FVector(BodyHeight > 1.f ? GolferHeight / BodyHeight : 1.f));
	GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
	GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
	IdleAnim.LoadSynchronous();
	WalkAnim.LoadSynchronous();
	JogAnim.LoadSynchronous();
	RunAnim.LoadSynchronous();
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
	case EGolferReaction::TeeUp:       return TeeUpAnim.LoadSynchronous();
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
	LocomotionClip.Reset();
	if (bRoaming)
	{
		return; // Walking: Tick plays idle / walk instead.
	}
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
	bClubFitted = false;
	if (!bHasBody || !ClubMesh || bRoaming)
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
	if ((Grip - Head).IsNearlyZero())
	{
		return;
	}
	bClubResting = false;
	SwingLength = 0.f;
	SetClubBetween(Head, Grip, Forward, RightHand);
}

void AGolfCharacter::SetClubBetween(const FVector& Head, const FVector& Grip, const FVector& Forward, FName HandBone)
{
	const UStaticMesh* ClubMesh = Club->GetStaticMesh();
	const FVector Shaft = (Grip - Head).GetSafeNormal();
	if (!ClubMesh || Shaft.IsNearlyZero())
	{
		return;
	}
	// Club mesh: origin at the sole, shaft up +Z, face towards +X (the target).
	const FRotator Rotation = FRotationMatrix::MakeFromZX(Shaft, Forward).Rotator();

	// Fix it to the right hand, keeping this world placement (and real-world size despite the body scale).
	if (Club->GetAttachParent() != GetMesh() || Club->GetAttachSocketName() != HandBone)
	{
		Club->AttachToComponent(GetMesh(), FAttachmentTransformRules(EAttachmentRule::KeepWorld, EAttachmentRule::KeepWorld, EAttachmentRule::KeepWorld, false), HandBone);
	}
	Club->SetWorldLocationAndRotation(Head, Rotation);
	// Stretch the shaft (not the head) so the grip reaches the hands of the scaled-up golfer.
	const float MeshLength = ClubMesh->GetBounds().BoxExtent.Z * 2.f;
	const float Reach = FVector::Dist(Head, Grip) + ClubGripOverhang;
	const float Stretch = MeshLength > 1.f ? FMath::Clamp(Reach / MeshLength, 0.7f, 1.8f) : 1.f;
	Club->SetWorldScale3D(FVector(1.f, 1.f, Stretch));
}

void AGolfCharacter::RestClub()
{
	// After the stroke and through the reactions: the club hangs from the right hand with its head on the
	// ground just outside the right foot, the way a golfer stands holding one.
	bClubFitted = false;
	const FName RightHand = FindBone(*ClubHandBone);
	const FName RightFoot = FindBone(TEXT("RightFoot"));
	if (RightHand.IsNone() || RightFoot.IsNone())
	{
		return;
	}
	const FRotator Facing(0.f, GetActorRotation().Yaw, 0.f);
	const FVector Forward = Facing.Vector();
	const FVector Right = FRotationMatrix(Facing).GetUnitAxis(EAxis::Y);
	const FVector Grip = GetMesh()->GetBoneLocation(RightHand);
	FVector Head = GetMesh()->GetBoneLocation(RightFoot) + Right * ClubRestSide + Forward * ClubRestAhead;
	Head.Z = GetMesh()->GetComponentLocation().Z;  // the mesh origin sits at his soles, on the ground
	SetClubBetween(Head, Grip, Forward, RightHand);
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
	LeaveBuggy();
	SetActorLocationAndRotation(Ground + FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight()), FRotator(0.f, Yaw, 0.f));
	BuggyStep = bEnter ? EBuggyStep::Entering : EBuggyStep::Exiting;
	RiddenBuggy = Buggy;
	SetSeatDrop(bEnter ? 0.f : SeatDrop);

	bPlayingAction = true;
	Club->SetVisibility(false);
	GetMesh()->PlayAnimation(Clip, false);
	GetMesh()->SetPosition(0.f, false);
	GetMesh()->SetPlayRate(BuggyAnimRate);
}

void AGolfCharacter::MulticastSeatInBuggy_Implementation(AGolfBuggy* Buggy)
{
	if (!Buggy)
	{
		return;
	}
	// The climb-in clip has ended on its seated frame; ride along in it rather than vanishing.
	BuggyStep = EBuggyStep::Seated;
	RiddenBuggy = Buggy;
	SetSeatDrop(SeatDrop);
	SetActorHiddenInGame(false);
	GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	if (UPrimitiveComponent* Root = Cast<UPrimitiveComponent>(Buggy->GetRootComponent()))
	{
		Root->IgnoreActorWhenMoving(this, true);
	}
	AttachToActor(Buggy, FAttachmentTransformRules::KeepWorldTransform);
}

void AGolfCharacter::LeaveBuggy()
{
	if (AGolfBuggy* Buggy = RiddenBuggy.Get())
	{
		if (UPrimitiveComponent* Root = Cast<UPrimitiveComponent>(Buggy->GetRootComponent()))
		{
			Root->IgnoreActorWhenMoving(this, false);
		}
	}
	if (GetAttachParentActor())
	{
		DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
	}
	GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	RiddenBuggy.Reset();
}

void AGolfCharacter::SetSeatDrop(float Drop)
{
	GetMesh()->SetRelativeLocation(FVector(0.f, 0.f, -GetCapsuleComponent()->GetScaledCapsuleHalfHeight() - Drop));
}

void AGolfCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bRoaming)
	{
		UpdateLocomotion();
	}
	UpdateIdleFacing(DeltaSeconds);
	if (bClubFitted && bPlayingAction && !bClubResting && Club->IsVisible() && GetMesh()->GetPosition() < SwingLength - 0.05f)
	{
		UpdateClubFit();
	}
	// Once the swing has finished (and through any reaction) the club rests on the ground by his foot.
	if (bHasBody && !bRoaming && Club->IsVisible()
		&& (bClubResting || (SwingLength > 0.f && GetMesh()->GetPosition() >= SwingLength - 0.05f)))
	{
		RestClub();
	}
	if (BuggyStep != EBuggyStep::Entering && BuggyStep != EBuggyStep::Exiting)
	{
		return;
	}
	const UAnimSequence* Clip = (BuggyStep == EBuggyStep::Entering ? EnterBuggyAnim : ExitBuggyAnim).Get();
	const float Length = Clip ? Clip->GetPlayLength() : 0.f;
	if (Length <= 0.f)
	{
		return;
	}
	// Measured on the clips: the hips settle onto the seat at 55-62% of the climb in, and lift off it at
	// 34-46% of the climb out. Ease the extra drop for the low buggy seat in and out over those spans.
	const float T = GetMesh()->GetPosition() / Length;
	SetSeatDrop(BuggyStep == EBuggyStep::Entering
		? SeatDrop * FMath::SmoothStep(0.5f, 0.62f, T)
		: SeatDrop * (1.f - FMath::SmoothStep(0.3f, 0.46f, T)));
	if (BuggyStep == EBuggyStep::Exiting && T >= 1.f)
	{
		BuggyStep = EBuggyStep::None;
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
	// Long Mixamo clips are cut short so the round keeps moving (the putt victory runs until the ball is out).
	const float Cap = Reaction == EGolferReaction::PuttVictory || Reaction == EGolferReaction::TeeUp ? 5.f : 4.f;
	return Clip ? FMath::Min(Clip->GetPlayLength(), Cap) : 0.f;
}

void AGolfCharacter::MulticastPlayReaction_Implementation(EGolferReaction Reaction, FVector CupLocation)
{
	if (UAnimSequence* Clip = bHasBody ? ReactionAsset(Reaction) : nullptr)
	{
		if (Reaction == EGolferReaction::PuttVictory)
		{
			// The clip walks forward and picks the ball out of a cup at CupPickupOffset: stand back from the
			// real cup by that much, keeping the putting direction, so the hand goes into the actual hole.
			const FRotator Facing(0.f, GetActorRotation().Yaw, 0.f);
			const FVector Feet = CupLocation - Facing.RotateVector(CupPickupOffset);
			SetActorLocation(FVector(Feet.X, Feet.Y, CupLocation.Z + GetCapsuleComponent()->GetScaledCapsuleHalfHeight()));
		}
		bPlayingAction = true;
		bClubResting = true;
		GetMesh()->SetPlayRate(1.f);
		GetMesh()->PlayAnimation(Clip, false);
	}
}

void AGolfCharacter::SetAddress(const FVector& InBallLocation, float InAimYaw, bool bPutting)
{
	if (bRoaming)
	{
		SetRoaming(false);
	}
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
	if (bRoaming)
	{
		return; // Walking: the player moves the golfer, not the address.
	}
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

	// Back on foot at the ball: out of the buggy and its low seat.
	if (BuggyStep != EBuggyStep::None)
	{
		LeaveBuggy();
		BuggyStep = EBuggyStep::None;
		SetSeatDrop(0.f);
	}

	// A right-handed golfer stands on the left of the target line, facing the ball.
	FVector Feet = BallLocation - Right * StanceDistance - Aim.Vector() * AddressBackOffset - FVector(0.f, 0.f, GolfPhysics::BallRadius);
	// Stand on the ground under the feet, not at the ball's height (on a slope that sinks or floats the golfer).
	FHitResult Ground;
	const FCollisionQueryParams Params(SCENE_QUERY_STAT(GolferFeet), true, this);
	if (GetWorld() && GetWorld()->LineTraceSingleByObjectType(Ground, Feet + FVector(0.f, 0.f, 150.f), Feet - FVector(0.f, 0.f, 150.f),
		FCollisionObjectQueryParams(ECC_WorldStatic), Params))
	{
		Feet.Z = Ground.ImpactPoint.Z;
	}
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
		// Address with this swing's own first frame (a chip used to start from the drive's, hands 17 cm away),
		// put the club behind the ball for it, then fit the club so its head meets the ball at impact.
		GetWorldTimerManager().ClearTimer(ClubTimer);
		bPlayingAction = false;
		GetMesh()->PlayAnimation(Clip, false);
		GetMesh()->SetPosition(0.f, false);
		GetMesh()->SetPlayRate(0.f);
		PlaceClub();
		FitClubToImpact(GetImpactDelay(Swing));
		bPlayingAction = true;
		bClubResting = false;
		SwingLength = Clip->GetPlayLength();
		GetMesh()->SetPlayRate(1.f);
	}
}

void AGolfCharacter::FitClubToImpact(float ImpactTime)
{
	// The club is fixed to the right hand, but the retargeted swing doesn't bring the hand back exactly to its
	// address spot at impact (the bodies differ from the one the clips were made on), so the head would pass the
	// ball by 5-20 cm. Look ahead to the hand at impact and work out the small turn of the club in the hands
	// (and the shaft length) that puts the head on the ball then; Tick eases it in over the downswing.
	bClubFitted = false;
	const FName RightHand = FindBone(*ClubHandBone);
	const FName LeftHand = FindBone(TEXT("LeftHand"));
	if (ImpactTime <= 0.f || !Club->IsVisible() || Club->GetAttachParent() != GetMesh() || RightHand.IsNone() || LeftHand.IsNone())
	{
		return;
	}
	const FTransform HandAtAddress = GetMesh()->GetSocketTransform(RightHand);
	const FVector Head = Club->GetComponentLocation();  // the club's origin is its sole, set behind the ball
	const FVector Grip = (GetMesh()->GetBoneLocation(RightHand) + GetMesh()->GetBoneLocation(LeftHand)) * 0.5f;
	GetMesh()->SetPosition(ImpactTime, false);
	GetMesh()->TickAnimation(0.f, false);
	GetMesh()->RefreshBoneTransforms();
	const FTransform HandAtImpact = GetMesh()->GetSocketTransform(RightHand);
	GetMesh()->SetPosition(0.f, false);
	GetMesh()->TickAnimation(0.f, false);
	GetMesh()->RefreshBoneTransforms();

	// In the hand's frame: where the grip and head are now, and where the head must be at impact.
	ClubFitPivot = HandAtAddress.InverseTransformPosition(Grip);
	const FVector From = HandAtAddress.InverseTransformPosition(Head) - ClubFitPivot;
	const FVector To = HandAtImpact.InverseTransformPosition(Head) - ClubFitPivot;
	if (From.IsNearlyZero() || To.IsNearlyZero())
	{
		return;
	}
	ClubFitRotation = FQuat::FindBetweenVectors(From, To);
	ClubFitLength = FMath::Clamp(To.Size() / From.Size(), 0.8f, 1.25f);
	ClubFitGripZ = Club->GetComponentTransform().InverseTransformPosition(Grip).Z;
	ClubAddressRelative = Club->GetRelativeTransform();
	ClubImpactTime = ImpactTime;
	bClubFitted = true;
}

void AGolfCharacter::UpdateClubFit()
{
	// Full fit at impact, none at address or once the follow-through is under way.
	const float Time = GetMesh()->GetPosition();
	const float Alpha = FMath::SmoothStep(ClubImpactTime - 0.45f, ClubImpactTime, Time)
		* (1.f - FMath::SmoothStep(ClubImpactTime + 0.05f, ClubImpactTime + 0.5f, Time));
	// Lengthen or shorten the shaft about the grip (the head end moves), then turn the club about the grip.
	const float Length = FMath::Lerp(1.f, ClubFitLength, Alpha);
	const FTransform Shaft(FQuat::Identity, FVector(0.f, 0.f, ClubFitGripZ * (1.f - Length)), FVector(1.f, 1.f, Length));
	const FTransform Turn = FTransform(-ClubFitPivot) * FTransform(FQuat::Slerp(FQuat::Identity, ClubFitRotation, Alpha)) * FTransform(ClubFitPivot);
	Club->SetRelativeTransform(Shaft * ClubAddressRelative * Turn);
}

// ---------------------------------------------------------------- walking

void AGolfCharacter::SetRoaming(bool bRoam)
{
	if (!HasAuthority())
	{
		return;
	}
	bRoaming = bRoam;
	SetReplicateMovement(bRoam);
	ApplyRoaming();
	ForceNetUpdate();
}

void AGolfCharacter::OnRep_Roaming()
{
	ApplyRoaming();
}

void AGolfCharacter::ApplyRoaming()
{
	UCharacterMovementComponent* Movement = GetCharacterMovement();
	LocomotionClip.Reset();
	if (!bRoaming)
	{
		Movement->StopMovementImmediately();
		Movement->DisableMovement();
		Movement->bOrientRotationToMovement = false;
		CameraArm->bEnableCameraLag = false;
		CameraArm->bEnableCameraRotationLag = false;
		CameraArm->SetUsingAbsoluteLocation(true);
		CameraArm->SetUsingAbsoluteRotation(true);
		return;
	}

	// On foot: out of any buggy seat, no club, free to walk.
	if (BuggyStep != EBuggyStep::None)
	{
		LeaveBuggy();
		BuggyStep = EBuggyStep::None;
		SetSeatDrop(0.f);
	}
	bPlayingAction = false;
	Club->SetVisibility(false);
	GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	Movement->MaxWalkSpeed = WalkSpeed;
	Movement->bOrientRotationToMovement = true;
	Movement->SetMovementMode(MOVE_Walking);
	ApplyPace();

	// Follow camera: over the shoulder, trailing the golfer's heading with a little lag.
	CameraArm->SetUsingAbsoluteLocation(false);
	CameraArm->SetUsingAbsoluteRotation(false);
	CameraArm->SetRelativeLocationAndRotation(FVector(0.f, 0.f, 50.f), FRotator(-14.f, 0.f, 0.f));
	CameraArm->TargetArmLength = 460.f;
	CameraArm->SocketOffset = FVector(0.f, 0.f, 40.f);
	CameraArm->bEnableCameraLag = true;
	CameraArm->CameraLagSpeed = 10.f;
	CameraArm->bEnableCameraRotationLag = true;
	CameraArm->CameraRotationLagSpeed = 3.5f;
	Camera->SetFieldOfView(75.f);
	UpdateLocomotion();
}

void AGolfCharacter::UpdateLocomotion()
{
	if (!bHasBody || bPlayingAction)
	{
		return;
	}
	const float Speed = GetVelocity().Size2D();
	const bool bMoving = Speed > 15.f;
	// Walk and fast walk on the walk clip, then the jog clip, then the run clip (each sped up or slowed to the
	// ground speed so the feet don't skate). Switch halfway between the gaits' speeds; fall back to whatever
	// clips were imported.
	const float JogFrom = (FastWalkSpeed + JogSpeed) * 0.5f;
	const float RunFrom = (JogSpeed + RunSpeed) * 0.5f;
	UAnimSequence* Clip = IdleAnim.Get();
	if (bMoving)
	{
		Clip = WalkAnim.Get();
		if (Speed > RunFrom && RunAnim.Get())
		{
			Clip = RunAnim.Get();
		}
		else if (Speed > JogFrom && (JogAnim.Get() || RunAnim.Get()))
		{
			Clip = JogAnim.Get() ? JogAnim.Get() : RunAnim.Get();
		}
	}
	if (!Clip)
	{
		Clip = WalkAnim.Get() ? WalkAnim.Get() : IdleAnim.Get();
	}
	if (!Clip)
	{
		return; // Walk / idle not imported yet: the golfer glides in the last pose.
	}
	if (LocomotionClip.Get() != Clip)
	{
		GetMesh()->PlayAnimation(Clip, true);
		LocomotionClip = Clip;
	}
	float Rate = 1.f;
	if (Clip == RunAnim.Get())
	{
		Rate = FMath::Clamp(Speed / RunAnimSpeed, 0.6f, 2.f);
	}
	else if (Clip == JogAnim.Get())
	{
		Rate = FMath::Clamp(Speed / JogAnimSpeed, 0.6f, 2.f);
	}
	else if (Clip == WalkAnim.Get())
	{
		Rate = FMath::Clamp(Speed / WalkAnimSpeed, 0.6f, 2.f);
	}
	GetMesh()->SetPlayRate(Rate);
}

void AGolfCharacter::UpdateIdleFacing(float DeltaSeconds)
{
	// Standing about on foot, the golfer turns to face this screen's camera; walking, back to where they're going.
	// Only the body turns (not the actor), so the follow camera, which trails the actor, doesn't swing round with
	// them, and it's per screen, so everyone sees every idle golfer face them without touching replication.
	if (!bHasBody)
	{
		return;
	}
	if (!bRoaming)
	{
		// At the ball or in the buggy the body faces the way the code placed it, at once.
		if (IdleFaceYaw != 0.f)
		{
			IdleFaceYaw = 0.f;
			GetMesh()->SetRelativeRotation(FRotator(0.f, MeshYawOffset, 0.f));
		}
		return;
	}
	const bool bIdle = !bPlayingAction && BuggyStep == EBuggyStep::None && GetVelocity().Size2D() <= 15.f;
	float Target = 0.f;
	const APlayerController* Viewer = bIdle ? GetWorld()->GetFirstPlayerController() : nullptr;
	if (Viewer && Viewer->PlayerCameraManager)
	{
		const FVector ToCamera = Viewer->PlayerCameraManager->GetCameraLocation() - GetActorLocation();
		if (ToCamera.Size2D() > 1.f)
		{
			Target = FRotator::NormalizeAxis(ToCamera.Rotation().Yaw - GetActorRotation().Yaw);
		}
	}
	IdleFaceYaw = FMath::FixedTurn(IdleFaceYaw, Target, (bIdle ? IdleTurnRate : 3.f * IdleTurnRate) * DeltaSeconds);
	GetMesh()->SetRelativeRotation(FRotator(0.f, MeshYawOffset + IdleFaceYaw, 0.f));
}

void AGolfCharacter::SetPace(float InPace)
{
	InPace = FMath::Clamp(InPace, 0.f, 1.f);
	if (FMath::IsNearlyEqual(InPace, Pace, 0.01f))
	{
		return;
	}
	Pace = InPace;
	ApplyPace();
	if (!HasAuthority())
	{
		ServerSetPace(InPace); // The server moves the character too, so it needs the same top speed.
	}
}

void AGolfCharacter::ServerSetPace_Implementation(float InPace)
{
	Pace = FMath::Clamp(InPace, 0.f, 1.f);
	ApplyPace();
}

void AGolfCharacter::ApplyPace()
{
	GetCharacterMovement()->MaxWalkSpeed = SpeedForPace(Pace);
}

float AGolfCharacter::SpeedForPace(float InPace) const
{
	// Through the four gaits of the GO bar (walk, fast walk, jog, run each a quarter of it).
	const float Knots[4] = { WalkSpeed, FastWalkSpeed, JogSpeed, RunSpeed };
	const float At[4] = { 0.f, 0.375f, 0.625f, 1.f };
	InPace = FMath::Clamp(InPace, 0.f, 1.f);
	for (int32 Index = 1; Index < 4; ++Index)
	{
		if (InPace <= At[Index])
		{
			return FMath::Lerp(Knots[Index - 1], Knots[Index], (InPace - At[Index - 1]) / (At[Index] - At[Index - 1]));
		}
	}
	return RunSpeed;
}

FString AGolfCharacter::GaitName(float InPace)
{
	return InPace < 0.25f ? TEXT("WALK") : InPace < 0.5f ? TEXT("FAST WALK") : InPace < 0.75f ? TEXT("JOG") : TEXT("RUN");
}

void AGolfCharacter::MulticastStandBesideBuggy_Implementation(AGolfBuggy* Buggy)
{
	if (!Buggy)
	{
		return;
	}
	// Where the climb-out clip leaves the golfer: by the driver's door, where the climb in starts.
	const FTransform BuggyFrame(FRotator(0.f, Buggy->GetActorRotation().Yaw, 0.f), Buggy->GetActorLocation() - FVector(0.f, 0.f, AGolfBuggy::RideHeight));
	FVector Feet = BuggyFrame.TransformPosition(DriverSeat + EnterStartFromSeat);
	FHitResult Ground;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(GolferStand), true, this);
	Params.AddIgnoredActor(Buggy);
	if (GetWorld()->LineTraceSingleByObjectType(Ground, Feet + FVector(0.f, 0.f, 200.f), Feet - FVector(0.f, 0.f, 300.f),
		FCollisionObjectQueryParams(ECC_WorldStatic), Params))
	{
		Feet.Z = Ground.ImpactPoint.Z;
	}
	LeaveBuggy();
	BuggyStep = EBuggyStep::None;
	SetSeatDrop(0.f);
	bPlayingAction = false;
	LocomotionClip.Reset();
	SetActorHiddenInGame(false);
	SetActorLocationAndRotation(Feet + FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 2.f),
		FRotator(0.f, Buggy->GetActorRotation().Yaw - 90.f, 0.f));
}
