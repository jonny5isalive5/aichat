#include "GolfBuggy.h"
#include "SkyLinks.h"
#include "GolfPhysics.h"
#include "Camera/CameraComponent.h"
#include "Components/BoxComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/SpringArmComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Net/UnrealNetwork.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
	constexpr float SyncInterval = 0.05f;   // 20 position updates a second from the driver
	constexpr float ProxyFollowSpeed = 10.f;
}

AGolfBuggy::AGolfBuggy()
{
	PrimaryActorTick.bCanEverTick = true;
	bReplicates = true;
	bAlwaysRelevant = true;
	SetReplicateMovement(false);

	// Collision only blocks the world (trees, buildings); it ignores golfers, other buggies and balls.
	Collision = CreateDefaultSubobject<UBoxComponent>(TEXT("Collision"));
	Collision->SetBoxExtent(FVector(130.f, 62.f, 55.f));
	Collision->SetCollisionProfileName(TEXT("Pawn"));
	Collision->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
	Collision->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
	Collision->SetCollisionResponseToChannel(ECC_GolfBall, ECR_Ignore);
	RootComponent = Collision;

	auto MakeMesh = [this](const TCHAR* Name)
	{
		UStaticMeshComponent* Part = CreateDefaultSubobject<UStaticMeshComponent>(Name);
		Part->SetupAttachment(Collision);
		Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		return Part;
	};
	Body = MakeMesh(TEXT("Body"));
	WheelFL = MakeMesh(TEXT("WheelFL"));
	WheelFR = MakeMesh(TEXT("WheelFR"));
	WheelRL = MakeMesh(TEXT("WheelRL"));
	WheelRR = MakeMesh(TEXT("WheelRR"));

	BodyMeshAsset = TSoftObjectPtr<UStaticMesh>(FSoftObjectPath(TEXT("/Game/Vehicles/Buggy/SM_Buggy_Body.SM_Buggy_Body")));
	WheelMeshAsset = TSoftObjectPtr<UStaticMesh>(FSoftObjectPath(TEXT("/Game/Vehicles/Buggy/SM_Buggy_Wheel.SM_Buggy_Wheel")));

	// Chase camera behind and above, following the buggy's heading with a little lag.
	CameraArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraArm"));
	CameraArm->SetupAttachment(Collision);
	CameraArm->TargetArmLength = 650.f;
	CameraArm->SocketOffset = FVector(0.f, 0.f, 140.f);
	CameraArm->SetRelativeRotation(FRotator(-12.f, 0.f, 0.f));
	CameraArm->bInheritPitch = false;
	CameraArm->bInheritRoll = false;
	CameraArm->bEnableCameraLag = true;
	CameraArm->bEnableCameraRotationLag = true;
	CameraArm->CameraLagSpeed = 8.f;
	CameraArm->CameraRotationLagSpeed = 5.f;
	CameraArm->bDoCollisionTest = true;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(CameraArm);
	Camera->SetFieldOfView(75.f);
}

void AGolfBuggy::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	// The driver ignores this while driving, but needs it once they get out so the parked buggy stays put.
	DOREPLIFETIME(AGolfBuggy, NetState);
}

void AGolfBuggy::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	LoadMeshes();
}

void AGolfBuggy::BeginPlay()
{
	Super::BeginPlay();
	LoadMeshes();
	LastLocation = GetActorLocation();
	if (HasAuthority())
	{
		PublishState();
	}
}

void AGolfBuggy::LoadMeshes()
{
	UStaticMesh* BodyMesh = BodyMeshAsset.LoadSynchronous();
	UStaticMesh* WheelMesh = WheelMeshAsset.LoadSynchronous();

	// The body's origin is on the ground between the axles.
	Body->SetRelativeLocation(FVector(0.f, 0.f, -RideHeight));
	Body->SetRelativeRotation(FRotator(0.f, BodyYawOffset, 0.f));
	if (BodyMesh)
	{
		Body->SetStaticMesh(BodyMesh);
		Body->SetRelativeScale3D(FVector::OneVector);
	}
	else if (UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")))
	{
		// Stand-in until the Blender body is imported: a white 2.4 x 1.2 m tub.
		Body->SetStaticMesh(Cube);
		Body->SetRelativeLocation(FVector(0.f, 0.f, 60.f - RideHeight));
		Body->SetRelativeScale3D(FVector(2.4f, 1.2f, 0.7f));
		if (UMaterialInstanceDynamic* Material = Body->CreateAndSetMaterialInstanceDynamic(0))
		{
			Material->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.85f, 0.85f, 0.83f));
		}
	}

	bUsingFallbackWheels = WheelMesh == nullptr;
	UStaticMesh* Wheel = WheelMesh ? WheelMesh : LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	const float Z = WheelRadius - RideHeight;
	const TPair<UStaticMeshComponent*, FVector> Placement[] = {
		{ WheelFL, FVector(WheelBase * 0.5f, -Track * 0.5f, Z) },
		{ WheelFR, FVector(WheelBase * 0.5f, Track * 0.5f, Z) },
		{ WheelRL, FVector(-WheelBase * 0.5f, -Track * 0.5f, Z) },
		{ WheelRR, FVector(-WheelBase * 0.5f, Track * 0.5f, Z) },
	};
	for (const TPair<UStaticMeshComponent*, FVector>& Entry : Placement)
	{
		Entry.Key->SetStaticMesh(Wheel);
		Entry.Key->SetRelativeLocation(Entry.Value);
		Entry.Key->SetRelativeScale3D(bUsingFallbackWheels ? FVector(WheelRadius * 2.f / 100.f, WheelRadius * 2.f / 100.f, 0.18f) : FVector::OneVector);
		if (bUsingFallbackWheels)
		{
			if (UMaterialInstanceDynamic* Material = Entry.Key->CreateAndSetMaterialInstanceDynamic(0))
			{
				Material->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.02f, 0.02f, 0.02f));
			}
		}
	}
	AnimateWheels(0.f);
}

void AGolfBuggy::SetDriveInput(float InThrottle, float InSteer)
{
	Throttle = FMath::Clamp(InThrottle, -1.f, 1.f);
	SteerInput = FMath::Clamp(InSteer, -1.f, 1.f);
}

void AGolfBuggy::ParkAt(const FVector& Location, float Yaw)
{
	FVector Ground = Location;
	FRotator Rotation(0.f, Yaw, 0.f);
	bool bWater = false;
	SampleGround(Location, Yaw, Ground, Rotation, bWater);
	Speed = 0.f;
	SteerAngle = 0.f;
	SetActorLocationAndRotation(Ground, Rotation, false, nullptr, ETeleportType::TeleportPhysics);
	LastLocation = Ground;
	PublishState();
	MulticastTeleport(Ground, Rotation);
}

void AGolfBuggy::MulticastTeleport_Implementation(FVector Location, FRotator Rotation)
{
	Speed = 0.f;
	SteerAngle = 0.f;
	SetActorLocationAndRotation(Location, Rotation, false, nullptr, ETeleportType::TeleportPhysics);
	LastLocation = Location;
	NetState.Location = Location;
	NetState.Rotation = Rotation;
	NetState.Speed = 0.f;
	NetState.Steer = 0.f;
}

void AGolfBuggy::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (IsLocallyControlled())
	{
		Drive(DeltaSeconds);
		SyncTimer -= DeltaSeconds;
		if (HasAuthority())
		{
			PublishState();
		}
		else if (SyncTimer <= 0.f)
		{
			SyncTimer = SyncInterval;
			ServerSyncMove(GetActorLocation(), GetActorRotation(), Speed, SteerAngle);
		}
	}
	else if (!HasAuthority())
	{
		FollowProxy(DeltaSeconds);
	}
	else
	{
		// Server copy of a buggy someone else is driving: position arrives through ServerSyncMove.
		Speed = NetState.Speed;
		SteerAngle = NetState.Steer;
	}
	AnimateWheels(DeltaSeconds);
}

void AGolfBuggy::PublishState()
{
	NetState.Location = GetActorLocation();
	NetState.Rotation = GetActorRotation();
	NetState.Speed = Speed;
	NetState.Steer = SteerAngle;
}

void AGolfBuggy::ServerSyncMove_Implementation(FVector_NetQuantize10 Location, FRotator Rotation, float InSpeed, float InSteer)
{
	// Casual game: trust the driver's position, but ignore anything faster than the buggy can go.
	const float Allowed = (MaxSpeed * 1.5f) * 0.5f + 200.f;
	if (FVector::Dist(Location, GetActorLocation()) > Allowed)
	{
		return;
	}
	SetActorLocationAndRotation(Location, Rotation);
	Speed = InSpeed;
	SteerAngle = InSteer;
	PublishState();
}

void AGolfBuggy::FollowProxy(float DeltaSeconds)
{
	const FVector Location = FMath::VInterpTo(GetActorLocation(), NetState.Location, DeltaSeconds, ProxyFollowSpeed);
	const FRotator Rotation = FMath::RInterpTo(GetActorRotation(), NetState.Rotation, DeltaSeconds, ProxyFollowSpeed);
	SetActorLocationAndRotation(Location, Rotation);
	Speed = NetState.Speed;
	SteerAngle = NetState.Steer;
}

void AGolfBuggy::Drive(float DeltaSeconds)
{
	// Pedals: accelerate, brake when pushing against the direction of travel, coast otherwise.
	if (Throttle > 0.f)
	{
		Speed += (Speed < 0.f ? BrakeDeceleration : Acceleration * Throttle) * DeltaSeconds;
	}
	else if (Throttle < 0.f)
	{
		Speed -= (Speed > 0.f ? BrakeDeceleration : Acceleration * 0.6f * -Throttle) * DeltaSeconds;
	}
	else
	{
		Speed = FMath::FInterpConstantTo(Speed, 0.f, DeltaSeconds, CoastDeceleration);
	}
	Speed = FMath::Clamp(Speed, -MaxReverseSpeed, MaxSpeed);

	// Much less steering lock at speed keeps it stable (full lock only when slow).
	const float SpeedFactor = 1.f - 0.8f * FMath::Clamp(FMath::Abs(Speed) / MaxSpeed, 0.f, 1.f);
	SteerAngle = FMath::FInterpTo(SteerAngle, SteerInput * MaxSteerAngle * SpeedFactor, DeltaSeconds, 6.f);

	// Bicycle model: yaw rate from speed, wheelbase and steering angle.
	const float YawRate = FMath::RadiansToDegrees(Speed / WheelBase * FMath::Tan(FMath::DegreesToRadians(SteerAngle)));
	const float Yaw = GetActorRotation().Yaw + YawRate * DeltaSeconds;
	const FVector Forward = FRotator(0.f, Yaw, 0.f).Vector();
	const FVector Target = GetActorLocation() + Forward * Speed * DeltaSeconds;

	FVector Ground;
	FRotator Rotation;
	bool bWater = false;
	if (!SampleGround(Target, Yaw, Ground, Rotation, bWater) || bWater)
	{
		Speed = 0.f; // Edge of the course or the water's edge: stop.
		return;
	}

	FHitResult Hit;
	SetActorLocationAndRotation(Ground, Rotation, true, &Hit);
	if (Hit.bBlockingHit)
	{
		Speed *= -0.2f; // Bumped into a tree or wall.
	}
}

bool AGolfBuggy::SampleGround(const FVector& Center, float Yaw, FVector& OutLocation, FRotator& OutRotation, bool& bOutWater) const
{
	const UWorld* World = GetWorld();
	const FRotator Heading(0.f, Yaw, 0.f);
	const FVector Forward = Heading.Vector();
	const FVector Right = FRotationMatrix(Heading).GetUnitAxis(EAxis::Y);
	const FVector Wheels[4] = {
		Center + Forward * WheelBase * 0.5f - Right * Track * 0.5f,
		Center + Forward * WheelBase * 0.5f + Right * Track * 0.5f,
		Center - Forward * WheelBase * 0.5f - Right * Track * 0.5f,
		Center - Forward * WheelBase * 0.5f + Right * Track * 0.5f,
	};

	FCollisionQueryParams Params(SCENE_QUERY_STAT(BuggyGround), false, this);
	Params.bReturnPhysicalMaterial = true;
	const FCollisionObjectQueryParams Objects(ECC_WorldStatic);

	float Heights[4];
	bOutWater = false;
	for (int32 Index = 0; Index < 4; ++Index)
	{
		FHitResult Hit;
		const FVector Top(Wheels[Index].X, Wheels[Index].Y, Center.Z + 150.f);
		const FVector Bottom(Wheels[Index].X, Wheels[Index].Y, Center.Z - 400.f);
		if (!World->LineTraceSingleByObjectType(Hit, Top, Bottom, Objects, Params))
		{
			return false;
		}
		Heights[Index] = Hit.ImpactPoint.Z;
		bOutWater |= GolfPhysics::LieFromHit(Hit) == EGolfLie::Water;
	}

	const float Front = (Heights[0] + Heights[1]) * 0.5f;
	const float Rear = (Heights[2] + Heights[3]) * 0.5f;
	const float Left = (Heights[0] + Heights[2]) * 0.5f;
	const float RightSide = (Heights[1] + Heights[3]) * 0.5f;
	const float Pitch = FMath::RadiansToDegrees(FMath::Atan2(Front - Rear, WheelBase));
	const float Roll = FMath::RadiansToDegrees(FMath::Atan2(Left - RightSide, Track));

	OutRotation = FRotator(Pitch, Yaw, Roll);
	OutLocation = FVector(Center.X, Center.Y, (Front + Rear) * 0.5f + RideHeight);
	return true;
}

void AGolfBuggy::AnimateWheels(float DeltaSeconds)
{
	// Roll the wheels by the distance actually travelled (works for driver and watchers alike).
	const FVector Location = GetActorLocation();
	const float Travelled = FVector::DotProduct(Location - LastLocation, GetActorForwardVector());
	LastLocation = Location;
	if (FMath::Abs(Travelled) < 500.f)
	{
		WheelSpin = FMath::Fmod(WheelSpin - FMath::RadiansToDegrees(Travelled / WheelRadius), 360.f);
	}

	// Imported wheel: axle along Y, hub facing -Y (the left). Engine cylinder: axle along Z.
	const FQuat Base = bUsingFallbackWheels ? FQuat(FRotator(0.f, 0.f, 90.f)) : FQuat::Identity;
	auto Pose = [&](UStaticMeshComponent* Wheel, float Steer, bool bRightSide)
	{
		const float Spin = bRightSide ? -WheelSpin : WheelSpin;
		const float Yaw = Steer + (bRightSide && !bUsingFallbackWheels ? 180.f : 0.f);
		Wheel->SetRelativeRotation(FQuat(FRotator(Spin, Yaw, 0.f)) * Base);
	};
	Pose(WheelFL, SteerAngle, false);
	Pose(WheelFR, SteerAngle, true);
	Pose(WheelRL, 0.f, false);
	Pose(WheelRR, 0.f, true);
}
