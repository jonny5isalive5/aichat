#include "GolfBall.h"
#include "SkyLinks.h"
#include "Components/StaticMeshComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Camera/CameraComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Net/UnrealNetwork.h"
#include "UObject/ConstructorHelpers.h"


AGolfBall::AGolfBall()
{
	PrimaryActorTick.bCanEverTick = true;
	bReplicates = true;
	bAlwaysRelevant = true;
	SetReplicateMovement(false);

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(Root);
	Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	if (Sphere.Succeeded())
	{
		Mesh->SetStaticMesh(Sphere.Object);
	}
	// The visual is deliberately enlarged (VisualScale). Collision and the physics sweeps still use
	// GolfPhysics::BallRadius, so this does not make shots easier or alter rolls.
	// Engine sphere is 100 cm across. Lift the enlarged mesh so it still sits on the ground.
	Mesh->SetRelativeScale3D(FVector(GolfPhysics::BallRadius * 2.f * VisualScale / 100.f));
	Mesh->SetRelativeLocation(FVector(0.f, 0.f, GolfPhysics::BallRadius * (VisualScale - 1.f)));

	ChaseArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("ChaseArm"));
	ChaseArm->SetupAttachment(Root);
	ChaseArm->SetUsingAbsoluteRotation(true);
	ChaseArm->TargetArmLength = ChaseDistance;
	ChaseArm->SocketOffset = FVector(0.f, 0.f, 60.f);
	ChaseArm->bDoCollisionTest = false;
	ChaseArm->bEnableCameraLag = true;
	ChaseArm->CameraLagSpeed = 8.f;

	ChaseCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("ChaseCamera"));
	ChaseCamera->SetupAttachment(ChaseArm);
	ChaseCamera->SetFieldOfView(75.f);
}

void AGolfBall::BeginPlay()
{
	Super::BeginPlay();
	// Clean white finish. Done here rather than in the constructor so no material instance is
	// created on the class default object.
	if (UMaterialInstanceDynamic* BallMaterial = Mesh->CreateAndSetMaterialInstanceDynamic(0))
	{
		BallMaterial->SetVectorParameterValue(TEXT("Color"), FLinearColor::White);
	}
}

void AGolfBall::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AGolfBall, RestLocation);
	DOREPLIFETIME(AGolfBall, RestLie);
}

void AGolfBall::Launch(const FGolfBallState& State, const FVector& Wind, const FVector& CupLocation, float InCupRadius)
{
	check(HasAuthority());
	MulticastLaunch(State.Location, State.Velocity, State.SpinAxis, State.SpinRate, Wind, CupLocation, InCupRadius);
}

void AGolfBall::MulticastLaunch_Implementation(FVector Start, FVector Velocity, FVector SpinAxis, float SpinRate, FVector Wind, FVector CupLocation, float InCupRadius)
{
	Sim.Location = Start;
	FallLimit = Start.Z - GolfPhysics::KillDepth;
	Sim.Velocity = Velocity;
	Sim.SpinAxis = SpinAxis;
	Sim.SpinRate = SpinRate;
	SimWind = Wind;
	Cup = CupLocation;
	CupRadius = InCupRadius;
	Accumulator = SimTime = RestTimer = 0.f;
	Mode = Velocity.Z > 1.f ? EMode::Flight : EMode::Roll;

	// Start the chase camera directly behind the shot line.
	ChaseYaw = FVector(Velocity.X, Velocity.Y, 0.f).Rotation().Yaw;
	UpdateChaseCamera(0.f, true);
}

void AGolfBall::PlaceAt(const FVector& Location, bool bOnTee)
{
	check(HasAuthority());
	Sim = FGolfBallState();
	Sim.Location = Location;
	Mode = EMode::Rest;
	RestLocation = Location;
	RestLie = bOnTee ? EGolfLie::Tee : ProbeLie(Location);
	SetActorLocation(Location);
	MulticastSettle(Location);
}

void AGolfBall::MulticastSettle_Implementation(FVector Location)
{
	Mode = EMode::Rest;
	Sim.Location = Location;
	Sim.Velocity = FVector::ZeroVector;
	SetActorLocation(Location);
}

void AGolfBall::OnRep_RestLocation()
{
	if (Mode == EMode::Rest)
	{
		Sim.Location = RestLocation;
		SetActorLocation(RestLocation);
	}
}

void AGolfBall::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (Mode == EMode::Rest)
	{
		return;
	}

	Accumulator += FMath::Min(DeltaSeconds, 0.1f);
	while (Accumulator >= GolfPhysics::FixedStep && Mode != EMode::Rest)
	{
		Simulate(GolfPhysics::FixedStep);
		Accumulator -= GolfPhysics::FixedStep;
	}
	SetActorLocation(Sim.Location);
	UpdateChaseCamera(DeltaSeconds, false);
}

void AGolfBall::UpdateChaseCamera(float DeltaSeconds, bool bSnap)
{
	// Keep the camera behind the ball: turn toward the horizontal direction of travel.
	const FVector Flat(Sim.Velocity.X, Sim.Velocity.Y, 0.f);
	if (Flat.SizeSquared() > 400.f)
	{
		const float TargetYaw = Flat.Rotation().Yaw;
		ChaseYaw = bSnap ? TargetYaw : FMath::FixedTurn(ChaseYaw, TargetYaw, ChaseTurnSpeed * 60.f * DeltaSeconds);
	}

	// Look down a little more while the ball rolls so the ground and cup stay in view.
	const float Pitch = Mode == EMode::Flight ? ChasePitch : ChasePitch - 8.f;
	ChaseArm->SetWorldRotation(FRotator(Pitch, ChaseYaw, 0.f));
	ChaseArm->TargetArmLength = ChaseDistance;
}

void AGolfBall::Simulate(float Dt)
{
	SimTime += Dt;
	if (SimTime > 40.f)
	{
		Finish(EGolfShotResult::Resting);
		return;
	}

	switch (Mode)
	{
	case EMode::Flight: StepFlightMode(Dt); break;
	case EMode::Roll:   StepRollMode(Dt);   break;
	case EMode::Holing: StepHoling(Dt);     break;
	default: break;
	}
}

bool AGolfBall::IsOverCup() const
{
	const FVector Delta = Sim.Location - Cup;
	return FVector2D(Delta.X, Delta.Y).Size() < CupRadius && FMath::Abs(Delta.Z) < 30.f;
}

void AGolfBall::StepFlightMode(float Dt)
{
	const FVector Previous = Sim.Location;
	GolfPhysics::StepFlight(Sim, SimWind, Dt);

	FHitResult Hit;
	if (GolfPhysics::SweepBall(GetWorld(), Previous, Sim.Location, Hit, this))
	{
		const EGolfLie Lie = GolfPhysics::LieFromHit(Hit);
		Sim.Location = Hit.Location + Hit.ImpactNormal * 0.1f;

		if (Lie == EGolfLie::Water)       { Finish(EGolfShotResult::Water); return; }
		if (Lie == EGolfLie::OutOfBounds) { Finish(EGolfShotResult::OutOfBounds); return; }
		if (IsOverCup())                  { BeginHoling(); return; }

		const FGolfSurfaceParams& Surface = GolfPhysics::GetSurface(Lie);
		const FVector N = Hit.ImpactNormal;
		const float NormalSpeed = FVector::DotProduct(Sim.Velocity, N);
		const FVector NormalPart = N * NormalSpeed;
		FVector Tangent = Sim.Velocity - NormalPart;

		// Backspin makes the ball check up, most of all on the green.
		const float Bite = FMath::Clamp(Sim.SpinRate / 800.f, 0.f, 1.f) * (Lie == EGolfLie::Green ? 0.5f : 0.25f);
		Tangent *= FMath::Max(0.f, 1.f - Surface.BounceFriction - Bite);

		Sim.Velocity = Tangent - NormalPart * Surface.Restitution;
		Sim.SpinRate *= 0.4f;

		if (N.Z > 0.3f && FMath::Abs(NormalSpeed) * Surface.Restitution < 150.f)
		{
			Mode = EMode::Roll;
			Sim.Velocity = FVector::VectorPlaneProject(Sim.Velocity, N);
		}
	}

	if (Sim.Location.Z < FallLimit)
	{
		Finish(EGolfShotResult::OutOfBounds);
	}
}

void AGolfBall::StepRollMode(float Dt)
{
	const UWorld* World = GetWorld();

	FHitResult Ground;
	if (!GolfPhysics::SweepBall(World, Sim.Location + FVector(0.f, 0.f, 3.f), Sim.Location - FVector(0.f, 0.f, 6.f), Ground, this) || Ground.ImpactNormal.Z < 0.3f)
	{
		// Rolled off an edge.
		Mode = EMode::Flight;
		return;
	}

	const EGolfLie Lie = GolfPhysics::LieFromHit(Ground);
	if (Lie == EGolfLie::Water)       { Finish(EGolfShotResult::Water); return; }
	if (Lie == EGolfLie::OutOfBounds) { Finish(EGolfShotResult::OutOfBounds); return; }

	const FVector N = Ground.ImpactNormal;
	Sim.Location = Ground.Location + N * 0.1f;

	const FGolfSurfaceParams& Surface = GolfPhysics::GetSurface(Lie);
	const FVector Slope = FVector::VectorPlaneProject(FVector(0.f, 0.f, -GolfPhysics::Gravity), N);
	FVector Velocity = FVector::VectorPlaneProject(Sim.Velocity, N) + Slope * Dt;

	float Speed = Velocity.Size();
	const float Decel = Surface.RollDecel * Dt;
	Velocity = Speed > Decel ? Velocity * ((Speed - Decel) / Speed) : FVector::ZeroVector;
	Speed = Velocity.Size();

	if (IsOverCup())
	{
		if (Speed < 150.f)
		{
			BeginHoling();
			return;
		}
		Velocity *= 0.85f; // Lipped: too fast to drop.
	}

	const FVector Target = Sim.Location + Velocity * Dt;
	FHitResult Blocker;
	if (GolfPhysics::SweepBall(World, Sim.Location, Target, Blocker, this))
	{
		const EGolfLie BlockerLie = GolfPhysics::LieFromHit(Blocker);
		if (BlockerLie == EGolfLie::Water)       { Finish(EGolfShotResult::Water); return; }
		if (BlockerLie == EGolfLie::OutOfBounds) { Finish(EGolfShotResult::OutOfBounds); return; }

		Sim.Location = Blocker.Location + Blocker.ImpactNormal * 0.1f;
		if (Blocker.ImpactNormal.Z < 0.3f)
		{
			Velocity = Velocity.MirrorByVector(Blocker.ImpactNormal) * 0.4f;
		}
	}
	else
	{
		Sim.Location = Target;
	}
	Sim.Velocity = Velocity;

	if (Speed < 3.f && Slope.Size() <= Surface.RollDecel)
	{
		RestTimer += Dt;
		if (RestTimer > 0.25f)
		{
			Finish(EGolfShotResult::Resting);
		}
	}
	else
	{
		RestTimer = 0.f;
	}
}

void AGolfBall::BeginHoling()
{
	Mode = EMode::Holing;
	HolingTime = 0.f;
	HolingStart = Sim.Location;
	Sim.Velocity = FVector::ZeroVector;
}

void AGolfBall::StepHoling(float Dt)
{
	HolingTime += Dt;
	const float Alpha = FMath::Clamp(HolingTime / 0.35f, 0.f, 1.f);
	Sim.Location = FMath::Lerp(HolingStart, Cup - FVector(0.f, 0.f, 8.f), Alpha);
	if (Alpha >= 1.f)
	{
		Finish(EGolfShotResult::Holed);
	}
}

void AGolfBall::Finish(EGolfShotResult Result)
{
	Mode = EMode::Rest;
	Accumulator = 0.f;
	Sim.Velocity = FVector::ZeroVector;
	SetActorLocation(Sim.Location);

	if (HasAuthority())
	{
		RestLocation = Sim.Location;
		if (Result == EGolfShotResult::Resting)
		{
			RestLie = ProbeLie(Sim.Location);
		}
		MulticastSettle(Sim.Location);
		OnStopped.Broadcast(this, Result);
	}
}

EGolfLie AGolfBall::ProbeLie(const FVector& At) const
{
	FHitResult Hit;
	if (GolfPhysics::SweepBall(GetWorld(), At + FVector(0.f, 0.f, 5.f), At - FVector(0.f, 0.f, 20.f), Hit, this))
	{
		return GolfPhysics::LieFromHit(Hit);
	}
	return EGolfLie::Rough;
}
