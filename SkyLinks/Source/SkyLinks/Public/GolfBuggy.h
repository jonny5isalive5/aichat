#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "GolfBuggy.generated.h"

class UBoxComponent;
class UStaticMeshComponent;
class UStaticMesh;
class USpringArmComponent;
class UCameraComponent;
class ACameraActor;

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

	/** After a portal: the view holds at the spot the portal's picture was taken from while you drive off, for
	 *  up to this long (s) or until the buggy is PortalCameraReach (cm) away, then blends back behind it. */
	UPROPERTY(EditAnywhere, Category = "Buggy|Portal")
	float PortalCameraHold = 2.f;

	UPROPERTY(EditAnywhere, Category = "Buggy|Portal")
	float PortalCameraReach = 1500.f;

	/** Seconds to blend from the arrival view back to the chase camera (0 = cut). */
	UPROPERTY(EditAnywhere, Category = "Buggy|Portal")
	float PortalCameraBlend = 0.4f;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void OnConstruction(const FTransform& Transform) override;

	UFUNCTION(Server, Unreliable)
	void ServerSyncMove(FVector_NetQuantize10 Location, FRotator Rotation, float InSpeed, float InSteer);

	UFUNCTION(NetMulticast, Reliable)
	void MulticastTeleport(FVector Location, FRotator Rotation);

	/** Driver went through a portal: the server checks it came out of one and tells everyone else. */
	UFUNCTION(Server, Reliable)
	void ServerPortalHop(FVector_NetQuantize10 Location, FRotator Rotation, float InSpeed);

	/** Everyone but the driver: snap to the far side of the portal (no gliding across the sky). */
	UFUNCTION(NetMulticast, Reliable)
	void MulticastPortalHop(FVector Location, FRotator Rotation, float InSpeed);

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
	/** If the move from Start just went through a portal, come out of its partner. True if it did. */
	bool TryPortal(const FVector& Start);
	/** Frames to hold the chase camera still after a portal hop, so it cuts instead of flying across. */
	int32 CameraCutFrames = 0;
	/** Driver only: look from the portal's arrival spot, then hand back to the chase camera. */
	void StartArrivalView(const ASkyLinksPortal* Portal, int32 Direction);
	void UpdateArrivalView(float DeltaSeconds);
	void EndArrivalView(float Blend);

	/** The fixed camera used on arrival through a portal (local, never replicated). */
	UPROPERTY(Transient)
	TObjectPtr<ACameraActor> ArrivalCamera;
	float ArrivalTime = -1.f;

	float Throttle = 0.f;
	float SteerInput = 0.f;
	float Speed = 0.f;
	float SteerAngle = 0.f;
	float WheelSpin = 0.f;
	float SyncTimer = 0.f;
	FVector LastLocation = FVector::ZeroVector;
	bool bUsingFallbackWheels = false;


};
