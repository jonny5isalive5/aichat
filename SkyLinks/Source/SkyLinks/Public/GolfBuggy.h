#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "GolfBuggy.generated.h"

class UBoxComponent;
class UStaticMeshComponent;
class UStaticMesh;
class USpringArmComponent;
class UCameraComponent;

USTRUCT()
struct FBuggyNetState
{
	GENERATED_BODY()

	UPROPERTY()
	FVector_NetQuantize10 Location = FVector::ZeroVector;

	UPROPERTY()
	FRotator Rotation = FRotator::ZeroRotator;

	UPROPERTY()
	float Speed = 0.f;

	UPROPERTY()
	float Steer = 0.f;
};

/**
 * Drivable golf buggy. Arcade handling tuned to a real electric cart (about 24 km/h top speed):
 * bicycle-model steering, follows the ground through four wheel traces, stops at trees, buildings
 * and water. The driving player simulates it locally and streams its position to the server,
 * which relays it to everyone else, so it feels instant on a phone.
 *
 * Meshes come from the Blender exports (Art/Exports) imported to /Game/Vehicles/Buggy.
 * Until then it draws as simple boxes and cylinders.
 */
UCLASS()
class SKYLINKS_API AGolfBuggy : public APawn
{
	GENERATED_BODY()

public:
	AGolfBuggy();

	virtual void Tick(float DeltaSeconds) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Driver's input, -1..1 each. Only used on the machine that is driving. */
	void SetDriveInput(float InThrottle, float InSteer);

	/** Server: put the buggy on the ground at this spot, stopped. */
	void ParkAt(const FVector& Location, float Yaw);

	float GetSpeed() const { return Speed; }

	/** How close to the ball the buggy must be before the player can get out and play. */
	static constexpr float ArriveDistance = 1500.f;

	/** How close (cm, golfer to buggy centre) you must stand to get in with E. */
	static constexpr float EnterReach = 450.f;

	/** Height of the collision box centre (the actor origin) above the ground. */
	static constexpr float RideHeight = 85.f;

	UPROPERTY(VisibleAnywhere, Category = "Buggy")
	TObjectPtr<UBoxComponent> Collision;

	UPROPERTY(VisibleAnywhere, Category = "Buggy")
	TObjectPtr<UStaticMeshComponent> Body;

	UPROPERTY(VisibleAnywhere, Category = "Buggy")
	TObjectPtr<UStaticMeshComponent> WheelFL;

	UPROPERTY(VisibleAnywhere, Category = "Buggy")
	TObjectPtr<UStaticMeshComponent> WheelFR;

	UPROPERTY(VisibleAnywhere, Category = "Buggy")
	TObjectPtr<UStaticMeshComponent> WheelRL;

	UPROPERTY(VisibleAnywhere, Category = "Buggy")
	TObjectPtr<UStaticMeshComponent> WheelRR;

	UPROPERTY(VisibleAnywhere, Category = "Buggy")
	TObjectPtr<USpringArmComponent> CameraArm;

	UPROPERTY(VisibleAnywhere, Category = "Buggy")
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY(EditAnywhere, Category = "Buggy|Meshes")
	TSoftObjectPtr<UStaticMesh> BodyMeshAsset;

	UPROPERTY(EditAnywhere, Category = "Buggy|Meshes")
	TSoftObjectPtr<UStaticMesh> WheelMeshAsset;

	/** Turn the imported body if it faces the wrong way after import. */
	UPROPERTY(EditAnywhere, Category = "Buggy|Meshes")
	float BodyYawOffset = 0.f;

	/** cm/s. 2680 is about 96 km/h: four times a real cart, so trips between shots stay short. */
	UPROPERTY(EditAnywhere, Category = "Buggy|Handling")
	float MaxSpeed = 2680.f;

	UPROPERTY(EditAnywhere, Category = "Buggy|Handling")
	float MaxReverseSpeed = 1120.f;

	UPROPERTY(EditAnywhere, Category = "Buggy|Handling")
	float Acceleration = 1280.f;

	UPROPERTY(EditAnywhere, Category = "Buggy|Handling")
	float BrakeDeceleration = 3600.f;

	UPROPERTY(EditAnywhere, Category = "Buggy|Handling")
	float CoastDeceleration = 720.f;

	UPROPERTY(EditAnywhere, Category = "Buggy|Handling")
	float MaxSteerAngle = 32.f;

	UPROPERTY(EditAnywhere, Category = "Buggy|Dimensions")
	float WheelBase = 165.f;

	UPROPERTY(EditAnywhere, Category = "Buggy|Dimensions")
	float Track = 92.f;

	UPROPERTY(EditAnywhere, Category = "Buggy|Dimensions")
	float WheelRadius = 23.f;

protected:
	virtual void BeginPlay() override;
	virtual void OnConstruction(const FTransform& Transform) override;

	UFUNCTION(Server, Unreliable)
	void ServerSyncMove(FVector_NetQuantize10 Location, FRotator Rotation, float InSpeed, float InSteer);

	UFUNCTION(NetMulticast, Reliable)
	void MulticastTeleport(FVector Location, FRotator Rotation);

	UPROPERTY(Replicated)
	FBuggyNetState NetState;

private:
	void LoadMeshes();
	void Drive(float DeltaSeconds);
	void FollowProxy(float DeltaSeconds);
	void AnimateWheels(float DeltaSeconds);
	/** Ground height and slope under the four wheels at this position and yaw. */
	bool SampleGround(const FVector& Center, float Yaw, FVector& OutLocation, FRotator& OutRotation, bool& bOutWater) const;
	void PublishState();

	float Throttle = 0.f;
	float SteerInput = 0.f;
	float Speed = 0.f;
	float SteerAngle = 0.f;
	float WheelSpin = 0.f;
	float SyncTimer = 0.f;
	FVector LastLocation = FVector::ZeroVector;
	bool bUsingFallbackWheels = false;


};
