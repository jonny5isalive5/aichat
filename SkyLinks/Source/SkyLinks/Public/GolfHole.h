#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GolfHole.generated.h"

class UStaticMeshComponent;

/**
 * One hole of the course. Place 18 of these in the level (the blockout script does it for you).
 * The actor's origin is the tee; move CupRoot onto the green.
 */
UCLASS()
class SKYLINKS_API AGolfHole : public AActor
{
	GENERATED_BODY()

public:
	AGolfHole();

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void BeginPlay() override;

	FVector GetTeeLocation() const;
	FVector GetCupLocation() const;

	/** Default aim: toward AimPoint from the tee, toward the cup from anywhere else. */
	float GetDefaultAimYaw(const FVector& From) const;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Golf")
	TObjectPtr<USceneComponent> TeeRoot;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Golf")
	TObjectPtr<USceneComponent> CupRoot;

	UPROPERTY(VisibleAnywhere, Category = "Golf")
	TObjectPtr<UStaticMeshComponent> CupMesh;

	UPROPERTY(VisibleAnywhere, Category = "Golf")
	TObjectPtr<UStaticMeshComponent> FlagPole;

	UPROPERTY(VisibleAnywhere, Category = "Golf")
	TObjectPtr<UStaticMeshComponent> Flag;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Golf")
	int32 HoleNumber = 1;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Golf")
	int32 Par = 4;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Golf")
	FString HoleName = TEXT("Unnamed");

	/** Capture radius of the cup in cm. Regulation is 5.4; a little larger feels better on a phone. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Golf")
	float CupRadius = 8.f;

	/** Strongest wind this hole can roll, cm/s. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Golf")
	float MaxWind = 800.f;

	/** Where the tee shot aims by default (dogleg corner), relative to the tee. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Golf", meta = (MakeEditWidget = true))
	FVector AimPoint = FVector(20000.f, 0.f, 0.f);

private:
	void ApplyColors();
};
