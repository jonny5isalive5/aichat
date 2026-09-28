#include "GolfGameMode.h"
#include "SkyLinks.h"
#include "GolfBall.h"
#include "GolfBuggy.h"
#include "GolfCharacter.h"
#include "GolfGameState.h"
#include "GolfHole.h"
#include "GolfHUD.h"
#include "GolfPhysics.h"
#include "GolfPlayerController.h"
#include "GolfPlayerState.h"
#include "GolfSessionSubsystem.h"
#include "Engine/GameInstance.h"
#include "EngineUtils.h"
#include "TimerManager.h"

namespace
{
	FString ScoreName(int32 Strokes, int32 Par)
	{
		if (Strokes == 1)
		{
			return TEXT("HOLE IN ONE!");
		}
		switch (Strokes - Par)
		{
		case -3: return TEXT("ALBATROSS!");
		case -2: return TEXT("EAGLE!");
		case -1: return TEXT("BIRDIE!");
		case 0:  return TEXT("PAR");
		case 1:  return TEXT("BOGEY");
		case 2:  return TEXT("DOUBLE BOGEY");
		default: return FString::Printf(TEXT("+%d"), Strokes - Par);
		}
	}
}

const FName AGolfGameMode::BuggyBayTag(TEXT("BuggyBay"));

AGolfGameMode::AGolfGameMode()
{
	DefaultPawnClass = AGolfCharacter::StaticClass();
	PlayerControllerClass = AGolfPlayerController::StaticClass();
	PlayerStateClass = AGolfPlayerState::StaticClass();
	GameStateClass = AGolfGameState::StaticClass();
	HUDClass = AGolfHUD::StaticClass();
	BallClass = AGolfBall::StaticClass();
	BuggyClass = AGolfBuggy::StaticClass();
}

AGolfGameState* AGolfGameMode::GetGolfState() const
{
	return GetGameState<AGolfGameState>();
}

void AGolfGameMode::BeginPlay()
{
	Super::BeginPlay();

	for (TActorIterator<AGolfHole> It(GetWorld()); It; ++It)
	{
		Holes.Add(*It);
	}
	Holes.Sort([](const AGolfHole& A, const AGolfHole& B) { return A.HoleNumber < B.HoleNumber; });

	AGolfGameState* State = GetGolfState();
	for (const AGolfHole* Hole : Holes)
	{
		State->Pars.Add(Hole->Par);
		State->HoleNames.Add(Hole->HoleName);
	}

	if (GetNetMode() == NM_ListenServer)
	{
		if (const UGolfSessionSubsystem* Sessions = GetGameInstance()->GetSubsystem<UGolfSessionSubsystem>())
		{
			State->RoomCode = Sessions->GetRoomCode();
		}
	}

	if (Holes.Num() == 0)
	{
		UE_LOG(LogSkyLinks, Error, TEXT("No GolfHole actors in this level. Run Scripts/build_blockout_course.py or place them by hand."));
	}
	SpawnCarPark();
}

void AGolfGameMode::SpawnCarPark()
{
	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (!It->ActorHasTag(BuggyBayTag))
		{
			continue;
		}
		AGolfBuggy* Buggy = GetWorld()->SpawnActor<AGolfBuggy>(BuggyClass, FTransform(FVector(0.f, 0.f, -100000.f)), Params);
		if (Buggy)
		{
			Buggy->ParkAt(It->GetActorLocation(), It->GetActorRotation().Yaw);
			CarPark.Add(Buggy);
		}
	}
	UE_LOG(LogSkyLinks, Log, TEXT("Car park: %d buggies"), CarPark.Num());
}

void AGolfGameMode::PostLogin(APlayerController* NewPlayer)
{
	Super::PostLogin(NewPlayer);

	AGolfPlayerState* Player = NewPlayer->GetPlayerState<AGolfPlayerState>();
	if (!Player)
	{
		return;
	}

	FActorSpawnParameters Params;
	Params.Owner = NewPlayer;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	Player->Ball = GetWorld()->SpawnActor<AGolfBall>(BallClass, FTransform(FVector(0.f, 0.f, -100000.f)), Params);
	Player->Ball->SetActorHiddenInGame(true);
	Player->Ball->OnStopped.AddUObject(this, &AGolfGameMode::OnBallStopped);
	Player->HoleScores.Init(0, Holes.Num());
	Player->Golfer = NewPlayer->GetPawn<AGolfCharacter>();

	// With a car park, players pick their own buggy (E); without one, everyone gets a buggy by the first tee.
	Player->Buggy = CarPark.Num() > 0 ? nullptr : GetWorld()->SpawnActor<AGolfBuggy>(BuggyClass, FTransform(FVector(0.f, 0.f, -100000.f)), Params);
	if (Player->Buggy && Holes.Num() > 0)
	{
		// Park in the row beside the first tee.
		const AGolfHole* First = Holes[0];
		const float Yaw = First->GetDefaultAimYaw(First->GetTeeLocation());
		const FRotator Heading(0.f, Yaw, 0.f);
		const int32 Slot = GameState->PlayerArray.Num() - 1;
		Player->Buggy->ParkAt(First->GetTeeLocation() - Heading.Vector() * 1200.f
			+ FRotationMatrix(Heading).GetUnitAxis(EAxis::Y) * (Slot * 350.f - 525.f), Yaw);
	}

	AGolfGameState* State = GetGolfState();
	if (State->Phase == EGolfMatchPhase::Lobby || State->Phase == EGolfMatchPhase::RoundOver)
	{
		// Walk around the clubhouse (spawned at the PlayerStart) until the host tees off.
		if (AGolfCharacter* Golfer = GetGolfer(Player))
		{
			Golfer->SetRoaming(true);
		}
		State->MulticastAnnounce(FString::Printf(TEXT("%s joined"), *Player->GetPlayerName()));
	}
	else if (AGolfPlayerState* Active = Cast<AGolfPlayerState>(State->ActivePlayer))
	{
		// Joined mid-round: watch until the next round starts.
		if (APawn* OwnPawn = NewPlayer->GetPawn())
		{
			OwnPawn->SetActorHiddenInGame(true);
		}
		if (AGolfCharacter* Golfer = GetGolfer(Active))
		{
			NewPlayer->SetViewTargetWithBlend(Golfer, 0.f);
		}
	}
}

void AGolfGameMode::Logout(AController* Exiting)
{
	if (AGolfPlayerState* Player = Exiting->GetPlayerState<AGolfPlayerState>())
	{
		if (Player->Ball)
		{
			Player->Ball->Destroy();
			Player->Ball = nullptr;
		}
		// Whichever pawn is not possessed would be left behind.
		for (APawn* Owned : { static_cast<APawn*>(Player->Buggy.Get()), static_cast<APawn*>(Player->Golfer.Get()) })
		{
			const bool bCarParkBuggy = Owned && CarPark.Contains(Cast<AGolfBuggy>(Owned));
			if (Owned && Owned != Exiting->GetPawn() && !bCarParkBuggy)
			{
				Owned->Destroy();
			}
		}
		Player->Buggy = nullptr;
		Player->Golfer = nullptr;
		Player->bInRound = false;
		TeeOrder.Remove(Player);
		InTransition.Remove(Player);

		AGolfGameState* State = GetGolfState();
		if (State->ActivePlayer == Player && State->Phase == EGolfMatchPhase::PlayingHole)
		{
			bShotInFlight = false;
			State->bActiveDriving = false;
			State->ActivePlayer = nullptr;
			GetWorldTimerManager().SetTimer(FlowTimer, this, &AGolfGameMode::NextTurn, TurnDelay, false);
		}
	}
	Super::Logout(Exiting);
}

TArray<AGolfPlayerState*> AGolfGameMode::GetRoundPlayers() const
{
	TArray<AGolfPlayerState*> Result;
	for (APlayerState* Base : GameState->PlayerArray)
	{
		AGolfPlayerState* Player = Cast<AGolfPlayerState>(Base);
		if (Player && Player->bInRound && Player->Ball)
		{
			Result.Add(Player);
		}
	}
	return Result;
}

AGolfCharacter* AGolfGameMode::GetGolfer(AGolfPlayerState* Player) const
{
	return Player ? Player->Golfer.Get() : nullptr;
}

void AGolfGameMode::PossessGolfer(AGolfPlayerState* Player)
{
	APlayerController* Controller = Player ? Player->GetPlayerController() : nullptr;
	AGolfCharacter* Golfer = GetGolfer(Player);
	if (Controller && Golfer && Controller->GetPawn() != Golfer)
	{
		Controller->Possess(Golfer);
	}
}

AGolfPlayerState* AGolfGameMode::FindBallOwner(const AGolfBall* Ball) const
{
	for (APlayerState* Base : GameState->PlayerArray)
	{
		AGolfPlayerState* Player = Cast<AGolfPlayerState>(Base);
		if (Player && Player->Ball == Ball)
		{
			return Player;
		}
	}
	return nullptr;
}

void AGolfGameMode::ViewAll(AActor* Target, float BlendTime)
{
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		if (APlayerController* Controller = It->Get())
		{
			Controller->SetViewTargetWithBlend(Target, BlendTime, VTBlend_EaseInOut, 2.f);
		}
	}
}

void AGolfGameMode::RequestStartRound(APlayerController* Requester)
{
	AGolfGameState* State = GetGolfState();
	const bool bCanStart = State->Phase == EGolfMatchPhase::Lobby || State->Phase == EGolfMatchPhase::RoundOver;
	// Only the host (the listen server's own player, or the solo player) starts the round.
	if (!bCanStart || !Requester || !Requester->IsLocalController() || Holes.Num() == 0)
	{
		return;
	}

	TeeOrder.Reset();
	for (APlayerState* Base : GameState->PlayerArray)
	{
		if (AGolfPlayerState* Player = Cast<AGolfPlayerState>(Base); Player && Player->Ball)
		{
			Player->bInRound = true;
			Player->HoleScores.Init(0, Holes.Num());
			TeeOrder.Add(Player);
			if (!IsValid(Player->Buggy))
			{
				AssignBuggy(Player);
			}
		}
	}
	StartHole(0);
}

void AGolfGameMode::StartHole(int32 Index)
{
	AGolfGameState* State = GetGolfState();
	AGolfHole* Hole = Holes[Index];

	State->Phase = EGolfMatchPhase::PlayingHole;
	State->HoleIndex = Index;
	State->CurrentHole = Hole;
	State->ActivePlayer = nullptr;
	State->Wind = FRotator(0.f, FMath::FRandRange(0.f, 360.f), 0.f).Vector() * FMath::FRandRange(0.f, Hole->MaxWind);
	bShotInFlight = false;

	State->bActiveDriving = false;
	InTransition.Reset();
	const float TeeYaw = Hole->GetDefaultAimYaw(Hole->GetTeeLocation());
	const FRotator TeeHeading(0.f, TeeYaw, 0.f);
	const FVector TeeRight = FRotationMatrix(TeeHeading).GetUnitAxis(EAxis::Y);
	int32 Slot = 0;
	for (AGolfPlayerState* Player : GetRoundPlayers())
	{
		Player->Strokes = 0;
		Player->bHoledOut = false;
		Player->bTeedOff = false;
		Player->Ball->SetActorHiddenInGame(true);
		PossessGolfer(Player);
		// Everyone off their feet / out of their buggy and onto the tee (only the first player is shown).
		if (AGolfCharacter* Golfer = GetGolfer(Player))
		{
			const FVector Tee = Hole->GetTeeLocation() + FVector(0.f, 0.f, GolfPhysics::BallRadius);
			Golfer->SetAddress(Tee, Hole->GetDefaultAimYaw(Tee));
			Golfer->SetActorHiddenInGame(true);
			Golfer->SetActorEnableCollision(false);
		}
		if (Player->Buggy)
		{
			Player->Buggy->ParkAt(Hole->GetTeeLocation() - TeeHeading.Vector() * 1200.f + TeeRight * (Slot * 350.f - 525.f), TeeYaw);
		}
		++Slot;
	}

	// Honors: lowest score on the previous hole tees off first. Stable sort keeps ties in order.
	TeeOrder.RemoveAll([](const TWeakObjectPtr<AGolfPlayerState>& Player) { return !Player.IsValid(); });
	if (Index > 0)
	{
		TeeOrder.StableSort([Index](const TWeakObjectPtr<AGolfPlayerState>& A, const TWeakObjectPtr<AGolfPlayerState>& B)
		{
			return A->HoleScores[Index - 1] < B->HoleScores[Index - 1];
		});
	}

	State->MulticastAnnounce(FString::Printf(TEXT("HOLE %d  ·  %s  ·  PAR %d"), Index + 1, *Hole->HoleName, Hole->Par));

	// Fly-in view of the tee before the first player steps up.
	if (TeeOrder.Num() > 0)
	{
		if (AGolfCharacter* Golfer = GetGolfer(TeeOrder[0].Get()))
		{
			Golfer->SetActorHiddenInGame(false);
			ViewAll(Golfer, 0.8f);
		}
	}
	GetWorldTimerManager().SetTimer(FlowTimer, this, &AGolfGameMode::NextTurn, 2.5f, false);
}

void AGolfGameMode::NextTurn()
{
	AGolfGameState* State = GetGolfState();
	if (State->Phase != EGolfMatchPhase::PlayingHole)
	{
		return;
	}

	TArray<AGolfPlayerState*> Waiting = GetRoundPlayers().FilterByPredicate([](const AGolfPlayerState* Player) { return !Player->bHoledOut; });
	if (Waiting.Num() == 0)
	{
		EndHole();
		return;
	}

	AGolfPlayerState* Next = nullptr;
	for (const TWeakObjectPtr<AGolfPlayerState>& Player : TeeOrder)
	{
		if (Player.IsValid() && Waiting.Contains(Player.Get()) && !Player->bTeedOff)
		{
			Next = Player.Get();
			break;
		}
	}
	if (!Next)
	{
		// Everyone is off the tee: farthest from the cup plays.
		const FVector Cup = State->CurrentHole->GetCupLocation();
		float Farthest = -1.f;
		for (AGolfPlayerState* Player : Waiting)
		{
			const float Distance = FVector::Dist(Player->Ball->GetRestLocation(), Cup);
			if (Distance > Farthest)
			{
				Farthest = Distance;
				Next = Player;
			}
		}
	}
	BeginTurn(Next);
}

void AGolfGameMode::BeginTurn(AGolfPlayerState* Player)
{
	AGolfGameState* State = GetGolfState();
	AGolfHole* Hole = State->CurrentHole;
	AGolfBall* Ball = Player->Ball;

	if (!Player->bTeedOff)
	{
		Ball->PlaceAt(Hole->GetTeeLocation() + FVector(0.f, 0.f, GolfPhysics::BallRadius + 0.1f), true);
	}
	Ball->SetActorHiddenInGame(false);
	State->ActivePlayer = Player;

	// Off the tee, walk (or drive) to the ball unless the golfer is already standing at it.
	const AGolfCharacter* Golfer = GetGolfer(Player);
	const bool bAway = Golfer && FVector::Dist2D(Golfer->GetActorLocation(), Ball->GetRestLocation()) > WalkUpDistance;
	if (Player->bTeedOff && bAway && Player->GetPlayerController())
	{
		StartTravel(Player);
	}
	else
	{
		AddressBall(Player);
	}
}

bool AGolfGameMode::CanRoam(const AGolfPlayerState* Player) const
{
	const AGolfGameState* State = GetGolfState();
	if (!Player || !State || !Player->Golfer)
	{
		return false;
	}
	switch (State->Phase)
	{
	case EGolfMatchPhase::Lobby:
	case EGolfMatchPhase::RoundOver:
		return true;
	case EGolfMatchPhase::PlayingHole:
		return State->ActivePlayer == Player && State->bActiveDriving;
	default:
		return false;
	}
}

void AGolfGameMode::ViewFor(AGolfPlayerState* Player, AActor* Target, float BlendTime)
{
	if (GetGolfState()->Phase == EGolfMatchPhase::PlayingHole)
	{
		ViewAll(Target, BlendTime); // Everyone follows the player whose turn it is.
	}
	else if (APlayerController* Controller = Player ? Player->GetPlayerController() : nullptr)
	{
		Controller->SetViewTargetWithBlend(Target, BlendTime, VTBlend_EaseInOut, 2.f);
	}
}

void AGolfGameMode::ShowOnly(AGolfPlayerState* Player)
{
	// Hidden golfers also stop colliding, so they can't block the one walking about (or a buggy).
	for (APlayerState* Base : GameState->PlayerArray)
	{
		if (AGolfCharacter* Golfer = GetGolfer(Cast<AGolfPlayerState>(Base)))
		{
			Golfer->SetActorHiddenInGame(Base != Player);
			Golfer->SetActorEnableCollision(Base == Player);
		}
	}
}

bool AGolfGameMode::IsBuggyFree(const AGolfBuggy* Buggy) const
{
	for (APlayerState* Base : GameState->PlayerArray)
	{
		const AGolfPlayerState* Player = Cast<AGolfPlayerState>(Base);
		if (Player && Player->Buggy == Buggy)
		{
			return false;
		}
	}
	return IsValid(Buggy);
}

AGolfBuggy* AGolfGameMode::FindBuggyToEnter(AGolfPlayerState* Player) const
{
	const AGolfCharacter* Golfer = GetGolfer(Player);
	if (!Golfer)
	{
		return nullptr;
	}
	TArray<AGolfBuggy*> Candidates;
	if (IsValid(Player->Buggy))
	{
		Candidates.Add(Player->Buggy);
	}
	// Before and after a round any free buggy in the car park is up for grabs.
	if (GetGolfState()->Phase != EGolfMatchPhase::PlayingHole)
	{
		for (AGolfBuggy* Buggy : CarPark)
		{
			if (IsBuggyFree(Buggy))
			{
				Candidates.Add(Buggy);
			}
		}
	}
	AGolfBuggy* Best = nullptr;
	float BestDistance = AGolfBuggy::EnterReach;
	for (AGolfBuggy* Buggy : Candidates)
	{
		const float Distance = FVector::Dist2D(Buggy->GetActorLocation(), Golfer->GetActorLocation());
		if (Distance <= BestDistance)
		{
			Best = Buggy;
			BestDistance = Distance;
		}
	}
	return Best;
}

void AGolfGameMode::AssignBuggy(AGolfPlayerState* Player)
{
	const AGolfCharacter* Golfer = GetGolfer(Player);
	const FVector From = Golfer ? Golfer->GetActorLocation() : FVector::ZeroVector;
	AGolfBuggy* Best = nullptr;
	for (AGolfBuggy* Buggy : CarPark)
	{
		if (IsBuggyFree(Buggy) && (!Best || FVector::DistSquared(Buggy->GetActorLocation(), From) < FVector::DistSquared(Best->GetActorLocation(), From)))
		{
			Best = Buggy;
		}
	}
	if (!Best)
	{
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Best = GetWorld()->SpawnActor<AGolfBuggy>(BuggyClass, FTransform(FVector(0.f, 0.f, -100000.f)), Params);
	}
	Player->Buggy = Best;
}

void AGolfGameMode::ToggleBuggy(APlayerController* Controller)
{
	AGolfPlayerState* Player = Controller ? Controller->GetPlayerState<AGolfPlayerState>() : nullptr;
	if (!Player || InTransition.Contains(Player) || !CanRoam(Player))
	{
		return;
	}
	if (IsValid(Player->Buggy) && Controller->GetPawn() == Player->Buggy)
	{
		ExitBuggy(Player, false);
		return;
	}
	AGolfCharacter* Golfer = GetGolfer(Player);
	if (Golfer && Golfer->IsRoaming() && Controller->GetPawn() == Golfer)
	{
		if (AGolfBuggy* Buggy = FindBuggyToEnter(Player))
		{
			EnterBuggy(Player, Buggy);
		}
	}
}

void AGolfGameMode::StartTravel(AGolfPlayerState* Player)
{
	AGolfGameState* State = GetGolfState();
	State->bActiveDriving = true;
	ShowOnly(Player);
	PossessGolfer(Player);
	if (AGolfCharacter* Golfer = GetGolfer(Player))
	{
		Golfer->SetRoaming(true);
		ViewAll(Golfer, 0.6f);
		const float Meters = FVector::Dist2D(Golfer->GetActorLocation(), Player->Ball->GetRestLocation()) / 100.f;
		State->MulticastAnnounce(FString::Printf(TEXT("%s  ·  WALK OR DRIVE TO YOUR BALL  ·  %.0f m"), *Player->GetPlayerName(), Meters));
	}
}

void AGolfGameMode::EnterBuggy(AGolfPlayerState* Player, AGolfBuggy* Buggy)
{
	APlayerController* Controller = Player->GetPlayerController();
	AGolfCharacter* Golfer = GetGolfer(Player);
	if (!Controller || !Golfer || !Buggy)
	{
		return;
	}
	Player->Buggy = Buggy; // Picked: it's this player's buggy from now on.
	Buggy->SetOwner(Controller);
	Golfer->SetRoaming(false);
	ViewFor(Player, Buggy, 0.6f);

	// Climb in (seen from behind the buggy), then hand over the controls.
	TWeakObjectPtr<AGolfPlayerState> WeakPlayer = Player;
	auto TakeWheel = [this, WeakPlayer]()
	{
		AGolfPlayerState* Driver = WeakPlayer.Get();
		InTransition.Remove(WeakPlayer);
		if (!Driver || !IsValid(Driver->Buggy) || !Driver->GetPlayerController() || !CanRoam(Driver))
		{
			return;
		}
		if (AGolfCharacter* Seated = GetGolfer(Driver))
		{
			// With the climb-in animation the golfer stays in the seat and rides along; without it, hide them.
			if (Seated->GetBuggyTransitionDuration(true) > 0.f)
			{
				Seated->MulticastSeatInBuggy(Driver->Buggy);
			}
			else
			{
				Seated->SetActorHiddenInGame(true);
			}
		}
		Driver->GetPlayerController()->Possess(Driver->Buggy);
		ViewFor(Driver, Driver->Buggy, 0.2f);
	};
	const float Duration = Golfer->GetBuggyTransitionDuration(true);
	if (Duration > 0.f)
	{
		InTransition.Add(Player);
		Golfer->SetActorHiddenInGame(false);
		Golfer->MulticastBuggyTransition(Buggy, true);
		FTimerHandle Handle;
		GetWorldTimerManager().SetTimer(Handle, FTimerDelegate::CreateWeakLambda(this, TakeWheel), Duration, false);
	}
	else
	{
		TakeWheel();
	}
}

void AGolfGameMode::ExitBuggy(AGolfPlayerState* Player, bool bThenAddress)
{
	AGolfBuggy* Buggy = Player->Buggy;
	AGolfCharacter* Golfer = GetGolfer(Player);
	if (!IsValid(Buggy) || !Golfer)
	{
		return;
	}
	// Stop where it is, hand control back to the golfer and climb out while the camera watches from behind.
	Buggy->ParkAt(Buggy->GetActorLocation(), Buggy->GetActorRotation().Yaw);
	PossessGolfer(Player);
	ViewFor(Player, Buggy, 0.3f);

	TWeakObjectPtr<AGolfPlayerState> WeakPlayer = Player;
	auto StepOut = [this, WeakPlayer, bThenAddress]()
	{
		InTransition.Remove(WeakPlayer);
		AGolfPlayerState* Returning = WeakPlayer.Get();
		AGolfCharacter* Walker = GetGolfer(Returning);
		if (!Returning || !Walker)
		{
			return;
		}
		if (bThenAddress)
		{
			GetGolfState()->bActiveDriving = false;
			AddressBall(Returning);
			return;
		}
		if (!CanRoam(Returning))
		{
			return;
		}
		Walker->MulticastStandBesideBuggy(Returning->Buggy);
		Walker->SetRoaming(true);
		ViewFor(Returning, Walker, 0.4f);
	};
	const float Duration = Golfer->GetBuggyTransitionDuration(false);
	if (Duration > 0.f)
	{
		InTransition.Add(Player);
		Golfer->SetActorHiddenInGame(false);
		Golfer->MulticastBuggyTransition(Buggy, false);
		FTimerHandle Handle;
		GetWorldTimerManager().SetTimer(Handle, FTimerDelegate::CreateWeakLambda(this, StepOut), Duration, false);
	}
	else
	{
		StepOut();
	}
}

void AGolfGameMode::FinishDriving(APlayerController* Driver, bool bSkip)
{
	AGolfGameState* State = GetGolfState();
	AGolfPlayerState* Player = Driver ? Driver->GetPlayerState<AGolfPlayerState>() : nullptr;
	if (!Player || State->Phase != EGolfMatchPhase::PlayingHole || !State->bActiveDriving || State->ActivePlayer != Player
		|| InTransition.Contains(Player) || !Driver->GetPawn())
	{
		return;
	}

	const bool bInBuggy = IsValid(Player->Buggy) && Driver->GetPawn() == Player->Buggy;
	const FVector BallLocation = Player->Ball->GetRestLocation();
	if (bSkip)
	{
		// Straight to the ball: the buggy parks a few metres back from it, off to the side of the line.
		if (IsValid(Player->Buggy))
		{
			const float Yaw = State->CurrentHole->GetDefaultAimYaw(BallLocation);
			const FRotator Heading(0.f, Yaw, 0.f);
			Player->Buggy->ParkAt(BallLocation - Heading.Vector() * 600.f - FRotationMatrix(Heading).GetUnitAxis(EAxis::Y) * 400.f, Yaw);
		}
	}
	else if (FVector::Dist2D(Driver->GetPawn()->GetActorLocation(), BallLocation) > AGolfBuggy::ArriveDistance)
	{
		return;
	}

	if (bInBuggy)
	{
		ExitBuggy(Player, true); // Climb out, then step up to the ball.
	}
	else
	{
		State->bActiveDriving = false;
		AddressBall(Player);
	}
}

void AGolfGameMode::ReleaseToRoam()
{
	for (APlayerState* Base : GameState->PlayerArray)
	{
		AGolfPlayerState* Player = Cast<AGolfPlayerState>(Base);
		AGolfCharacter* Golfer = GetGolfer(Player);
		if (!Golfer)
		{
			continue;
		}
		PossessGolfer(Player);
		Golfer->SetActorHiddenInGame(false);
		Golfer->SetActorEnableCollision(true);
		Golfer->SetRoaming(true);
		if (APlayerController* Controller = Player->GetPlayerController())
		{
			Controller->SetViewTargetWithBlend(Golfer, 0.8f);
		}
	}
}

void AGolfGameMode::AddressBall(AGolfPlayerState* Player)
{
	AGolfGameState* State = GetGolfState();
	AGolfHole* Hole = State->CurrentHole;

	// Only the golfer whose turn it is stands on the course.
	ShowOnly(Player);
	PossessGolfer(Player);

	if (AGolfCharacter* Golfer = GetGolfer(Player))
	{
		const FVector BallLocation = Player->Ball->GetRestLocation();
		Golfer->SetAddress(BallLocation, Hole->GetDefaultAimYaw(BallLocation), Player->Ball->GetLie() == EGolfLie::Green);
		ViewAll(Golfer, 0.6f);
	}

	State->MulticastAnnounce(FString::Printf(TEXT("%s  ·  SHOT %d"), *Player->GetPlayerName(), Player->Strokes + 1));
}

void AGolfGameMode::HandleShot(APlayerController* Shooter, const FGolfShotInput& Input)
{
	AGolfGameState* State = GetGolfState();
	AGolfPlayerState* Player = Shooter ? Shooter->GetPlayerState<AGolfPlayerState>() : nullptr;
	if (!Player || State->Phase != EGolfMatchPhase::PlayingHole || State->ActivePlayer != Player || bShotInFlight
		|| State->bActiveDriving || !Player->Ball || !Player->Ball->IsAtRest())
	{
		return;
	}

	const TArray<FGolfClub>& Bag = GolfPhysics::GetClubBag();
	if (!Bag.IsValidIndex(Input.ClubIndex))
	{
		return;
	}

	// Never trust the client's numbers.
	FGolfShotInput Clean = Input;
	Clean.Power = FMath::Clamp(Input.Power, 0.02f, 1.1f);
	Clean.Accuracy = FMath::Clamp(Input.Accuracy, -1.f, 1.f);
	Clean.Spin.X = FMath::Clamp(Input.Spin.X, -1.f, 1.f);
	Clean.Spin.Y = FMath::Clamp(Input.Spin.Y, -1.f, 1.f);
	Clean.AimYaw = FRotator::NormalizeAxis(Input.AimYaw);

	AGolfBall* Ball = Player->Ball;
	const FGolfClub& Club = Bag[Clean.ClubIndex];
	const EGolfLie Lie = Ball->GetLie();
	const FVector Start = Ball->GetRestLocation() + FVector(0.f, 0.f, 0.5f);

	Player->LastShotLocation = Ball->GetRestLocation();
	Player->bLastShotFromTee = Lie == EGolfLie::Tee;
	Player->bLastShotWasPutt = Club.bIsPutter;
	Player->Strokes++;
	Player->bTeedOff = true;
	bShotInFlight = true;

	// The golfer swings first; the ball leaves when the club reaches it.
	const EGolferSwing Swing = Club.bIsPutter ? EGolferSwing::Putt : Club.LaunchAngle >= 28.f ? EGolferSwing::Chip : EGolferSwing::Drive;
	float ImpactDelay = 0.f;
	if (AGolfCharacter* Golfer = GetGolfer(Player))
	{
		Golfer->SetAddress(Ball->GetRestLocation(), Clean.AimYaw, Club.bIsPutter);
		Golfer->MulticastPlaySwing(Swing);
		ImpactDelay = Golfer->GetImpactDelay(Swing);
	}

	const FGolfBallState LaunchState = GolfPhysics::MakeLaunch(Club, Clean, Lie, Start);
	const FVector Wind = Club.bIsPutter ? FVector::ZeroVector : State->Wind;
	const FVector Cup = State->CurrentHole->GetCupLocation();
	const float CupRadius = State->CurrentHole->CupRadius;
	TWeakObjectPtr<AGolfBall> WeakBall = Ball;
	auto Strike = [this, WeakBall, LaunchState, Wind, Cup, CupRadius]()
	{
		if (!WeakBall.IsValid())
		{
			return;
		}
		WeakBall->Launch(LaunchState, Wind, Cup, CupRadius);
		// Cut everyone to the chase camera behind the ball.
		GetWorldTimerManager().SetTimer(CameraTimer, FTimerDelegate::CreateWeakLambda(this, [this, WeakBall]()
		{
			if (WeakBall.IsValid())
			{
				ViewAll(WeakBall.Get(), 0.35f);
			}
		}), ChaseCameraDelay, false);
	};
	if (ImpactDelay > 0.f)
	{
		GetWorldTimerManager().SetTimer(StrikeTimer, FTimerDelegate::CreateWeakLambda(this, Strike), ImpactDelay, false);
	}
	else
	{
		Strike();
	}
}

void AGolfGameMode::OnBallStopped(AGolfBall* Ball, EGolfShotResult Result)
{
	AGolfGameState* State = GetGolfState();
	AGolfPlayerState* Player = FindBallOwner(Ball);
	if (!Player || State->Phase != EGolfMatchPhase::PlayingHole || !State->CurrentHole)
	{
		return;
	}
	bShotInFlight = false;

	const int32 Par = State->CurrentHole->Par;
	const int32 Index = State->HoleIndex;

	switch (Result)
	{
	case EGolfShotResult::Holed:
		Player->bHoledOut = true;
		Player->HoleScores[Index] = Player->Strokes;
		State->MulticastAnnounce(FString::Printf(TEXT("%s  %s"), *ScoreName(Player->Strokes, Par), *Player->GetPlayerName()));
		break;

	case EGolfShotResult::Water:
	case EGolfShotResult::OutOfBounds:
		Player->Strokes++;
		Ball->PlaceAt(Player->LastShotLocation, Player->bLastShotFromTee);
		State->MulticastAnnounce(Result == EGolfShotResult::Water ? TEXT("WATER HAZARD  ·  +1 STROKE") : TEXT("OUT OF BOUNDS  ·  +1 STROKE"));
		break;

	default:
		State->MulticastAnnounce(FString::Printf(TEXT("%s  ·  %.0f m to the pin"),
			*GolfPhysics::LieName(Ball->GetLie()), FVector::Dist2D(Ball->GetRestLocation(), State->CurrentHole->GetCupLocation()) / 100.f));
		break;
	}

	if (!Player->bHoledOut && Player->Strokes >= Par * 2)
	{
		Player->bHoledOut = true;
		Player->HoleScores[Index] = Par * 2;
		State->MulticastAnnounce(FString::Printf(TEXT("%s picks up  ·  %d"), *Player->GetPlayerName(), Par * 2));
	}
	if (Player->bHoledOut)
	{
		Ball->SetActorHiddenInGame(true);
	}

	// Let the golfer react, and give everyone time to watch it.
	EGolferReaction Reaction = EGolferReaction::None;
	switch (Result)
	{
	case EGolfShotResult::Holed:
		Reaction = Player->Strokes == 1 ? EGolferReaction::HoleInOne
			: Player->bLastShotWasPutt ? EGolferReaction::PuttVictory : EGolferReaction::Celebrate;
		break;
	case EGolfShotResult::Water:
	case EGolfShotResult::OutOfBounds:
		Reaction = EGolferReaction::BadShot;
		break;
	default:
		if (Player->bLastShotWasPutt && FVector::Dist2D(Ball->GetRestLocation(), State->CurrentHole->GetCupLocation()) < 300.f)
		{
			Reaction = EGolferReaction::PuttMiss;
		}
		break;
	}
	float Delay = TurnDelay;
	if (AGolfCharacter* Golfer = GetGolfer(Player); Golfer && Reaction != EGolferReaction::None)
	{
		const float Duration = Golfer->GetReactionDuration(Reaction);
		if (Duration > 0.f)
		{
			Golfer->SetActorHiddenInGame(false);
			Golfer->MulticastPlayReaction(Reaction, State->CurrentHole->GetCupLocation());
			ViewAll(Golfer, 0.5f);
			Delay = FMath::Max(Delay, Duration);
		}
	}
	GetWorldTimerManager().SetTimer(FlowTimer, this, &AGolfGameMode::NextTurn, Delay, false);
}

void AGolfGameMode::EndHole()
{
	AGolfGameState* State = GetGolfState();
	State->Phase = EGolfMatchPhase::HoleSummary;
	State->ActivePlayer = nullptr;

	const int32 Next = State->HoleIndex + 1;
	GetWorldTimerManager().SetTimer(FlowTimer, FTimerDelegate::CreateWeakLambda(this, [this, Next]()
	{
		AGolfGameState* GolfState = GetGolfState();
		if (Holes.IsValidIndex(Next))
		{
			StartHole(Next);
			return;
		}

		GolfState->Phase = EGolfMatchPhase::RoundOver;
		ReleaseToRoam();
		AGolfPlayerState* Winner = nullptr;
		for (AGolfPlayerState* Player : GetRoundPlayers())
		{
			if (!Winner || Player->GetTotalStrokes() < Winner->GetTotalStrokes())
			{
				Winner = Player;
			}
		}
		if (Winner)
		{
			GolfState->MulticastAnnounce(FString::Printf(TEXT("%s WINS  ·  %d"), *Winner->GetPlayerName(), Winner->GetTotalStrokes()));
		}
	}), HoleSummarySeconds, false);
}
