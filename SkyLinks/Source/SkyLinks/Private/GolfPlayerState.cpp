#include "GolfPlayerState.h"
#include "GolfBall.h"
#include "Net/UnrealNetwork.h"

void AGolfPlayerState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AGolfPlayerState, HoleScores);
	DOREPLIFETIME(AGolfPlayerState, Strokes);
	DOREPLIFETIME(AGolfPlayerState, bHoledOut);
	DOREPLIFETIME(AGolfPlayerState, bInRound);
	DOREPLIFETIME(AGolfPlayerState, Ball);
}

int32 AGolfPlayerState::GetTotalStrokes() const
{
	int32 Total = 0;
	for (const int32 HoleScore : HoleScores)
	{
		Total += HoleScore;
	}
	return Total;
}

int32 AGolfPlayerState::GetToPar(const TArray<int32>& Pars) const
{
	int32 Diff = 0;
	for (int32 Index = 0; Index < HoleScores.Num() && Index < Pars.Num(); ++Index)
	{
		if (HoleScores[Index] > 0)
		{
			Diff += HoleScores[Index] - Pars[Index];
		}
	}
	return Diff;
}
