#include "GolfPhysics.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "SkyLinks.h"
#include "Engine/World.h"
#include "Engine/HitResult.h"
#include "CollisionQueryParams.h"
#include "CollisionShape.h"
#include "PhysicalMaterials/PhysicalMaterial.h"

namespace
{
	FGolfClub MakeClub(const TCHAR* Name, float SpeedMetersPerSecond, float Angle, float Rpm, float Error, bool bPutter)
	{
		FGolfClub Club;
		Club.ShortName = Name;
		Club.LaunchSpeed = SpeedMetersPerSecond * 100.f;
		Club.LaunchAngle = Angle;
		Club.BackspinRpm = Rpm;
		Club.ErrorDegrees = Error;
		Club.bIsPutter = bPutter;
		return Club;
	}

	TArray<FGolfClub> MakeBag()
	{
		return {
			MakeClub(TEXT("1W"), 70.f, 11.f, 2600.f, 8.f, false),
			MakeClub(TEXT("3W"), 64.f, 13.f, 3500.f, 7.f, false),
			MakeClub(TEXT("5I"), 54.f, 16.f, 5000.f, 6.f, false),
			MakeClub(TEXT("7I"), 48.f, 19.f, 6500.f, 5.f, false),
			MakeClub(TEXT("9I"), 42.f, 24.f, 8000.f, 4.f, false),
			MakeClub(TEXT("PW"), 38.f, 28.f, 9000.f, 4.f, false),
			MakeClub(TEXT("SW"), 30.f, 34.f, 10000.f, 3.f, false),
			MakeClub(TEXT("PT"), 7.f, 0.f, 0.f, 1.5f, true),
		};
	}
}

const TArray<FGolfClub>& GolfPhysics::GetClubBag()
{
	static const TArray<FGolfClub> Bag = MakeBag();
	return Bag;
}

int32 GolfPhysics::GetPutterIndex()
{
	return GetClubBag().IndexOfByPredicate([](const FGolfClub& Club) { return Club.bIsPutter; });
}

const FGolfSurfaceParams& GolfPhysics::GetSurface(EGolfLie Lie)
{
	static const FGolfSurfaceParams Fairway{ 0.35f, 0.25f, 110.f, 1.f };
	static const FGolfSurfaceParams Rough{ 0.2f, 0.5f, 350.f, 0.85f };
	static const FGolfSurfaceParams Bunker{ 0.05f, 0.8f, 900.f, 0.6f };
	static const FGolfSurfaceParams Green{ 0.3f, 0.2f, 60.f, 1.f };

	switch (Lie)
	{
	case EGolfLie::Tee:
	case EGolfLie::Fairway: return Fairway;
	case EGolfLie::Bunker:  return Bunker;
	case EGolfLie::Green:   return Green;
	default:                return Rough;
	}
}

EGolfLie GolfPhysics::LieFromHit(const FHitResult& Hit)
{
	switch (UPhysicalMaterial::DetermineSurfaceType(Hit.PhysMaterial.Get()))
	{
	case SURFACE_Fairway:     return EGolfLie::Fairway;
	case SURFACE_Bunker:      return EGolfLie::Bunker;
	case SURFACE_Green:       return EGolfLie::Green;
	case SURFACE_Water:       return EGolfLie::Water;
	case SURFACE_OutOfBounds: return EGolfLie::OutOfBounds;
	default:                  return EGolfLie::Rough;
	}
}

FString GolfPhysics::LieName(EGolfLie Lie)
{
	switch (Lie)
	{
	case EGolfLie::Tee:     return TEXT("TEE");
	case EGolfLie::Fairway: return TEXT("FAIRWAY");
	case EGolfLie::Rough:   return TEXT("ROUGH");
	case EGolfLie::Bunker:  return TEXT("BUNKER");
	case EGolfLie::Green:   return TEXT("GREEN");
	case EGolfLie::Water:   return TEXT("WATER");
	default:                return TEXT("OB");
	}
}

void GolfPhysics::StepFlight(FGolfBallState& State, const FVector& Wind, float Dt)
{
	FVector Accel(0.f, 0.f, -Gravity);

	const FVector Relative = State.Velocity - Wind;
	const float Speed = Relative.Size();
	if (Speed > 1.f)
	{
		Accel -= DragK * Speed * Relative;

		// Magnus lift: lift coefficient grows with spin ratio, capped.
		const float SpinRatio = BallRadius * State.SpinRate / Speed;
		const float LiftCoefficient = FMath::Min(0.3f, 2.f * SpinRatio);
		const FVector LiftDir = FVector::CrossProduct(State.SpinAxis, Relative).GetSafeNormal();
		Accel += LiftDir * LiftCoefficient * (DragK / DragCoefficient) * Speed * Speed;
	}

	State.Velocity += Accel * Dt;
	State.Location += State.Velocity * Dt;
	State.SpinRate *= FMath::Exp(-Dt / SpinDecaySeconds);
}

FGolfBallState GolfPhysics::MakeLaunch(const FGolfClub& Club, const FGolfShotInput& Input, EGolfLie Lie, const FVector& Start)
{
	FGolfBallState State;
	State.Location = Start;

	const float Power = FMath::Clamp(Input.Power, 0.f, 1.1f);
	const float Accuracy = FMath::Clamp(Input.Accuracy, -1.f, 1.f);
	const float LieScale = Club.bIsPutter ? 1.f : GetSurface(Lie).PowerScale;
	const float Overdrive = Power > 1.f ? 1.6f : 1.f;

	const float Speed = Club.LaunchSpeed * Power * LieScale;
	const float Yaw = Input.AimYaw + Accuracy * Club.ErrorDegrees * Overdrive;
	const float Pitch = Club.bIsPutter ? 0.f : FMath::Max(2.f, Club.LaunchAngle - Input.Spin.Y * 3.f);
	State.Velocity = FRotator(Pitch, Yaw, 0.f).Vector() * Speed;

	if (!Club.bIsPutter)
	{
		// Backspin spins about Forward x Up, which makes Magnus lift point up.
		// Spin about +Up curves the ball right (a slice for a right-handed player).
		const FVector Forward = FRotator(0.f, Yaw, 0.f).Vector();
		const float BackRpm = Club.BackspinRpm * Power * (1.f - 0.6f * Input.Spin.Y);
		const float SideRpm = (Accuracy * 0.7f + Input.Spin.X * 0.3f) * 3000.f * Power * Overdrive;
		const FVector Spin = FVector::CrossProduct(Forward, FVector::UpVector) * BackRpm + FVector::UpVector * SideRpm;
		State.SpinRate = Spin.Size() * 2.f * PI / 60.f;
		State.SpinAxis = Spin.GetSafeNormal();
	}
	return State;
}

bool GolfPhysics::IsFoliageHit(const FHitResult& Hit)
{
	return Hit.GetComponent() && Hit.GetComponent()->IsA<UInstancedStaticMeshComponent>();
}

bool GolfPhysics::SweepBall(const UWorld* World, const FVector& From, const FVector& To, FHitResult& OutHit, const AActor* Ignore, const AActor* IgnoreAlso)
{
	if (!World)
	{
		return false;
	}
	FCollisionQueryParams Params(SCENE_QUERY_STAT(GolfBallSweep), false, Ignore);
	if (IgnoreAlso)
	{
		Params.AddIgnoredActor(IgnoreAlso);
	}
	Params.bReturnPhysicalMaterial = true;
	const bool bHit = World->SweepSingleByChannel(OutHit, From, To, FQuat::Identity, ECC_GolfBall, FCollisionShape::MakeSphere(BallRadius), Params);
	return bHit && !OutHit.bStartPenetrating;
}

bool GolfPhysics::PredictCarry(const UWorld* World, FGolfBallState State, const AActor* Ignore, TArray<FVector>& OutPath, FVector& OutLanding)
{
	OutPath.Reset();
	OutPath.Add(State.Location);
	const float FallLimit = State.Location.Z - KillDepth;

	const int32 MaxSteps = FMath::CeilToInt(12.f / FixedStep);
	for (int32 Step = 0; Step < MaxSteps; ++Step)
	{
		const FVector Previous = State.Location;
		StepFlight(State, FVector::ZeroVector, FixedStep);

		FHitResult Hit;
		if (SweepBall(World, Previous, State.Location, Hit, Ignore))
		{
			OutLanding = Hit.Location;
			OutPath.Add(OutLanding);
			return true;
		}
		if (Step % 6 == 0)
		{
			OutPath.Add(State.Location);
		}
		if (State.Location.Z < FallLimit)
		{
			break;
		}
	}
	OutLanding = State.Location;
	return false;
}

float GolfPhysics::FlatCarry(const FGolfClub& Club, EGolfLie Lie)
{
	if (Club.bIsPutter)
	{
		return PuttDistance(Club.LaunchSpeed);
	}
	FGolfShotInput Input;
	Input.Power = 1.f;
	FGolfBallState State = MakeLaunch(Club, Input, Lie, FVector::ZeroVector);
	for (int32 Step = 0; Step < 12.f / FixedStep; ++Step)
	{
		StepFlight(State, FVector::ZeroVector, FixedStep);
		if (State.Location.Z < 0.f)
		{
			break;
		}
	}
	return FVector2D(State.Location.X, State.Location.Y).Size();
}

float GolfPhysics::PuttDistance(float Speed)
{
	return Speed * Speed / (2.f * GetSurface(EGolfLie::Green).RollDecel);
}
