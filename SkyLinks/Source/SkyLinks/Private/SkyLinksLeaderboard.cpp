#include "SkyLinksLeaderboard.h"
#include "GolfGameState.h"
#include "GolfPlayerState.h"
#include "Components/TextRenderComponent.h"
#include "Engine/World.h"

namespace
{
	constexpr float BoardHalfWidth = 440.f;   // cm, inside the screen's frame
	constexpr float TopRow = 170.f;
	constexpr float RowPitch = 62.f;
	constexpr float TextSize = 48.f;
}

ASkyLinksLeaderboard::ASkyLinksLeaderboard()
{
	PrimaryActorTick.bCanEverTick = true;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));

	auto MakeText = [this](const FName& Name, float Y, float Z, EHorizTextAligment Align, float Size)
	{
		UTextRenderComponent* Text = CreateDefaultSubobject<UTextRenderComponent>(Name);
		Text->SetupAttachment(GetRootComponent());
		Text->SetRelativeLocation(FVector(2.f, Y, Z));
		Text->SetHorizontalAlignment(Align);
		Text->SetVerticalAlignment(EVRTA_TextCenter);
		Text->SetWorldSize(Size);
		Text->SetTextRenderColor(FColor::White);
		Text->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		return Text;
	};
	Title = MakeText(TEXT("Title"), 0.f, TopRow + 80.f, EHTA_Center, 60.f);
	Title->SetText(FText::FromString(TEXT("LEADERBOARD")));
	Title->SetTextRenderColor(FColor(255, 214, 60));
	for (int32 Row = 0; Row < Rows; ++Row)
	{
		const float Z = TopRow - Row * RowPitch;
		Names.Add(MakeText(*FString::Printf(TEXT("Name%d"), Row), -BoardHalfWidth, Z, EHTA_Left, TextSize));
		Scores.Add(MakeText(*FString::Printf(TEXT("Score%d"), Row), BoardHalfWidth, Z, EHTA_Right, TextSize));
	}
}

void ASkyLinksLeaderboard::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	SinceRefresh += DeltaSeconds;
	if (SinceRefresh >= 1.f)
	{
		SinceRefresh = 0.f;
		Refresh();
	}
}

void ASkyLinksLeaderboard::Refresh()
{
	const AGolfGameState* State = GetWorld()->GetGameState<AGolfGameState>();
	TArray<const AGolfPlayerState*> Players;
	if (State)
	{
		for (const APlayerState* Base : State->PlayerArray)
		{
			if (const AGolfPlayerState* Player = Cast<AGolfPlayerState>(Base))
			{
				Players.Add(Player);
			}
		}
	}
	auto Played = [](const AGolfPlayerState* Player)
	{
		int32 Holes = 0;
		for (const int32 Score : Player->HoleScores)
		{
			Holes += Score > 0 ? 1 : 0;
		}
		return Holes;
	};
	const TArray<int32> Pars = State ? State->Pars : TArray<int32>();
	Players.Sort([&Pars, &Played](const AGolfPlayerState& A, const AGolfPlayerState& B)
	{
		const int32 ToParA = A.GetToPar(Pars), ToParB = B.GetToPar(Pars);
		return ToParA != ToParB ? ToParA < ToParB : Played(&A) > Played(&B);
	});

	int32 Position = 0;
	int32 LastToPar = INT32_MIN;
	for (int32 Row = 0; Row < Rows; ++Row)
	{
		if (!Players.IsValidIndex(Row))
		{
			Names[Row]->SetText(FText::GetEmpty());
			Scores[Row]->SetText(FText::GetEmpty());
			continue;
		}
		const AGolfPlayerState* Player = Players[Row];
		const int32 ToPar = Player->GetToPar(Pars);
		if (ToPar != LastToPar)
		{
			Position = Row + 1;   // tied players share a position
			LastToPar = ToPar;
		}
		const int32 Holes = Played(Player);
		const FString Thru = Holes >= Pars.Num() && Pars.Num() > 0 ? FString(TEXT("F")) : FString::Printf(TEXT("%d"), Holes);
		const FString Score = ToPar == 0 ? FString(TEXT("E")) : FString::Printf(TEXT("%+d"), ToPar);
		Names[Row]->SetText(FText::FromString(FString::Printf(TEXT("%d  %s"), Position, *Player->GetPlayerName().Left(14).ToUpper())));
		Scores[Row]->SetText(FText::FromString(FString::Printf(TEXT("%s   THRU %s"), *Score, *Thru)));
		// Golf convention: red for under par.
		Scores[Row]->SetTextRenderColor(ToPar < 0 ? FColor(255, 70, 60) : FColor::White);
	}
}
