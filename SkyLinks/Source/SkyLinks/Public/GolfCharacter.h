#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "GolfCharacter.generated.h"

class USpringArmComponent;
class UCameraComponent;
class UAnimMontage;

/**
 * The golfer. Stands addressing the ball; the camera sits low behind the ball looking down the
 * aim line, with the golfer on the left of frame. Its position is derived on every machine from
 * the replicated ball location and aim, so no movement replication is needed.
 */
UCLASS()
class SKYLINKS_API AGolfCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	AGolfCharacter();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Server: walk up to a ball and face this direction. */
	void SetAddress(const FVector& InBallLocation, float InAimYaw);

	/** Owning client: turn to aim now, and tell the server so spectators see it. */
	void SetLocalAim(float InAimYaw);

	float GetAimYaw() const { return AimYaw; }
	FVector GetAddressBallLocation() const { return BallLocation; }

	UFUNCTION(NetMulticast, Unreliable)
	void MulticastPlaySwing();

	UPROPERTY(VisibleAnywhere, Category = "Golf")
	TObjectPtr<USpringArmComponent> CameraArm;

	UPROPERTY(VisibleAnywhere, Category = "Golf")
	TObjectPtr<UCameraComponent> Camera;

	/** Shown until you assign a skeletal mesh to the character Blueprint. */
	UPROPERTY(VisibleAnywhere, Category = "Golf")
	TObjectPtr<UStaticMeshComponent> PlaceholderBody;

	UPROPERTY(EditDefaultsOnly, Category = "Golf")
	TObjectPtr<UAnimMontage> SwingMontage;

	/** Distance from the ball to the golfer's feet. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf")
	float StanceDistance = 70.f;

protected:
	virtual void BeginPlay() override;
	virtual void Restart() override;

	UFUNCTION(Server, Unreliable)
	void ServerSetAim(float InAimYaw);

	UFUNCTION()
	void OnRep_Address();

	void ApplyAddress();

	UPROPERTY(ReplicatedUsing = OnRep_Address)
	FVector BallLocation = FVector::ZeroVector;

	UPROPERTY(ReplicatedUsing = OnRep_Address)
	float AimYaw = 0.f;
};
