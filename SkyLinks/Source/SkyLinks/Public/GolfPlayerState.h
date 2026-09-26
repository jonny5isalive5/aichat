#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerState.h"
#include "GolfPlayerState.generated.h"

class AGolfBall;

UCLASS()
class SKYLINKS_API AGolfPlayerState : public APlayerState
{
	GENERATED_BODY()

public:
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	int32 GetTotalStrokes() const;
	/** Score against par over the holes finished so far. */
	int32 GetToPar(const TArray<int32>& Pars) const;

	/** Strokes per hole; 0 means not finished yet. */
	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Golf")
	TArray<int32> HoleScores;

	/** Strokes on the current hole, penalties included. */
	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Golf")
	int32 Strokes = 0;

	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Golf")
	bool bHoledOut = false;

	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Golf")
	bool bInRound = false;

	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Golf")
	TObjectPtr<AGolfBall> Ball;

	// Server-only bookkeeping.
	bool bTeedOff = false;
	FVector LastShotLocation = FVector::ZeroVector;
	bool bLastShotFromTee = true;
};
