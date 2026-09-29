#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SkyLinksLeaderboard.generated.h"

class UTextRenderComponent;

/**
 * The big leaderboard beside the 18th green: the live standings of everyone in the round (position, name, score
 * to par, holes completed), best first, refreshed every second. Placed on the stadium's screen by
 * Scripts/apply_floating_islands.py; it faces its +X axis.
 */
UCLASS()
class SKYLINKS_API ASkyLinksLeaderboard : public AActor
{
	GENERATED_BODY()

public:
	ASkyLinksLeaderboard();
	virtual void Tick(float DeltaSeconds) override;

	static constexpr int32 Rows = 8;

private:
	void Refresh();

	UPROPERTY(VisibleAnywhere, Category = "Leaderboard")
	TObjectPtr<UTextRenderComponent> Title;

	UPROPERTY(VisibleAnywhere, Category = "Leaderboard")
	TArray<TObjectPtr<UTextRenderComponent>> Names;

	UPROPERTY(VisibleAnywhere, Category = "Leaderboard")
	TArray<TObjectPtr<UTextRenderComponent>> Scores;

	float SinceRefresh = 10.f;
};
