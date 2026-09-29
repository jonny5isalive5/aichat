#include "GolfHUD.h"
#include "GolfBall.h"
#include "GolfBuggy.h"
#include "GolfGameState.h"
#include "GolfHole.h"
#include "GolfPhysics.h"
#include "GolfPlayerController.h"
#include "GolfPlayerState.h"
#include "GolfSessionSubsystem.h"
#include "GolfVoiceSubsystem.h"
#include "SkyLinksGrass.h"
#include "EngineUtils.h"
#include "Engine/GameInstance.h"
#include "CanvasItem.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Engine/World.h"
#include "Camera/PlayerCameraManager.h"
#include "Engine/TextureRenderTarget2D.h"

namespace Palette
{
	// Holographic sports-broadcast look: see-through blue glass panels with hairline frames and bright corner
	// brackets, thin rings and arcs, white type with pale-cyan accents.
	const FLinearColor Panel(0.04f, 0.16f, 0.34f, 0.42f);
	const FLinearColor PanelSolid(0.03f, 0.12f, 0.28f, 0.55f);
	const FLinearColor Trim(0.82f, 0.95f, 1.f, 0.9f);
	const FLinearColor Gold(1.f, 0.78f, 0.28f, 1.f);      // amber highlights: par, carry, lie, headings
	const FLinearColor White(1.f, 1.f, 1.f, 1.f);
	const FLinearColor Dim(0.5f, 0.85f, 1.f, 0.95f);      // cyan captions
	const FLinearColor Glow(0.55f, 0.88f, 1.f, 0.95f);
	const FLinearColor Hairline(0.8f, 0.94f, 1.f, 0.45f);
	const FLinearColor Under(0.45f, 1.f, 0.8f, 1.f);   // under par: cool green-cyan
	const FLinearColor Over(1.f, 0.5f, 0.45f, 1.f);    // over par: soft red
	const FLinearColor Accept(0.3f, 0.95f, 0.72f, 0.3f); // go / join / play: green-cyan glass
	const FLinearColor Red(0.9f, 0.22f, 0.18f, 1.f);
	const FLinearColor Green(0.45f, 0.85f, 0.3f, 1.f);
	// Landing rings and break arrows: red reads against every shade of grass.
	const FLinearColor Target(1.f, 0.16f, 0.12f, 1.f);
	const FLinearColor TargetIdle(1.f, 0.35f, 0.3f, 0.9f);
}

// ---------------------------------------------------------------- drawing helpers

void AGolfHUD::Box(const FVector2D& Position, const FVector2D& Size, const FLinearColor& Color)
{
	FCanvasTileItem Item(Position, Size, Color);
	Item.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Item);

	// Panels (not thin bars or meters) get the holographic frame: a hairline border, bright corner brackets and a
	// faint highlight along the top edge.
	if (Size.X > 4.f * U && Size.Y > 3.f * U && Color.A < 0.6f)
	{
		const FVector2D A = Position, B = Position + FVector2D(Size.X, 0.f), C = Position + Size, D = Position + FVector2D(0.f, Size.Y);
		Line(A, B, Palette::Hairline, 0.12f * U);
		Line(B, C, Palette::Hairline, 0.12f * U);
		Line(C, D, Palette::Hairline, 0.12f * U);
		Line(D, A, Palette::Hairline, 0.12f * U);
		const float L = FMath::Min(2.2f * U, FMath::Min(Size.X, Size.Y) * 0.25f);
		const float T = 0.3f * U;
		Line(A, A + FVector2D(L, 0.f), Palette::Glow, T);  Line(A, A + FVector2D(0.f, L), Palette::Glow, T);
		Line(B, B - FVector2D(L, 0.f), Palette::Glow, T);  Line(B, B + FVector2D(0.f, L), Palette::Glow, T);
		Line(C, C - FVector2D(L, 0.f), Palette::Glow, T);  Line(C, C - FVector2D(0.f, L), Palette::Glow, T);
		Line(D, D + FVector2D(L, 0.f), Palette::Glow, T);  Line(D, D - FVector2D(0.f, L), Palette::Glow, T);
		FCanvasTileItem Sheen(Position + FVector2D(0.f, 0.15f * U), FVector2D(Size.X, FMath::Min(Size.Y * 0.35f, 3.f * U)), FLinearColor(0.8f, 0.95f, 1.f, 0.05f));
		Sheen.BlendMode = SE_BLEND_Translucent;
		Canvas->DrawItem(Sheen);
	}
}

void AGolfHUD::Arc(const FVector2D& Center, float Radius, float StartDegrees, float SweepDegrees, const FLinearColor& Color, float Thickness)
{
	const int32 Segments = FMath::Max(4, FMath::RoundToInt(FMath::Abs(SweepDegrees) / 6.f));
	for (int32 Index = 0; Index < Segments; ++Index)
	{
		const float A0 = FMath::DegreesToRadians(StartDegrees + SweepDegrees * Index / Segments);
		const float A1 = FMath::DegreesToRadians(StartDegrees + SweepDegrees * (Index + 1) / Segments);
		Line(Center + FVector2D(FMath::Cos(A0), FMath::Sin(A0)) * Radius, Center + FVector2D(FMath::Cos(A1), FMath::Sin(A1)) * Radius, Color, Thickness);
	}
}

void AGolfHUD::Disc(const FVector2D& Center, float Radius, const FLinearColor& Color)
{
	FCanvasNGonItem Item(Center, FVector2D(Radius, Radius), 48, Color);
	Item.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Item);
}

void AGolfHUD::Ring(const FVector2D& Center, float Radius, const FLinearColor& Color, float Thickness)
{
	constexpr int32 Segments = 48;
	for (int32 Index = 0; Index < Segments; ++Index)
	{
		const float A0 = 2.f * PI * Index / Segments;
		const float A1 = 2.f * PI * (Index + 1) / Segments;
		Line(Center + FVector2D(FMath::Cos(A0), FMath::Sin(A0)) * Radius, Center + FVector2D(FMath::Cos(A1), FMath::Sin(A1)) * Radius, Color, Thickness);
	}
}

void AGolfHUD::Line(const FVector2D& A, const FVector2D& B, const FLinearColor& Color, float Thickness)
{
	FCanvasLineItem Item(A, B);
	Item.SetColor(Color);
	Item.LineThickness = Thickness;
	Canvas->DrawItem(Item);
}

void AGolfHUD::Label(const FString& Text, const FVector2D& Position, float Height, const FLinearColor& Color, bool bCenter)
{
	UFont* Font = GEngine->GetLargeFont();
	const float Scale = Height * U / FMath::Max(1.f, (float)Font->GetMaxCharHeight());
	FCanvasTextItem Item(Position, FText::FromString(Text), Font, Color);
	Item.Scale = FVector2D(Scale, Scale);
	Item.bCentreX = bCenter;
	Item.bCentreY = bCenter;
	Item.EnableShadow(FLinearColor(0.f, 0.f, 0.f, 0.6f), FVector2D(1.5f, 1.5f));
	Item.bOutlined = true;
	Item.OutlineColor = FLinearColor(0.f, 0.03f, 0.08f, 0.75f);
	Canvas->DrawItem(Item);
}

void AGolfHUD::Heading(const FString& Text, const FVector2D& Position, float Width, float Height, bool bCenter)
{
	// Spaced capitals read as a broadcast caption.
	FString Spaced;
	for (const TCHAR Character : Text.ToUpper())
	{
		Spaced.AppendChar(Character);
		Spaced.AppendChar(TEXT(' '));
	}
	Spaced.TrimEndInline();
	const float Left = bCenter ? Position.X - Width * 0.5f : Position.X;
	Label(Spaced, bCenter ? Position + FVector2D(0.f, Height * 0.5f * U) : Position, Height, Palette::Gold, bCenter);
	const float RuleY = Position.Y + Height * 1.25f * U;
	Line(FVector2D(Left, RuleY), FVector2D(Left + Width, RuleY), Palette::Hairline, 0.12f * U);
	Line(FVector2D(Left, RuleY), FVector2D(Left + FMath::Min(Width * 0.22f, 6.f * U), RuleY), Palette::Glow, 0.35f * U);
	if (bCenter)
	{
		Line(FVector2D(Left + Width, RuleY), FVector2D(Left + Width - FMath::Min(Width * 0.22f, 6.f * U), RuleY), Palette::Glow, 0.35f * U);
	}
}

void AGolfHUD::RoundButton(EGolfHudButton Id, const FVector2D& Center, float Radius, const FString& Text, const FLinearColor& Fill, int32 Payload)
{
	// Glass disc in the button's own tint, a thin bright ring, a glowing accent arc outside it and four ticks.
	FLinearColor Glass = Fill;
	Glass.A = FMath::Min(Fill.A, 0.32f);
	Disc(Center, Radius, Glass);
	Ring(Center, Radius, Palette::Trim, 0.18f * U);
	Arc(Center, Radius * 1.12f, -150.f, 110.f, Palette::Glow, 0.35f * U);
	Arc(Center, Radius * 1.12f, 30.f, 50.f, Palette::Hairline, 0.2f * U);
	for (int32 Tick = 0; Tick < 4; ++Tick)
	{
		const FVector2D Dir(FMath::Cos(Tick * PI * 0.5f), FMath::Sin(Tick * PI * 0.5f));
		Line(Center + Dir * Radius * 0.86f, Center + Dir * Radius * 0.96f, Palette::Hairline, 0.18f * U);
	}
	Label(Text, Center, Radius * 0.45f / U * 1.f, Palette::White, true);
	Buttons.Add({ Id, Center, Radius, Payload });
}

bool AGolfHUD::ToScreen(const FVector& World, FVector2D& OutScreen) const
{
	return PlayerOwner && PlayerOwner->ProjectWorldLocationToScreen(World, OutScreen, true);
}

EGolfHudButton AGolfHUD::HitTest(const FVector2D& ScreenPosition, int32& OutPayload) const
{
	// Last drawn is on top, so test in reverse.
	for (int32 Index = Buttons.Num() - 1; Index >= 0; --Index)
	{
		const FButton& Button = Buttons[Index];
		const FVector2D Offset = ScreenPosition - Button.Center;
		const bool bInside = Button.RectSize.X > 0.f
			? FMath::Abs(Offset.X) <= Button.RectSize.X * 0.5f && FMath::Abs(Offset.Y) <= Button.RectSize.Y * 0.5f
			: Offset.Size() <= Button.Radius * 1.1f;
		if (bInside)
		{
			OutPayload = Button.Payload;
			return Button.Id;
		}
	}
	return EGolfHudButton::None;
}

// ---------------------------------------------------------------- frame

void AGolfHUD::BeginPlay()
{
	Super::BeginPlay();
	// 3D grass is purely visual and grows around this machine's camera, so every player gets their own.
	if (!TActorIterator<ASkyLinksGrass>(GetWorld()))
	{
		FActorSpawnParameters Params;
		Params.Owner = this;
		GetWorld()->SpawnActor<ASkyLinksGrass>(ASkyLinksGrass::StaticClass(), FTransform::Identity, Params);
	}
}

void AGolfHUD::DrawHUD()
{
	Super::DrawHUD();
	Buttons.Reset();
	if (!Canvas)
	{
		return;
	}
	U = Canvas->ClipY / 100.f;

	AGolfGameState* State = GetWorld()->GetGameState<AGolfGameState>();
	AGolfPlayerController* Controller = Cast<AGolfPlayerController>(PlayerOwner);
	if (!State || !Controller)
	{
		return;
	}

	switch (State->Phase)
	{
	case EGolfMatchPhase::Lobby:
		// The menu can be put away to walk round the clubhouse and pick a buggy.
		if (!Controller->IsLobbyPanelHidden() || Controller->IsKeypadOpen())
		{
			DrawLobby(State, Controller);
		}
		else
		{
			DrawMoving(Controller);
			const TCHAR* Hint = Controller->IsHost() ? TEXT("Pick a buggy (E), then walk or drive to the 1st tee and press E to tee off")
				: TEXT("Pick a buggy (E)  ·  waiting for the host to tee off on the 1st");
			Box(FVector2D(Canvas->ClipX * 0.5f - 42.f * U, 2.f * U), FVector2D(84.f * U, 4.5f * U), Palette::Panel);
			Line(FVector2D(Canvas->ClipX * 0.5f - 42.f * U, 2.f * U), FVector2D(Canvas->ClipX * 0.5f - 42.f * U, 6.5f * U), Palette::Glow, 0.6f * U);
			Label(FString(Hint).ToUpper(), FVector2D(Canvas->ClipX * 0.5f, 4.25f * U), 2.f, Palette::White, true);
		}
		RoundButton(EGolfHudButton::LobbyPanel, FVector2D(Canvas->ClipX * 0.5f, Canvas->ClipY - 6.f * U), 4.5f * U,
			Controller->IsLobbyPanelHidden() ? TEXT("MENU") : TEXT("WALK"), Palette::PanelSolid);
		break;
	case EGolfMatchPhase::PlayingHole:
		DrawPlaying(State, Controller);
		break;
	case EGolfMatchPhase::HoleSummary:
		DrawHoleCard(State);
		DrawScorecard(State);
		break;
	case EGolfMatchPhase::RoundOver:
		if (Controller->IsLobbyPanelHidden())
		{
			DrawMoving(Controller);
		}
		else
		{
			DrawScorecard(State);
		}
		RoundButton(EGolfHudButton::LobbyPanel, FVector2D(Canvas->ClipX * 0.5f - 22.f * U, Canvas->ClipY - 12.f * U), 5.f * U,
			Controller->IsLobbyPanelHidden() ? TEXT("SCORES") : TEXT("WALK"), Palette::PanelSolid);
		if (Controller->IsLocalController() && GetNetMode() != NM_Client)
		{
			RoundButton(EGolfHudButton::Start, FVector2D(Canvas->ClipX * 0.5f, Canvas->ClipY - 12.f * U), 8.f * U, TEXT("AGAIN"), Palette::Accept);
		}
		break;
	}
	DrawAnnouncement(State);
	DrawVoice(State, Controller);
	DrawInvitePopup();
}

void AGolfHUD::DrawVoice(AGolfGameState* State, AGolfPlayerController* Controller)
{
	const UGolfVoiceSubsystem* Voice = GetGameInstance()->GetSubsystem<UGolfVoiceSubsystem>();
	if (!Voice) return;
	const bool bMuted = Voice->IsMicrophoneMuted();
	const FString MicLabel = bMuted ? TEXT("MUTED") : Voice->IsReady() ? TEXT("MIC ON") : TEXT("NO VOICE");
	RoundButton(EGolfHudButton::Microphone, FVector2D(Canvas->ClipX - 6.5f * U, 35.f * U), 3.8f * U,
		MicLabel, bMuted ? Palette::Red : Voice->IsReady() ? Palette::Accept : Palette::PanelSolid);
	RoundButton(EGolfHudButton::VoicePanel, FVector2D(Canvas->ClipX - 16.f * U, 35.f * U), 3.8f * U,
		TEXT("GROUP"), Palette::PanelSolid);
	if (!Controller->IsVoicePanelOpen()) return;
	const FVector2D Origin(Canvas->ClipX - 54.f * U, 41.f * U);
	Box(Origin, FVector2D(52.f * U, 40.f * U), Palette::PanelSolid);
	Buttons.Add({ EGolfHudButton::VoicePanelBackground, Origin + FVector2D(26.f * U, 20.f * U), 0.f, 0, FVector2D(52.f * U, 40.f * U) });
	Heading(TEXT("Voice Group"), Origin + FVector2D(2.f * U, 1.6f * U), 48.f * U, 2.2f);
	Label(Voice->GetStatus(), Origin + FVector2D(2.f * U, 5.8f * U), 1.9f, Palette::Dim, false);
	const float Time = GetWorld()->GetRealTimeSeconds();
	int32 Row = 0;
	for (const APlayerState* GroupPlayer : State->PlayerArray)
	{
		if (!GroupPlayer || Row >= 4) continue;
		const float RowY = (13.f + Row++ * 7.f) * U;
		const bool bSelf = GroupPlayer == Controller->PlayerState;
		const bool bPlayerMuted = bSelf ? bMuted : Voice->IsPlayerMuted(GroupPlayer);
		const bool bTalking = Voice->IsPlayerTalking(GroupPlayer);
		// Level bars beside the name: they bounce while that player is talking.
		for (int32 Bar = 0; Bar < 4; ++Bar)
		{
			const float Level = bTalking ? 0.35f + 0.65f * FMath::Abs(FMath::Sin(Time * 9.f + Bar * 1.7f)) : 0.2f;
			const FVector2D Base = Origin + FVector2D((2.2f + Bar * 0.9f) * U, RowY + 1.4f * U);
			Line(Base, Base - FVector2D(0.f, Level * 2.8f * U), bTalking ? Palette::Under : Palette::Hairline, 0.5f * U);
		}
		Label(GroupPlayer->GetPlayerName().Left(20).ToUpper() + (bSelf ? TEXT("  (YOU)") : TEXT("")),
			Origin + FVector2D(6.5f * U, RowY - U), 2.1f, bTalking ? Palette::Under : Palette::White, false);
		Line(Origin + FVector2D(2.f * U, RowY + 3.2f * U), Origin + FVector2D(40.f * U, RowY + 3.2f * U), Palette::Hairline, 0.1f * U);
		RoundButton(bSelf ? EGolfHudButton::Microphone : EGolfHudButton::MutePlayer,
			Origin + FVector2D(46.f * U, RowY), 3.f * U, bPlayerMuted ? TEXT("UNMUTE") : TEXT("MUTE"),
			bPlayerMuted ? Palette::Red : Palette::PanelSolid, GroupPlayer->GetPlayerId());
	}
}

void AGolfHUD::DrawLobby(AGolfGameState* State, AGolfPlayerController* Controller)
{
	if (Controller->IsKeypadOpen())
	{
		DrawKeypad(Controller);
		return;
	}

	const UGolfSessionSubsystem* Sessions = GetGameInstance()->GetSubsystem<UGolfSessionSubsystem>();
	const bool bFriendsPanel = Controller->IsFriendsOpen() && Sessions && Sessions->SupportsFriends();
	const FVector2D Center(Canvas->ClipX * (bFriendsPanel ? 0.33f : 0.5f), Canvas->ClipY * 0.5f);
	const FVector2D Pos = Center - FVector2D(45.f * U, 40.f * U);
	Box(Pos, FVector2D(90.f * U, 80.f * U), Palette::Panel);

	// Title block: big logotype, thin rule with glowing ends, strapline.
	Label(TEXT("SKY LINKS"), Center - FVector2D(0.f, 33.f * U), 8.f, Palette::White, true);
	Line(Center - FVector2D(30.f * U, 28.2f * U), Center + FVector2D(30.f * U, -28.2f * U), Palette::Hairline, 0.12f * U);
	Line(Center - FVector2D(30.f * U, 28.2f * U), Center - FVector2D(22.f * U, 28.2f * U), Palette::Glow, 0.4f * U);
	Line(Center + FVector2D(22.f * U, -28.2f * U), Center + FVector2D(30.f * U, -28.2f * U), Palette::Glow, 0.4f * U);
	Label(TEXT("K E E P I N G   F R I E N D S   C O N N E C T E D"), Center - FVector2D(0.f, 26.f * U), 1.8f, Palette::Gold, true);

	int32 TotalPar = 0;
	for (const int32 Par : State->Pars)
	{
		TotalPar += Par;
	}
	if (State->Pars.Num() == 0)
	{
		Label(TEXT("No course in this level. Run Scripts/build_blockout_course.py, then open Maps/Course."),
			Center - FVector2D(0.f, 20.f * U), 2.6f, Palette::Over, true);
	}
	else
	{
		// Course infographic: one bar per hole, height by par, with the totals beside it.
		const float ChartLeft = Center.X - 38.f * U;
		const float ChartBase = Center.Y - 15.f * U;
		const float Pitch = FMath::Min(2.2f * U, 44.f * U / State->Pars.Num());
		for (int32 Index = 0; Index < State->Pars.Num(); ++Index)
		{
			const float Height = (State->Pars[Index] - 2) * 1.6f * U;
			const float X = ChartLeft + (Index + 0.5f) * Pitch;
			Line(FVector2D(X, ChartBase), FVector2D(X, ChartBase - Height), State->Pars[Index] >= 5 ? Palette::Glow : Palette::Trim, Pitch * 0.55f);
		}
		Line(FVector2D(ChartLeft, ChartBase + 0.5f * U), FVector2D(ChartLeft + Pitch * State->Pars.Num(), ChartBase + 0.5f * U), Palette::Hairline, 0.12f * U);
		Label(TEXT("COURSE PROFILE  ·  PAR BY HOLE"), FVector2D(ChartLeft, ChartBase + 1.2f * U), 1.6f, Palette::Dim, false);

		const float StatX = Center.X + 12.f * U;
		Label(FString::FromInt(State->Pars.Num()), FVector2D(StatX, ChartBase - 6.5f * U), 5.f, Palette::White, false);
		Label(TEXT("HOLES"), FVector2D(StatX, ChartBase - 0.4f * U), 1.6f, Palette::Dim, false);
		Line(FVector2D(StatX + 10.f * U, ChartBase - 6.f * U), FVector2D(StatX + 10.f * U, ChartBase + 1.f * U), Palette::Hairline, 0.12f * U);
		Label(FString::FromInt(TotalPar), FVector2D(StatX + 12.f * U, ChartBase - 6.5f * U), 5.f, Palette::White, false);
		Label(TEXT("PAR"), FVector2D(StatX + 12.f * U, ChartBase - 0.4f * U), 1.6f, Palette::Dim, false);
	}

	// Room code in digit slots, big, so it can be read out to friends.
	float Y = Center.Y - 9.f * U;
	if (!State->RoomCode.IsEmpty())
	{
		Heading(TEXT("Room Code"), FVector2D(Center.X, Y), 36.f * U, 1.8f, true);
		for (int32 Index = 0; Index < State->RoomCode.Len(); ++Index)
		{
			const FVector2D Slot(Center.X + (Index - (State->RoomCode.Len() - 1) * 0.5f) * 8.f * U, Y + 8.f * U);
			Box(Slot - FVector2D(3.2f * U, 3.8f * U), FVector2D(6.4f * U, 7.6f * U), Palette::PanelSolid);
			Label(State->RoomCode.Mid(Index, 1), Slot, 5.5f, Palette::White, true);
		}
		Y += 14.f * U;
	}

	// Players as glass chips.
	const int32 Count = State->PlayerArray.Num();
	const float ChipWidth = 20.f * U;
	int32 Index = 0;
	for (APlayerState* Player : State->PlayerArray)
	{
		const int32 Column = Index % 4, Row = Index / 4;
		const int32 InRow = FMath::Min(4, Count - Row * 4);
		const FVector2D Chip(Center.X + (Column - (InRow - 1) * 0.5f) * (ChipWidth + 1.f * U) - ChipWidth * 0.5f, Y + Row * 4.6f * U);
		FCanvasTileItem Tile(Chip, FVector2D(ChipWidth, 3.8f * U), Palette::Panel);
		Tile.BlendMode = SE_BLEND_Translucent;
		Canvas->DrawItem(Tile);
		Line(Chip, Chip + FVector2D(0.f, 3.8f * U), Index == 0 ? Palette::Glow : Palette::Hairline, 0.4f * U);
		Label(Player->GetPlayerName().Left(12).ToUpper(), Chip + FVector2D(ChipWidth * 0.5f, 1.9f * U), 2.f, Palette::White, true);
		++Index;
	}

	const ENetMode NetMode = GetNetMode();
	const float ButtonY = Center.Y + 27.f * U;
	if (NetMode == NM_Standalone)
	{
		RoundButton(EGolfHudButton::LobbyPanel, FVector2D(Center.X - 22.f * U, ButtonY), 7.5f * U, TEXT("SOLO"), Palette::PanelSolid);
		RoundButton(EGolfHudButton::Host, FVector2D(Center.X, ButtonY), 7.5f * U, TEXT("HOST"), Palette::PanelSolid);
		RoundButton(EGolfHudButton::Join, FVector2D(Center.X + 22.f * U, ButtonY), 7.5f * U, TEXT("JOIN"), Palette::PanelSolid);
	}
	else if (NetMode == NM_ListenServer)
	{
		RoundButton(EGolfHudButton::LobbyPanel, FVector2D(Center.X - 11.f * U, ButtonY), 7.5f * U, TEXT("PLAY"), Palette::Accept);
		if (Sessions && Sessions->SupportsFriends())
		{
			RoundButton(EGolfHudButton::Friends, FVector2D(Center.X + 11.f * U, ButtonY), 7.5f * U, TEXT("INVITE"), Palette::PanelSolid);
		}
		Label(FString::Printf(TEXT("%d / %d PLAYERS"), Count, UGolfSessionSubsystem::MaxPlayers),
			FVector2D(Center.X, ButtonY - 10.5f * U), 2.2f, Palette::Dim, true);
	}
	else
	{
		Label(TEXT("WAITING FOR THE HOST TO TEE OFF"), FVector2D(Center.X, ButtonY), 2.8f, Palette::Dim, true);
	}

	if (Sessions && !Sessions->GetStatus().IsEmpty())
	{
		Label(Sessions->GetStatus(), FVector2D(Center.X, Center.Y + 37.f * U), 2.4f, Palette::Gold, true);
	}
	if (bFriendsPanel)
	{
		DrawFriends();
	}
}

void AGolfHUD::DrawKeypad(AGolfPlayerController* Controller)
{
	const FVector2D Center(Canvas->ClipX * 0.5f, Canvas->ClipY * 0.5f);
	Box(Center - FVector2D(34.f * U, 44.f * U), FVector2D(68.f * U, 88.f * U), Palette::Panel);
	Heading(TEXT("Enter Room Code"), Center - FVector2D(0.f, 40.f * U), 44.f * U, 2.4f, true);

	// Four slots for the digits typed so far; the next one pulses.
	const FString Code = Controller->GetEnteredCode();
	const float Pulse = 0.5f + 0.5f * FMath::Sin(GetWorld()->GetRealTimeSeconds() * 5.f);
	for (int32 Index = 0; Index < 4; ++Index)
	{
		const FVector2D Slot(Center.X + (Index - 1.5f) * 9.f * U, Center.Y - 27.f * U);
		Box(Slot - FVector2D(3.5f * U, 4.f * U), FVector2D(7.f * U, 8.f * U), Palette::PanelSolid);
		if (Index < Code.Len())
		{
			Label(Code.Mid(Index, 1), Slot, 6.f, Palette::White, true);
		}
		else if (Index == Code.Len())
		{
			FLinearColor Caret = Palette::Glow;
			Caret.A *= Pulse;
			Line(Slot + FVector2D(-2.f * U, 2.8f * U), Slot + FVector2D(2.f * U, 2.8f * U), Caret, 0.4f * U);
		}
	}

	// Phone-style grid: 1-9, then delete / 0 / go.
	const float Step = 13.f * U;
	const float Radius = 5.2f * U;
	for (int32 Digit = 1; Digit <= 9; ++Digit)
	{
		const int32 Row = (Digit - 1) / 3;
		const int32 Column = (Digit - 1) % 3;
		RoundButton(EGolfHudButton::KeypadDigit, FVector2D(Center.X + (Column - 1) * Step, Center.Y - 11.f * U + Row * Step), Radius,
			FString::FromInt(Digit), Palette::PanelSolid, Digit);
	}
	const float LastRow = Center.Y - 11.f * U + 3.f * Step;
	RoundButton(EGolfHudButton::KeypadDelete, FVector2D(Center.X - Step, LastRow), Radius, TEXT("DEL"), Palette::PanelSolid);
	RoundButton(EGolfHudButton::KeypadDigit, FVector2D(Center.X, LastRow), Radius, TEXT("0"), Palette::PanelSolid, 0);
	RoundButton(EGolfHudButton::KeypadGo, FVector2D(Center.X + Step, LastRow), Radius, TEXT("GO"),
		Code.Len() == 4 ? Palette::Accept : Palette::PanelSolid);
	RoundButton(EGolfHudButton::KeypadCancel, FVector2D(Center.X + 29.f * U, Center.Y - 39.f * U), 3.f * U, TEXT("X"), Palette::PanelSolid);
}

void AGolfHUD::DrawFriends()
{
	const UGolfSessionSubsystem* Sessions = GetGameInstance()->GetSubsystem<UGolfSessionSubsystem>();
	if (!Sessions)
	{
		return;
	}
	const float Left = Canvas->ClipX * 0.62f;
	const float Width = Canvas->ClipX * 0.35f;
	Box(FVector2D(Left, 12.f * U), FVector2D(Width, 76.f * U), Palette::Panel);
	Heading(TEXT("Invite Friends"), FVector2D(Left + 2.5f * U, 14.5f * U), Width - 5.f * U, 2.4f);

	const TArray<FGolfFriend>& Friends = Sessions->GetFriends();
	if (Friends.Num() == 0)
	{
		Label(TEXT("NO FRIENDS FOUND YET"), FVector2D(Left + Width * 0.5f, 40.f * U), 2.4f, Palette::Dim, true);
		return;
	}
	float Y = 22.f * U;
	for (int32 Index = 0; Index < Friends.Num() && Index < 8; ++Index)
	{
		const FGolfFriend& Friend = Friends[Index];
		const FVector2D Dot(Left + 3.5f * U, Y + 2.f * U);
		Ring(Dot, 0.9f * U, Friend.bOnline ? Palette::Under : Palette::Hairline, 0.18f * U);
		if (Friend.bOnline)
		{
			Disc(Dot, 0.5f * U, Palette::Under);
		}
		Label(Friend.Name.Left(16).ToUpper(), FVector2D(Left + 6.f * U, Y + 0.4f * U), 2.4f, Friend.bOnline ? Palette::White : Palette::Dim, false);
		Line(FVector2D(Left + 2.5f * U, Y + 5.2f * U), FVector2D(Left + Width - 10.f * U, Y + 5.2f * U), Palette::Hairline, 0.1f * U);
		RoundButton(EGolfHudButton::Friend, FVector2D(Left + Width - 5.f * U, Y + 2.f * U), 2.8f * U, TEXT("+"), Palette::PanelSolid, Index);
		Y += 7.5f * U;
	}
}

void AGolfHUD::DrawInvitePopup()
{
	const UGolfSessionSubsystem* Sessions = GetGameInstance()->GetSubsystem<UGolfSessionSubsystem>();
	if (!Sessions || !Sessions->HasPendingInvite())
	{
		return;
	}
	const FVector2D Center(Canvas->ClipX * 0.5f, Canvas->ClipY * 0.5f);
	Box(Center - FVector2D(40.f * U, 17.f * U), FVector2D(80.f * U, 34.f * U), Palette::PanelSolid);
	Heading(TEXT("Incoming Invite"), Center - FVector2D(0.f, 15.f * U), 50.f * U, 1.9f, true);
	Label(FString::Printf(TEXT("%s invited you to play"), *Sessions->GetPendingInviteFrom()), Center - FVector2D(0.f, 7.f * U), 3.4f, Palette::White, true);
	RoundButton(EGolfHudButton::AcceptInvite, Center + FVector2D(-12.f * U, 6.f * U), 6.f * U, TEXT("JOIN"), Palette::Accept);
	RoundButton(EGolfHudButton::DeclineInvite, Center + FVector2D(12.f * U, 6.f * U), 6.f * U, TEXT("LATER"), Palette::Panel);
}

void AGolfHUD::DrawPlaying(AGolfGameState* State, AGolfPlayerController* Controller)
{
	if (Controller->IsMyTurn())
	{
		DrawGreenGrid(Controller);
		DrawPreview(Controller);
	}
	DrawPinMarker(State);
	DrawHoleCard(State);
	DrawMiniMap(State, Controller);
	DrawPlayers(State);
	DrawWind(State);

	if (const AGolfPlayerState* Active = Cast<AGolfPlayerState>(State->ActivePlayer); Active && Active->Ball)
	{
		const FVector2D LiePos(Canvas->ClipX - 11.f * U, 27.5f * U);
		Box(LiePos - FVector2D(8.f * U, 1.8f * U), FVector2D(16.f * U, 3.6f * U), Palette::Panel);
		Label(GolfPhysics::LieName(Active->Ball->GetLie()).ToUpper(), LiePos, 2.2f, Palette::Gold, true);
	}

	if (Controller->IsMyTurn())
	{
		DrawClubDisc(Controller);
		DrawPowerMeter(Controller);
		DrawLandingView(State, Controller);
	}
	DrawMoving(Controller);
}

void AGolfHUD::DrawMoving(AGolfPlayerController* Controller)
{
	if (Controller->IsDriving())
	{
		DrawDriving(Controller);
	}
	else if (Controller->IsWalking())
	{
		DrawWalking(Controller);
	}
}

void AGolfHUD::DrawLandingView(AGolfGameState* State, AGolfPlayerController* Controller)
{
	UTextureRenderTarget2D* Picture = Controller->GetLandingViewTexture();
	if (!Picture || !Picture->GetResource())
	{
		return;
	}
	// Window at the top middle, 16:9.
	const float GapLeft = 47.f * U, GapRight = Canvas->ClipX - 24.f * U;
	const float Width = FMath::Clamp(GapRight - GapLeft, 30.f * U, 34.f * U * 16.f / 9.f);
	const FVector2D Size(Width, Width * 9.f / 16.f);
	const FVector2D Pos(FMath::Max(GapLeft, (GapLeft + GapRight - Width) * 0.5f), 2.f * U);
	const FVector2D Center = Pos + Size * 0.5f;
	Box(Pos - FVector2D(0.4f * U, 0.4f * U), Size + FVector2D(0.8f * U, 0.8f * U), Palette::PanelSolid);
	FCanvasTileItem Tile(Pos, Picture->GetResource(), Size, FLinearColor::White);
	Tile.BlendMode = SE_BLEND_Opaque;
	Canvas->DrawItem(Tile);

	// Map ground offsets from the landing spot into the window (camera looks straight down, shot goes up).
	using PC = AGolfPlayerController;
	const float PixelsPerCm = (Size.X * 0.5f) / (Controller->GetLandingViewHeight() * FMath::Tan(FMath::DegreesToRadians(PC::LandingViewFOV * 0.5f)));
	const FRotator Aim(0.f, Controller->GetAimYaw(), 0.f);
	const FVector Forward = Aim.Vector();
	const FVector Right = FRotationMatrix(Aim).GetUnitAxis(EAxis::Y);
	const FVector ViewCenter = Controller->GetLandingViewCenter();
	auto ToWindow = [&](const FVector& World, FVector2D& Out)
	{
		const FVector Offset = World - ViewCenter;
		Out = Center + FVector2D(FVector::DotProduct(Offset, Right), -FVector::DotProduct(Offset, Forward)) * PixelsPerCm;
		return Out.X > Pos.X && Out.X < Pos.X + Size.X && Out.Y > Pos.Y && Out.Y < Pos.Y + Size.Y;
	};

	// Landing ring (moves as you aim and swipe), and the pin.
	FVector2D LandingSpot;
	ToWindow(Controller->GetPreviewLanding(), LandingSpot);
	Ring(LandingSpot, FMath::Max(250.f * PixelsPerCm, 1.2f * U), Controller->IsSwinging() ? Palette::Target : Palette::TargetIdle, 0.35f * U);
	if (State->CurrentHole)
	{
		FVector2D Pin;
		if (ToWindow(State->CurrentHole->GetCupLocation(), Pin))
		{
			const FLinearColor Yellow(1.f, 0.85f, 0.f, 1.f);
			Line(Pin, Pin - FVector2D(0.f, 3.f * U), FLinearColor::White, 0.25f * U);
			for (int32 Stroke = 0; Stroke <= 6; ++Stroke)
			{
				Line(Pin - FVector2D(0.f, 3.f * U - Stroke * 0.2f * U), Pin + FVector2D(2.f * U, -2.4f * U), Yellow, 0.3f * U);
			}
			Ring(Pin, 0.6f * U, Yellow, 0.25f * U);
		}
	}
	Box(Pos, FVector2D(14.f * U, 3.2f * U), Palette::PanelSolid);
	Label(TEXT("L A N D I N G"), Pos + FVector2D(7.f * U, 1.6f * U), 1.7f, Palette::White, true);
	Line(Pos + FVector2D(0.f, Size.Y), Pos + Size, Palette::Glow, 0.3f * U);
}

void AGolfHUD::DrawMiniMap(AGolfGameState* State, AGolfPlayerController* Controller)
{
	UTextureRenderTarget2D* Picture = Controller->GetMiniMapTexture();
	if (!Picture || !Picture->GetResource() || !State->CurrentHole)
	{
		return;
	}
	// Left edge, between the players list and the club disc: the whole hole, tee at the bottom.
	int32 Rows = 0;
	for (APlayerState* Base : State->PlayerArray)
	{
		const AGolfPlayerState* Player = Cast<AGolfPlayerState>(Base);
		Rows += Player && Player->bInRound ? 1 : 0;
	}
	const float Top = (20.f + 5.f * Rows) * U;
	const float Aspect = static_cast<float>(Picture->SizeX) / FMath::Max(1, Picture->SizeY);
	float Height = FMath::Max(16.f * U, Canvas->ClipY - 26.f * U - Top);
	if (Height * Aspect > 34.f * U)
	{
		Height = 34.f * U / Aspect;
	}
	const FVector2D Size(Height * Aspect, Height);
	const FVector2D Pos(2.f * U, Top);
	const FVector2D Center = Pos + Size * 0.5f;
	Box(Pos - FVector2D(0.4f * U, 0.4f * U), Size + FVector2D(0.8f * U, 0.8f * U), Palette::PanelSolid);
	FCanvasTileItem Tile(Pos, Picture->GetResource(), Size, FLinearColor::White);
	Tile.BlendMode = SE_BLEND_Opaque;
	Canvas->DrawItem(Tile);

	Box(Pos, FVector2D(FMath::Min(Size.X, 14.f * U), 3.2f * U), Palette::PanelSolid);
	Label(TEXT("H O L E  M A P"), Pos + FVector2D(FMath::Min(Size.X, 14.f * U) * 0.5f, 1.6f * U), 1.7f, Palette::White, true);

	const float PixelsPerCm = Size.X / Controller->GetMiniMapWidth();
	const FRotator Up(0.f, Controller->GetMiniMapYaw(), 0.f);
	const FVector Forward = Up.Vector();
	const FVector Right = FRotationMatrix(Up).GetUnitAxis(EAxis::Y);
	const FVector MapCenter = Controller->GetMiniMapCenter();
	auto ToMap = [&](const FVector& World)
	{
		const FVector Offset = World - MapCenter;
		FVector2D Out = Center + FVector2D(FVector::DotProduct(Offset, Right), -FVector::DotProduct(Offset, Forward)) * PixelsPerCm;
		Out.X = FMath::Clamp(Out.X, Pos.X, Pos.X + Size.X);
		Out.Y = FMath::Clamp(Out.Y, Pos.Y, Pos.Y + Size.Y);
		return Out;
	};

	// Pin.
	const FVector2D Pin = ToMap(State->CurrentHole->GetCupLocation());
	const FLinearColor Yellow(1.f, 0.85f, 0.f, 1.f);
	Line(Pin, Pin - FVector2D(0.f, 2.4f * U), FLinearColor::White, 0.2f * U);
	for (int32 Stroke = 0; Stroke <= 5; ++Stroke)
	{
		Line(Pin - FVector2D(0.f, 2.4f * U - Stroke * 0.16f * U), Pin + FVector2D(1.6f * U, -1.9f * U), Yellow, 0.25f * U);
	}

	// Every ball in play; the active player's shot setup (flight line and landing ring) on top.
	for (APlayerState* Base : State->PlayerArray)
	{
		const AGolfPlayerState* Player = Cast<AGolfPlayerState>(Base);
		if (Player && Player->Ball && Player->bInRound && !Player->bHoledOut && !Player->Ball->IsHidden())
		{
			const bool bActive = State->ActivePlayer == Player;
			const FVector2D Spot = ToMap(Player->Ball->GetActorLocation());
			Disc(Spot, (bActive ? 0.7f : 0.5f) * U, bActive ? Palette::White : Palette::Dim);
			Ring(Spot, (bActive ? 1.3f : 0.9f) * U, bActive ? Palette::Glow : Palette::Hairline, 0.15f * U);
		}
	}
	if (Controller->IsMyTurn() && Controller->HasPreview() && !Controller->IsPutting())
	{
		const TArray<FVector>& Path = Controller->GetPreviewPath();
		for (int32 Index = 1; Index < Path.Num(); ++Index)
		{
			Line(ToMap(Path[Index - 1]), ToMap(Path[Index]), FLinearColor(1.f, 1.f, 1.f, 0.8f), 0.2f * U);
		}
		Ring(ToMap(Controller->GetPreviewLanding()), FMath::Max(1500.f * PixelsPerCm, 0.9f * U),
			Controller->IsSwinging() ? Palette::Target : Palette::TargetIdle, 0.3f * U);
	}
}

void AGolfHUD::DrawPinMarker(AGolfGameState* State)
{
	// A fixed-size flag over the cup so the target stays readable from any distance.
	const AGolfHole* Hole = State->CurrentHole;
	if (!Hole)
	{
		return;
	}
	const FVector Cup = Hole->GetCupLocation();
	FVector2D Base, Top;
	if (!ToScreen(Cup, Base) || !ToScreen(Cup + FVector(0.f, 0.f, 213.f), Top))
	{
		return;
	}

	// Keep the marker at least a readable height even when the real flag is a few pixels tall.
	const float MinHeight = 7.f * U;
	if (Base.Y - Top.Y < MinHeight)
	{
		Top = Base - FVector2D(0.f, MinHeight);
	}
	const float PoleHeight = Base.Y - Top.Y;
	const FLinearColor Yellow(1.f, 0.85f, 0.f, 1.f);
	const FLinearColor Outline(0.f, 0.f, 0.f, 0.75f);

	// Pole with a dark outline so it reads on grass and sky alike.
	Line(Base, Top, Outline, 0.7f * U);
	Line(Base, Top, FLinearColor::White, 0.35f * U);

	// Pennant: filled with stacked lines between the pole and the tip.
	const float FlagHeight = FMath::Min(PoleHeight * 0.4f, 3.5f * U);
	const float FlagLength = FlagHeight * 1.5f;
	const FVector2D Tip = Top + FVector2D(FlagLength, FlagHeight * 0.5f);
	constexpr int32 Strokes = 10;
	for (int32 Index = 0; Index <= Strokes; ++Index)
	{
		const FVector2D OnPole = Top + FVector2D(0.f, FlagHeight * Index / Strokes);
		Line(OnPole, Tip, Yellow, FMath::Max(1.f, FlagHeight / Strokes + 1.f));
	}
	Line(Top, Tip, Outline, 0.2f * U);
	Line(Top + FVector2D(0.f, FlagHeight), Tip, Outline, 0.2f * U);

	// Cup ring and distance from the active ball.
	Ring(Base, 0.9f * U, Yellow, 0.3f * U);
	if (const AGolfPlayerState* Active = Cast<AGolfPlayerState>(State->ActivePlayer); Active && Active->Ball)
	{
		const float Meters = FVector::Dist2D(Active->Ball->GetRestLocation(), Cup) / 100.f;
		const FString Distance = Meters < 1.f ? FString::Printf(TEXT("%.0f cm"), Meters * 100.f)
			: (Meters < 10.f ? FString::Printf(TEXT("%.1f m"), Meters) : FString::Printf(TEXT("%.0f m"), Meters));
		const FVector2D Tag = Top - FVector2D(0.f, 2.6f * U);
		Box(Tag - FVector2D(5.f * U, 1.6f * U), FVector2D(10.f * U, 3.2f * U), Palette::Panel);
		Line(Tag - FVector2D(5.f * U, 1.6f * U), Tag + FVector2D(-5.f * U, 1.6f * U), Yellow, 0.4f * U);
		Label(Distance, Tag, 2.2f, Palette::White, true);
	}
}

void AGolfHUD::DrawBallCompass(AGolfPlayerController* Controller, const AActor* From)
{
	const AGolfBall* Ball = Controller->GetMyBall();
	if (!From || !Ball || !Controller->IsTravelling())
	{
		return;
	}
	// Direction and distance to the ball, top centre. Screen-up is where the camera looks.
	const FVector2D Compass(Canvas->ClipX * 0.5f, 9.f * U);
	Disc(Compass, 6.f * U, Palette::Panel);
	Ring(Compass, 6.f * U, Palette::Trim, 0.15f * U);
	for (int32 Tick = 0; Tick < 12; ++Tick)
	{
		const FVector2D TickDir(FMath::Cos(Tick * PI / 6.f), FMath::Sin(Tick * PI / 6.f));
		Line(Compass + TickDir * 5.2f * U, Compass + TickDir * 5.9f * U, Palette::Hairline, 0.15f * U);
	}
	Arc(Compass, 6.8f * U, -120.f, 60.f, Palette::Glow, 0.35f * U);
	const FVector ToBall = Ball->GetRestLocation() - From->GetActorLocation();
	const float CameraYaw = PlayerOwner->PlayerCameraManager ? PlayerOwner->PlayerCameraManager->GetCameraRotation().Yaw : From->GetActorRotation().Yaw;
	const float Bearing = FMath::DegreesToRadians(ToBall.Rotation().Yaw - CameraYaw);
	const FVector2D Dir(FMath::Sin(Bearing), -FMath::Cos(Bearing));
	const FVector2D Side(-Dir.Y, Dir.X);
	const FVector2D Tip = Compass + Dir * 4.5f * U;
	Line(Compass - Dir * 3.f * U, Tip, Palette::Glow, 0.5f * U);
	Line(Tip, Tip - Dir * 1.8f * U + Side * 1.4f * U, Palette::Glow, 0.5f * U);
	Line(Tip, Tip - Dir * 1.8f * U - Side * 1.4f * U, Palette::Glow, 0.5f * U);
	Label(TEXT("BALL"), Compass + FVector2D(0.f, 7.9f * U), 1.8f, Palette::Dim, true);
	Label(FString::Printf(TEXT("%.0f m"), Controller->GetDistanceToBall()), Compass + FVector2D(0.f, 10.4f * U), 2.8f, Palette::White, true);

	// Marker over the ball when it is in view.
	FVector2D BallScreen;
	if (ToScreen(Ball->GetRestLocation() + FVector(0.f, 0.f, 120.f), BallScreen))
	{
		Ring(BallScreen, 1.4f * U, Palette::Glow, 0.3f * U);
		Line(BallScreen + FVector2D(0.f, 1.4f * U), BallScreen + FVector2D(0.f, 4.f * U), Palette::Glow, 0.25f * U);
	}

	RoundButton(EGolfHudButton::SkipDrive, FVector2D(Canvas->ClipX - 11.f * U, 47.f * U), 4.5f * U, TEXT("SKIP"), Palette::PanelSolid);
	if (Controller->CanPlayShot())
	{
		RoundButton(EGolfHudButton::PlayShot, FVector2D(Canvas->ClipX * 0.5f, Canvas->ClipY - 14.f * U), 9.f * U, TEXT("PLAY SHOT"), Palette::Accept);
	}
	else
	{
		Label(TEXT("GET WITHIN 15 M OF YOUR BALL"), FVector2D(Canvas->ClipX * 0.5f, Canvas->ClipY - 5.f * U), 2.2f, Palette::Dim, true);
	}
}

void AGolfHUD::DrawDriving(AGolfPlayerController* Controller)
{
	const AGolfBuggy* Buggy = Controller->GetMyBuggy();
	if (!Buggy)
	{
		return;
	}
	DrawBallCompass(Controller, Buggy);

	// Steering track on the left: a ticked glass rail, the knob follows the thumb.
	const FVector2D Pad(18.f * U, Canvas->ClipY - 18.f * U);
	Box(Pad - FVector2D(12.f * U, 1.f * U), FVector2D(24.f * U, 2.f * U), Palette::Panel);
	Line(Pad - FVector2D(12.f * U, 1.f * U), Pad + FVector2D(12.f * U, -1.f * U), Palette::Hairline, 0.12f * U);
	Line(Pad - FVector2D(12.f * U, -1.f * U), Pad + FVector2D(12.f * U, 1.f * U), Palette::Hairline, 0.12f * U);
	for (int32 Tick = -4; Tick <= 4; ++Tick)
	{
		const float X = Pad.X + Tick * 2.75f * U;
		Line(FVector2D(X, Pad.Y - (Tick == 0 ? 2.2f : 1.6f) * U), FVector2D(X, Pad.Y - 1.1f * U), Tick == 0 ? Palette::Trim : Palette::Hairline, 0.15f * U);
	}
	const FVector2D Knob = Pad + FVector2D(Controller->GetDriveSteer() * 11.f * U, 0.f);
	Disc(Knob, 3.f * U, FLinearColor(0.55f, 0.88f, 1.f, 0.3f));
	Ring(Knob, 3.f * U, Palette::Trim, 0.2f * U);
	Disc(Knob, 0.8f * U, Palette::White);
	Label(TEXT("DRAG TO STEER"), Pad + FVector2D(0.f, 6.f * U), 1.9f, Palette::Dim, true);

	// Pedals on the right, and the door.
	const FVector2D Go(Canvas->ClipX - 14.f * U, Canvas->ClipY - 16.f * U);
	RoundButton(EGolfHudButton::Throttle, Go, 10.f * U, TEXT("GO"), Palette::Accept);
	RoundButton(EGolfHudButton::Reverse, FVector2D(Canvas->ClipX - 33.f * U, Canvas->ClipY - 10.f * U), 6.f * U, TEXT("REV"), Palette::PanelSolid);
	RoundButton(EGolfHudButton::Buggy, FVector2D(Canvas->ClipX - 11.f * U, 59.f * U), 4.5f * U, TEXT("GET OUT"), Palette::PanelSolid);

	// Speedo arc over the GO pedal.
	const float Kmh = FMath::Abs(Buggy->GetSpeed()) * 0.036f;
	Arc(Go, 13.f * U, 200.f, 140.f, Palette::Hairline, 0.2f * U);
	Arc(Go, 13.f * U, 200.f, 140.f * FMath::Clamp(Kmh / 30.f, 0.f, 1.f), Palette::Glow, 0.5f * U);
	Label(FString::Printf(TEXT("%.0f KM/H"), Kmh), Go - FVector2D(0.f, 15.5f * U), 2.4f, Palette::White, true);
}

void AGolfHUD::DrawWalking(AGolfPlayerController* Controller)
{
	DrawBallCompass(Controller, Controller->GetPawn());

	// Thumb stick on the left: glass ring with ticks and a glowing arc toward the push, the knob follows the thumb.
	const FVector2D Pad(18.f * U, Canvas->ClipY - 18.f * U);
	Disc(Pad, 9.f * U, Palette::Panel);
	Ring(Pad, 9.f * U, Palette::Trim, 0.18f * U);
	Ring(Pad, 5.f * U, Palette::Hairline, 0.1f * U);
	for (int32 Tick = 0; Tick < 8; ++Tick)
	{
		const FVector2D Dir(FMath::Cos(Tick * PI / 4.f), FMath::Sin(Tick * PI / 4.f));
		Line(Pad + Dir * 8.f * U, Pad + Dir * 8.9f * U, Palette::Hairline, 0.15f * U);
	}
	const FVector2D Stick = Controller->GetWalkStick();
	const FVector2D Offset(Stick.X, -Stick.Y);
	if (Offset.SizeSquared() > 0.01f)
	{
		const float Push = FMath::RadiansToDegrees(FMath::Atan2(Offset.Y, Offset.X));
		Arc(Pad, 10.f * U, Push - 25.f, 50.f, Palette::Glow, 0.45f * U);
	}
	const FVector2D Knob = Pad + Offset * 7.f * U;
	Disc(Knob, 3.f * U, FLinearColor(0.55f, 0.88f, 1.f, 0.3f));
	Ring(Knob, 3.f * U, Palette::Trim, 0.2f * U);
	Disc(Knob, 0.8f * U, Palette::White);
	Label(TEXT("DRAG TO WALK"), Pad + FVector2D(0.f, 12.f * U), 1.9f, Palette::Dim, true);

	if (Controller->CanTeeUp())
	{
		RoundButton(EGolfHudButton::Start, FVector2D(Canvas->ClipX - 16.f * U, Canvas->ClipY - 16.f * U), 8.f * U, TEXT("TEE UP"), Palette::Accept);
		Label(TEXT("[ E ]"), FVector2D(Canvas->ClipX - 16.f * U, Canvas->ClipY - 5.f * U), 2.f, Palette::Dim, true);
	}
	else if (Controller->GetBuggyInReach())
	{
		RoundButton(EGolfHudButton::Buggy, FVector2D(Canvas->ClipX - 16.f * U, Canvas->ClipY - 16.f * U), 8.f * U, TEXT("GET IN"), Palette::Accept);
		Label(TEXT("[ E ]"), FVector2D(Canvas->ClipX - 16.f * U, Canvas->ClipY - 5.f * U), 2.f, Palette::Dim, true);
	}
}

void AGolfHUD::DrawHoleCard(AGolfGameState* State)
{
	const AGolfHole* Hole = State->CurrentHole;
	if (!Hole)
	{
		return;
	}
	const FVector2D Pos(2.f * U, 2.f * U);
	Box(Pos, FVector2D(42.f * U, 15.f * U), Palette::Panel);

	// Round progress gauge with the hole number inside.
	const FVector2D Gauge(Pos.X + 7.5f * U, Pos.Y + 7.5f * U);
	const int32 Holes = FMath::Max(1, State->Pars.Num());
	Ring(Gauge, 5.8f * U, Palette::Hairline, 0.15f * U);
	Arc(Gauge, 5.8f * U, -90.f, 360.f * (State->HoleIndex + 1) / Holes, Palette::Glow, 0.45f * U);
	Label(FString::Printf(TEXT("%d"), State->HoleIndex + 1), Gauge, 6.f, Palette::White, true);

	Label(FString::Printf(TEXT("HOLE %d / %d"), State->HoleIndex + 1, Holes), FVector2D(Pos.X + 15.f * U, Pos.Y + 1.2f * U), 2.f, Palette::Dim, false);
	Label(Hole->HoleName.ToUpper(), FVector2D(Pos.X + 15.f * U, Pos.Y + 3.8f * U), 3.6f, Palette::White, false);
	Line(FVector2D(Pos.X + 15.f * U, Pos.Y + 8.6f * U), FVector2D(Pos.X + 40.f * U, Pos.Y + 8.6f * U), Palette::Hairline, 0.12f * U);
	Label(FString::Printf(TEXT("PAR %d"), Hole->Par), FVector2D(Pos.X + 15.f * U, Pos.Y + 9.8f * U), 3.f, Palette::Gold, false);

	if (const AGolfPlayerState* Active = Cast<AGolfPlayerState>(State->ActivePlayer); Active && Active->Ball)
	{
		const float Meters = FVector::Dist2D(Active->Ball->GetRestLocation(), Hole->GetCupLocation()) / 100.f;
		const FString PinDistance = Meters < 1.f
			? FString::Printf(TEXT("PIN %.0f cm"), Meters * 100.f)
			: (Meters < 10.f ? FString::Printf(TEXT("PIN %.1f m"), Meters) : FString::Printf(TEXT("PIN %.0f m"), Meters));
		Label(PinDistance, FVector2D(Pos.X + 26.f * U, Pos.Y + 9.8f * U), 3.f, Palette::Dim, false);
	}
}

void AGolfHUD::DrawPlayers(AGolfGameState* State)
{
	float Y = 19.f * U;
	for (APlayerState* Base : State->PlayerArray)
	{
		const AGolfPlayerState* Player = Cast<AGolfPlayerState>(Base);
		if (!Player || !Player->bInRound)
		{
			continue;
		}
		const bool bActive = State->ActivePlayer == Player;
		FCanvasTileItem Row(FVector2D(2.f * U, Y), FVector2D(42.f * U, 4.4f * U), bActive ? FLinearColor(0.06f, 0.3f, 0.6f, 0.55f) : Palette::Panel);
		Row.BlendMode = SE_BLEND_Translucent;
		Canvas->DrawItem(Row);
		// Accent bar on the left: bright for the player whose turn it is.
		Line(FVector2D(2.f * U, Y), FVector2D(2.f * U, Y + 4.4f * U), bActive ? Palette::Glow : Palette::Hairline, bActive ? 0.6f * U : 0.2f * U);
		Line(FVector2D(2.f * U, Y + 4.4f * U), FVector2D(44.f * U, Y + 4.4f * U), Palette::Hairline, 0.1f * U);

		const int32 ToPar = Player->GetToPar(State->Pars);
		const FString ToParText = ToPar == 0 ? TEXT("E") : FString::Printf(TEXT("%+d"), ToPar);
		Label(Player->GetPlayerName().Left(12).ToUpper(), FVector2D(4.f * U, Y + 0.7f * U), 2.8f, Palette::White, false);
		Label(Player->bHoledOut ? TEXT("IN") : FString::Printf(TEXT("%d"), Player->Strokes), FVector2D(32.f * U, Y + 0.7f * U), 2.8f, Palette::Gold, false);
		Label(ToParText, FVector2D(38.5f * U, Y + 0.7f * U), 2.8f, ToPar < 0 ? Palette::Under : ToPar > 0 ? Palette::Over : Palette::White, false);
		Y += 5.f * U;
	}
}

void AGolfHUD::DrawWind(AGolfGameState* State)
{
	const FVector2D Center(Canvas->ClipX - 11.f * U, 10.f * U);
	const float Radius = 7.f * U;
	Disc(Center, Radius, Palette::Panel);
	Ring(Center, Radius, Palette::Trim, 0.15f * U);
	Ring(Center, Radius * 0.62f, Palette::Hairline, 0.1f * U);
	for (int32 Tick = 0; Tick < 12; ++Tick)
	{
		const FVector2D Dir(FMath::Cos(Tick * PI / 6.f), FMath::Sin(Tick * PI / 6.f));
		const float Inner = Tick % 3 == 0 ? 0.78f : 0.88f;
		Line(Center + Dir * Radius * Inner, Center + Dir * Radius * 0.98f, Tick % 3 == 0 ? Palette::Trim : Palette::Hairline, 0.15f * U);
	}

	const float Speed = State->Wind.Size2D() / 100.f;
	// Strength arc round the outside (full circle at 10 m/s).
	Arc(Center, Radius * 1.14f, -90.f, 360.f * FMath::Clamp(Speed / 10.f, 0.f, 1.f), Palette::Glow, 0.35f * U);
	if (Speed > 0.05f && PlayerOwner && PlayerOwner->PlayerCameraManager)
	{
		// Screen-up is the camera's forward direction.
		const float Relative = FMath::DegreesToRadians(State->Wind.Rotation().Yaw - PlayerOwner->PlayerCameraManager->GetCameraRotation().Yaw);
		const FVector2D Dir(FMath::Sin(Relative), -FMath::Cos(Relative));
		const FVector2D Tip = Center + Dir * Radius * 0.72f;
		const FVector2D Tail = Center - Dir * Radius * 0.5f;
		const FVector2D Side(-Dir.Y, Dir.X);
		Line(Tail, Tip, Palette::White, 0.45f * U);
		Line(Tip, Tip - Dir * 2.f * U + Side * 1.4f * U, Palette::White, 0.45f * U);
		Line(Tip, Tip - Dir * 2.f * U - Side * 1.4f * U, Palette::White, 0.45f * U);
	}
	Label(TEXT("WIND"), Center + FVector2D(0.f, Radius + 2.f * U), 1.8f, Palette::Dim, true);
	Label(FString::Printf(TEXT("%.1f m/s"), Speed), Center + FVector2D(0.f, Radius + 4.3f * U), 2.6f, Palette::Gold, true);
}

void AGolfHUD::DrawGreenGrid(AGolfPlayerController* Controller)
{
	// The arrows point downhill. Their length and colour communicate the strength of the break.
	const TArray<FVector>& Points = Controller->GetGreenGridPoints();
	const TArray<FVector>& Slopes = Controller->GetGreenGridSlopes();
	if (Points.Num() > 0)
	{
		Box(FVector2D(Canvas->ClipX * 0.5f - 15.f * U, 2.f * U), FVector2D(30.f * U, 4.f * U), Palette::Panel);
		Line(FVector2D(Canvas->ClipX * 0.5f - 15.f * U, 2.f * U), FVector2D(Canvas->ClipX * 0.5f - 15.f * U, 6.f * U), Palette::Target, 0.6f * U);
		Label(TEXT("BREAK GUIDE  ·  ARROWS POINT DOWNHILL"), FVector2D(Canvas->ClipX * 0.5f, 4.f * U), 1.9f, Palette::White, true);
	}
	for (int32 Index = 0; Index < Points.Num() && Index < Slopes.Num(); ++Index)
	{
		const float Percent = Slopes[Index].Size() * 100.f;
		if (Percent < 0.6f)
		{
			continue;
		}
		const FLinearColor Color = Percent < 2.f ? FLinearColor(1.f, 0.35f, 0.3f, 0.8f) : Palette::Target;

		FVector2D From;
		if (!ToScreen(Points[Index] + FVector(0.f, 0.f, 1.f), From))
		{
			continue;
		}
		const FVector Tip = Points[Index] + Slopes[Index].GetSafeNormal() * FMath::Clamp(Percent * 20.f, 30.f, 90.f) + FVector(0.f, 0.f, 1.f);
		FVector2D To;
		if (ToScreen(Tip, To))
		{
			Line(From, To, Color, 0.35f * U);
			const FVector2D Direction = (To - From).GetSafeNormal();
			if (!Direction.IsNearlyZero())
			{
				const FVector2D Side(-Direction.Y, Direction.X);
				const float HeadLength = 1.1f * U;
				Line(To, To - Direction * HeadLength + Side * (0.65f * U), Color, 0.35f * U);
				Line(To, To - Direction * HeadLength - Side * (0.65f * U), Color, 0.35f * U);
			}
		}
	}
}

void AGolfHUD::DrawPreview(AGolfPlayerController* Controller)
{
	if (!Controller->HasPreview())
	{
		return;
	}
	const TArray<FVector>& Path = Controller->GetPreviewPath();
	const FVector Landing = Controller->GetPreviewLanding();
	const bool bPutt = Controller->IsPutting();

	if (bPutt)
	{
		// Solid aim line laid over the green, so you can line up the putt.
		FVector2D Previous;
		bool bHavePrevious = false;
		for (const FVector& Point : Path)
		{
			FVector2D Screen;
			const bool bOnScreen = ToScreen(Point + FVector(0.f, 0.f, 0.5f), Screen);
			if (bOnScreen && bHavePrevious)
			{
				Line(Previous, Screen, FLinearColor(1.f, 1.f, 1.f, 0.9f), 0.35f * U);
			}
			Previous = Screen;
			bHavePrevious = bOnScreen;
		}
	}
	else
	{
		for (const FVector& Point : Path)
		{
			FVector2D Screen;
			if (ToScreen(Point, Screen))
			{
				Disc(Screen, 0.35f * U, FLinearColor(1.f, 1.f, 1.f, 0.7f));
			}
		}
	}

	// Target ring on the ground where the ball lands (or stops, for a putt).
	const float RingRadius = bPutt ? 30.f : 250.f;
	FVector2D Previous;
	bool bHavePrevious = false;
	for (int32 Index = 0; Index <= 32; ++Index)
	{
		const float Angle = 2.f * PI * Index / 32.f;
		FVector2D Screen;
		const bool bOnScreen = ToScreen(Landing + FVector(FMath::Cos(Angle), FMath::Sin(Angle), 0.f) * RingRadius + FVector(0.f, 0.f, 1.f), Screen);
		if (bOnScreen && bHavePrevious)
		{
			Line(Previous, Screen, Controller->IsSwinging() ? Palette::Target : Palette::TargetIdle, 0.45f * U);
		}
		Previous = Screen;
		bHavePrevious = bOnScreen;
	}

	const float Meters = FVector::Dist2D(Path.Num() > 0 ? Path[0] : Landing, Landing) / 100.f;
	FVector2D LabelPos;
	if (ToScreen(Landing + FVector(0.f, 0.f, bPutt ? 40.f : 300.f), LabelPos))
	{
		Label(bPutt ? FString::Printf(TEXT("%.1f m"), Meters) : FString::Printf(TEXT("%.0f m"), Meters), LabelPos, 3.f, Palette::White, true);
	}
}

void AGolfHUD::DrawClubDisc(AGolfPlayerController* Controller)
{
	const TArray<FGolfClub>& Bag = GolfPhysics::GetClubBag();
	const int32 Index = Controller->GetClubIndex();
	if (!Bag.IsValidIndex(Index))
	{
		return;
	}
	const FVector2D Center(12.5f * U, Canvas->ClipY - 12.5f * U);
	const float Radius = 9.5f * U;
	Disc(Center, Radius, Palette::Panel);
	Ring(Center, Radius, Palette::Trim, 0.18f * U);
	// Dashed inner ring and a carry gauge: how far this club goes against the longest in the bag.
	for (int32 Dash = 0; Dash < 24; Dash += 2)
	{
		Arc(Center, Radius * 0.8f, Dash * 15.f, 9.f, Palette::Hairline, 0.14f * U);
	}
	float Longest = 1.f;
	for (int32 Club = 0; Club < Bag.Num(); ++Club)
	{
		Longest = FMath::Max(Longest, Controller->GetClubCarry(Club));
	}
	Arc(Center, Radius * 1.1f, 135.f, 270.f, Palette::Hairline, 0.2f * U);
	Arc(Center, Radius * 1.1f, 135.f, 270.f * FMath::Clamp(Controller->GetClubCarry(Index) / Longest, 0.f, 1.f), Palette::Glow, 0.5f * U);
	Label(TEXT("CLUB"), Center - FVector2D(0.f, 5.6f * U), 1.6f, Palette::Dim, true);
	Label(Bag[Index].ShortName, Center - FVector2D(0.f, 1.2f * U), 6.f, Palette::White, true);
	Label(FString::Printf(TEXT("%.0f m"), Controller->GetClubCarry(Index) / 100.f), Center + FVector2D(0.f, 4.6f * U), 2.4f, Palette::Gold, true);
	Buttons.Add({ EGolfHudButton::Club, Center, Radius, 0 });

	RoundButton(EGolfHudButton::Spin, FVector2D(29.f * U, Canvas->ClipY - 6.5f * U), 4.5f * U, Controller->GetSpinLabel(), Palette::PanelSolid);
}

void AGolfHUD::DrawPowerMeter(AGolfPlayerController* Controller)
{
	using PC = AGolfPlayerController;

	// Segmented glass track on the right: segments light up as the finger travels up. The swipe itself can start
	// anywhere low on screen.
	const float Bottom = Canvas->ClipY - 8.f * U;
	const float Length = PC::FullPowerSwipe * Canvas->ClipY;
	const float CenterX = Canvas->ClipX - 9.f * U;
	const float Width = 2.6f * U;
	const float Power = Controller->GetSwingPower();

	Box(FVector2D(CenterX - Width * 0.5f - 0.5f * U, Bottom - Length - 0.5f * U), FVector2D(Width + U, Length + U), Palette::Panel);
	constexpr int32 Segments = 20;
	const float Gap = 0.25f * U;
	const float SegmentLength = (Length - Gap * (Segments - 1)) / Segments;
	for (int32 Segment = 0; Segment < Segments; ++Segment)
	{
		const float From = static_cast<float>(Segment) / Segments;
		const bool bLit = Power > From;
		const FLinearColor Colour = bLit ? FMath::Lerp(Palette::Glow, Palette::White, From) : FLinearColor(0.8f, 0.94f, 1.f, 0.08f);
		FCanvasTileItem Cell(FVector2D(CenterX - Width * 0.5f, Bottom - (Segment + 1) * SegmentLength - Segment * Gap), FVector2D(Width, SegmentLength), Colour);
		Cell.BlendMode = SE_BLEND_Translucent;
		Canvas->DrawItem(Cell);
	}
	for (const float Notch : { 0.25f, 0.5f, 0.75f, 1.f })
	{
		const float Y = Bottom - Length * Notch;
		Line(FVector2D(CenterX - Width * 1.1f, Y), FVector2D(CenterX - Width * 0.6f, Y), Palette::Trim, 0.15f * U);
		Label(FString::Printf(TEXT("%d"), FMath::RoundToInt(Notch * 100.f)), FVector2D(CenterX - Width * 2.1f, Y), 1.7f, Palette::Dim, true);
	}

	// Straightness: the marker slides left or right as the swipe drifts.
	const float Accuracy = Controller->GetSwingAccuracy();
	const FVector2D Straight(CenterX, Bottom + 3.f * U);
	Line(Straight - FVector2D(4.f * U, 0.f), Straight + FVector2D(4.f * U, 0.f), Palette::Hairline, 0.15f * U);
	Line(Straight - FVector2D(0.f, 0.8f * U), Straight + FVector2D(0.f, 0.8f * U), Palette::Trim, 0.15f * U);
	if (Controller->IsSwinging())
	{
		const FVector2D Marker = Straight + FVector2D(Accuracy * 4.f * U, 0.f);
		Ring(Marker, 0.8f * U, FMath::IsNearlyZero(Accuracy) ? Palette::Glow : Palette::Over, 0.25f * U);
	}

	const FString Text = Controller->IsSwinging() ? FString::Printf(TEXT("%d%%"), FMath::RoundToInt(Power * 100.f)) : TEXT("SWIPE UP");
	Label(Text, FVector2D(CenterX, Bottom - Length - 3.f * U), 2.6f, Palette::White, true);

	if (!Controller->IsSwinging())
	{
		Label(TEXT("SWIPE UP FROM THE BOTTOM TO SWING  ·  DRAG THE TOP TO AIM"), FVector2D(Canvas->ClipX * 0.5f, Canvas->ClipY - 4.f * U), 2.2f, Palette::Dim, true);
	}
	if (GetWorld()->GetTimeSeconds() - Controller->GetPerfectFlashTime() < 1.2f)
	{
		const FVector2D Flash(Canvas->ClipX * 0.5f, Canvas->ClipY * 0.42f);
		Arc(Flash, 9.f * U, 200.f, 140.f, Palette::Glow, 0.3f * U);
		Arc(Flash, 9.f * U, 20.f, 140.f, Palette::Glow, 0.3f * U);
		Label(TEXT("PURE STRIKE"), Flash, 5.f, Palette::White, true);
	}
}

void AGolfHUD::DrawScorecard(AGolfGameState* State)
{
	const int32 Holes = State->Pars.Num();
	if (Holes == 0)
	{
		return;
	}

	const float Left = 3.f * U;
	const float Width = Canvas->ClipX - 6.f * U;
	const float NameWidth = 20.f * U;
	const float TotalWidth = 10.f * U;
	const float Cell = (Width - NameWidth - TotalWidth) / Holes;
	const float Row = 6.f * U;
	const float Top = 26.f * U;

	TArray<AGolfPlayerState*> Players;
	for (APlayerState* Base : State->PlayerArray)
	{
		if (AGolfPlayerState* Player = Cast<AGolfPlayerState>(Base); Player && Player->bInRound)
		{
			Players.Add(Player);
		}
	}

	// Holographic card: a glass panel with a title, a hairline grid, and the current hole's column lit up.
	const float Height = Row * (2 + Players.Num());
	Box(FVector2D(Left, Top - 7.f * U), FVector2D(Width, Height + 7.f * U), Palette::Panel);
	Label(TEXT("SCORECARD"), FVector2D(Left + 2.f * U, Top - 5.8f * U), 3.2f, Palette::White, false);
	Label(TEXT("STROKE PLAY"), FVector2D(Left + Width - 2.f * U - 16.f * U, Top - 5.2f * U), 2.f, Palette::Dim, false);
	auto CellCenter = [&](int32 Column, float RowY) { return FVector2D(Left + NameWidth + Cell * (Column + 0.5f), RowY + Row * 0.5f); };
	if (State->HoleIndex >= 0 && State->HoleIndex < Holes)
	{
		FCanvasTileItem Current(FVector2D(Left + NameWidth + Cell * State->HoleIndex, Top), FVector2D(Cell, Height), FLinearColor(0.4f, 0.8f, 1.f, 0.14f));
		Current.BlendMode = SE_BLEND_Translucent;
		Canvas->DrawItem(Current);
	}
	for (int32 Column = 0; Column <= Holes; ++Column)
	{
		const float X = Left + NameWidth + Cell * Column;
		Line(FVector2D(X, Top), FVector2D(X, Top + Height), Palette::Hairline, 0.08f * U);
	}
	for (int32 Line_ = 0; Line_ <= 2 + Players.Num(); ++Line_)
	{
		Line(FVector2D(Left, Top + Row * Line_), FVector2D(Left + Width, Top + Row * Line_), Line_ == 2 ? Palette::Trim : Palette::Hairline, Line_ == 2 ? 0.15f * U : 0.08f * U);
	}

	// Header rows: hole numbers and par.
	Label(TEXT("HOLE"), FVector2D(Left + 1.5f * U, Top + 1.5f * U), 2.4f, Palette::Dim, false);
	Label(TEXT("PAR"), FVector2D(Left + 1.5f * U, Top + Row + 1.5f * U), 2.4f, Palette::Dim, false);
	int32 ParTotal = 0;
	for (int32 Hole = 0; Hole < Holes; ++Hole)
	{
		const bool bCurrent = Hole == State->HoleIndex;
		Label(FString::Printf(TEXT("%d"), Hole + 1), CellCenter(Hole, Top), 2.6f, bCurrent ? Palette::Glow : Palette::White, true);
		Label(FString::Printf(TEXT("%d"), State->Pars[Hole]), CellCenter(Hole, Top + Row), 2.4f, Palette::Dim, true);
		ParTotal += State->Pars[Hole];
	}
	Label(TEXT("TOTAL"), FVector2D(Left + Width - TotalWidth * 0.5f, Top + Row * 0.5f), 2.2f, Palette::Dim, true);
	Label(FString::Printf(TEXT("%d"), ParTotal), FVector2D(Left + Width - TotalWidth * 0.5f, Top + Row * 1.5f), 2.4f, Palette::Dim, true);

	// Player rows: birdie or better ringed in cyan, bogey or worse boxed in soft red (doubles for eagle / double).
	float RowY = Top + Row * 2.f;
	for (AGolfPlayerState* Player : Players)
	{
		Label(Player->GetPlayerName().Left(10).ToUpper(), FVector2D(Left + 1.5f * U, RowY + 1.4f * U), 2.6f, Palette::White, false);
		for (int32 Hole = 0; Hole < Holes && Hole < Player->HoleScores.Num(); ++Hole)
		{
			const int32 Score = Player->HoleScores[Hole];
			if (Score <= 0)
			{
				continue;
			}
			const FVector2D Center = CellCenter(Hole, RowY);
			const int32 Diff = Score - State->Pars[Hole];
			const float Mark = FMath::Min(Cell, Row) * 0.38f;
			if (Diff < 0)
			{
				Ring(Center, Mark, Palette::Under, 0.15f * U);
				if (Diff < -1) Ring(Center, Mark * 1.25f, Palette::Under, 0.15f * U);
			}
			else if (Diff > 0)
			{
				auto Square = [&](float S)
				{
					Line(Center + FVector2D(-S, -S), Center + FVector2D(S, -S), Palette::Over, 0.15f * U);
					Line(Center + FVector2D(S, -S), Center + FVector2D(S, S), Palette::Over, 0.15f * U);
					Line(Center + FVector2D(S, S), Center + FVector2D(-S, S), Palette::Over, 0.15f * U);
					Line(Center + FVector2D(-S, S), Center + FVector2D(-S, -S), Palette::Over, 0.15f * U);
				};
				Square(Mark);
				if (Diff > 1) Square(Mark * 1.25f);
			}
			Label(FString::Printf(TEXT("%d"), Score), Center, 2.6f, Palette::White, true);
		}
		const int32 ToPar = Player->GetToPar(State->Pars);
		Label(FString::Printf(TEXT("%d  %s"), Player->GetTotalStrokes(), ToPar == 0 ? TEXT("E") : *FString::Printf(TEXT("%+d"), ToPar)),
			FVector2D(Left + Width - TotalWidth * 0.5f, RowY + Row * 0.5f), 2.6f, ToPar < 0 ? Palette::Under : ToPar > 0 ? Palette::Over : Palette::White, true);
		RowY += Row;
	}
}

void AGolfHUD::DrawAnnouncement(AGolfGameState* State)
{
	const float Age = GetWorld()->GetTimeSeconds() - State->AnnouncementTime;
	if (Age > 3.f || State->Announcement.IsEmpty())
	{
		return;
	}
	const float Alpha = FMath::Clamp(3.f - Age, 0.f, 1.f);
	const FVector2D Center(Canvas->ClipX * 0.5f, 25.f * U);
	const FVector2D Pos(Canvas->ClipX * 0.22f, Center.Y - 4.5f * U);
	const FVector2D Size(Canvas->ClipX * 0.56f, 9.f * U);
	Box(Pos, Size, FLinearColor(0.32f, 0.6f, 0.95f, 0.2f * Alpha));
	// A scan line sweeps across the strip as it appears.
	const float Sweep = FMath::Clamp(Age / 0.6f, 0.f, 1.f);
	Line(FVector2D(Pos.X, Pos.Y + Size.Y), FVector2D(Pos.X + Size.X * Sweep, Pos.Y + Size.Y), FLinearColor(0.55f, 0.88f, 1.f, 0.9f * Alpha), 0.3f * U);
	Label(State->Announcement.ToUpper(), Center, 4.2f, FLinearColor(1.f, 1.f, 1.f, Alpha), true);
}
