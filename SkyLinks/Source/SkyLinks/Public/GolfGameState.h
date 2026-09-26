#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameStateBase.h"
#include "GolfTypes.h"
#include "GolfGameState.generated.h"

class AGolfHole;

UCLASS()
class SKYLINKS_API AGolfGameState : public AGameStateBase
{
	GENERATED_BODY()

public:
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	UFUNCTION(NetMulticast, Reliable)
	void MulticastAnnounce(const FString& Text);

	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Golf")
	EGolfMatchPhase Phase = EGolfMatchPhase::Lobby;

	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Golf")
	int32 HoleIndex = 0;

	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Golf")
	TObjectPtr<AGolfHole> CurrentHole;

	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Golf")
	TObjectPtr<APlayerState> ActivePlayer;

	/** The active player is driving their buggy to the ball rather than addressing it. */
	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Golf")
	bool bActiveDriving = false;

	/** cm/s. */
	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Golf")
	FVector Wind = FVector::ZeroVector;

	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Golf")
	TArray<int32> Pars;

	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Golf")
	TArray<FString> HoleNames;

	/** Code friends type to join this game. Empty in solo play. */
	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Golf")
	FString RoomCode;

	// Local only: the latest announcement and when it arrived (world seconds).
	FString Announcement;
	float AnnouncementTime = -100.f;
};
