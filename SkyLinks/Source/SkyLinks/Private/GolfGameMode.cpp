#include "GolfGameMode.h"
#include "SkyLinks.h"
#include "GolfBall.h"
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

AGolfGameMode::AGolfGameMode()
{
	DefaultPawnClass = AGolfCharacter::StaticClass();
	PlayerControllerClass = AGolfPlayerController::StaticClass();
	PlayerStateClass = AGolfPlayerState::StaticClass();
	GameStateClass = AGolfGameState::StaticClass();
	HUDClass = AGolfHUD::StaticClass();
	BallClass = AGolfBall::StaticClass();
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

	AGolfGameState* State = GetGolfState();
	if (State->Phase == EGolfMatchPhase::Lobby || State->Phase == EGolfMatchPhase::RoundOver)
	{
		// Stand on the first tee while waiting.
		if (AGolfCharacter* Golfer = GetGolfer(Player); Golfer && Holes.Num() > 0)
		{
			const FVector Tee = Holes[0]->GetTeeLocation() + FVector(0.f, 0.f, GolfPhysics::BallRadius);
			Golfer->SetAddress(Tee, Holes[0]->GetDefaultAimYaw(Tee));
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
		Player->bInRound = false;
		TeeOrder.Remove(Player);

		AGolfGameState* State = GetGolfState();
		if (State->ActivePlayer == Player && State->Phase == EGolfMatchPhase::PlayingHole)
		{
			bShotInFlight = false;
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
	return Player ? Player->GetPawn<AGolfCharacter>() : nullptr;
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

	for (AGolfPlayerState* Player : GetRoundPlayers())
	{
		Player->Strokes = 0;
		Player->bHoledOut = false;
		Player->bTeedOff = false;
		Player->Ball->SetActorHiddenInGame(true);
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
			const FVector Tee = Hole->GetTeeLocation() + FVector(0.f, 0.f, GolfPhysics::BallRadius);
			Golfer->SetAddress(Tee, Hole->GetDefaultAimYaw(Tee));
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

	// Only the golfer whose turn it is stands on the course.
	for (APlayerState* Base : GameState->PlayerArray)
	{
		if (AGolfCharacter* Golfer = GetGolfer(Cast<AGolfPlayerState>(Base)))
		{
			Golfer->SetActorHiddenInGame(Base != Player);
		}
	}

	if (AGolfCharacter* Golfer = GetGolfer(Player))
	{
		const FVector BallLocation = Ball->GetRestLocation();
		Golfer->SetAddress(BallLocation, Hole->GetDefaultAimYaw(BallLocation));
		ViewAll(Golfer, 0.6f);
	}

	State->MulticastAnnounce(FString::Printf(TEXT("%s  ·  SHOT %d"), *Player->GetPlayerName(), Player->Strokes + 1));
}

void AGolfGameMode::HandleShot(APlayerController* Shooter, const FGolfShotInput& Input)
{
	AGolfGameState* State = GetGolfState();
	AGolfPlayerState* Player = Shooter ? Shooter->GetPlayerState<AGolfPlayerState>() : nullptr;
	if (!Player || State->Phase != EGolfMatchPhase::PlayingHole || State->ActivePlayer != Player || bShotInFlight
		|| !Player->Ball || !Player->Ball->IsAtRest())
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
	Player->Strokes++;
	Player->bTeedOff = true;
	bShotInFlight = true;

	if (AGolfCharacter* Golfer = GetGolfer(Player))
	{
		Golfer->SetAddress(Ball->GetRestLocation(), Clean.AimYaw);
		Golfer->MulticastPlaySwing();
	}

	const FVector Wind = Club.bIsPutter ? FVector::ZeroVector : State->Wind;
	Ball->Launch(GolfPhysics::MakeLaunch(Club, Clean, Lie, Start), Wind, State->CurrentHole->GetCupLocation(), State->CurrentHole->CupRadius);

	// Cut everyone to the chase camera behind the ball.
	TWeakObjectPtr<AGolfBall> WeakBall = Ball;
	GetWorldTimerManager().SetTimer(CameraTimer, FTimerDelegate::CreateWeakLambda(this, [this, WeakBall]()
	{
		if (WeakBall.IsValid())
		{
			ViewAll(WeakBall.Get(), 0.35f);
		}
	}), ChaseCameraDelay, false);
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

	GetWorldTimerManager().SetTimer(FlowTimer, this, &AGolfGameMode::NextTurn, TurnDelay, false);
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
