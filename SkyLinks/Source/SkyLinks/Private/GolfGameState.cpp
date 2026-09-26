#include "GolfGameState.h"
#include "GolfHole.h"
#include "Engine/World.h"
#include "Net/UnrealNetwork.h"

void AGolfGameState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AGolfGameState, Phase);
	DOREPLIFETIME(AGolfGameState, HoleIndex);
	DOREPLIFETIME(AGolfGameState, CurrentHole);
	DOREPLIFETIME(AGolfGameState, ActivePlayer);
	DOREPLIFETIME(AGolfGameState, Wind);
	DOREPLIFETIME(AGolfGameState, Pars);
	DOREPLIFETIME(AGolfGameState, HoleNames);
	DOREPLIFETIME(AGolfGameState, RoomCode);
}

void AGolfGameState::MulticastAnnounce_Implementation(const FString& Text)
{
	Announcement = Text;
	AnnouncementTime = GetWorld()->GetTimeSeconds();
}
