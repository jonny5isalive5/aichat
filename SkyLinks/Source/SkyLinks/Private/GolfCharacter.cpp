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
}

void AGolfCharacter::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AGolfCharacter, BallLocation);
	DOREPLIFETIME(AGolfCharacter, AimYaw);
}

void AGolfCharacter::BeginPlay()
{
	Super::BeginPlay();
	GetCharacterMovement()->DisableMovement();

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

void AGolfCharacter::SetAddress(const FVector& InBallLocation, float InAimYaw)
{
	BallLocation = InBallLocation;
	AimYaw = InAimYaw;
	ApplyAddress();
}

void AGolfCharacter::SetLocalAim(float InAimYaw)
{
	AimYaw = InAimYaw;
	ApplyAddress();
	ServerSetAim(InAimYaw);
}

void AGolfCharacter::ServerSetAim_Implementation(float InAimYaw)
{
	AimYaw = InAimYaw;
	ApplyAddress();
}

void AGolfCharacter::OnRep_Address()
{
	ApplyAddress();
}

void AGolfCharacter::ApplyAddress()
{
	const FRotator Aim(0.f, AimYaw, 0.f);
	const FVector Right = FRotationMatrix(Aim).GetUnitAxis(EAxis::Y);
	const float HalfHeight = GetCapsuleComponent()->GetScaledCapsuleHalfHeight();

	// A right-handed golfer stands on the left of the target line, facing the ball.
	const FVector Feet = BallLocation - Right * StanceDistance - FVector(0.f, 0.f, GolfPhysics::BallRadius);
	SetActorLocationAndRotation(Feet + FVector(0.f, 0.f, HalfHeight), FRotator(0.f, AimYaw + 90.f, 0.f));

	CameraArm->SetWorldLocationAndRotation(BallLocation + FVector(0.f, 0.f, 60.f), FRotator(-8.f, AimYaw, 0.f));
}

void AGolfCharacter::MulticastPlaySwing_Implementation()
{
	if (SwingMontage)
	{
		PlayAnimMontage(SwingMontage);
	}
}
