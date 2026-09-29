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
#include "SkyLinksWindDebris.h"
#include "EngineUtils.h"
#include "Engine/GameInstance.h"
#include "CanvasItem.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Engine/World.h"
#include "Camera/PlayerCameraManager.h"
#include "Engine/TextureRenderTarget2D.h"
#include "RenderUtils.h"

namespace Palette
{
	// Arcade broadcast look (Golden Tee): solid dark-navy plates, bright blue header strips, bold white type,
	// square corners, everything tucked into the screen corners.
	const FLinearColor Panel(0.01f, 0.03f, 0.09f, 0.82f);
	const FLinearColor PanelSolid(0.02f, 0.05f, 0.14f, 0.9f);
	const FLinearColor Blue(0.02f, 0.28f, 0.9f, 0.95f);
	const FLinearColor Trim(0.85f, 0.92f, 1.f, 0.9f);
	const FLinearColor Gold(1.f, 0.82f, 0.3f, 1.f);
	const FLinearColor White(1.f, 1.f, 1.f, 1.f);
	const FLinearColor Dim(0.7f, 0.8f, 0.95f, 0.95f);
	const FLinearColor Glow(0.35f, 0.65f, 1.f, 1.f);
	const FLinearColor Hairline(0.8f, 0.9f, 1.f, 0.35f);
	const FLinearColor Under(0.35f, 1.f, 0.55f, 1.f);   // under par
	const FLinearColor Over(1.f, 0.45f, 0.4f, 1.f);     // over par
	const FLinearColor Accept(0.04f, 0.5f, 0.3f, 0.92f); // go / join / play
	const FLinearColor Red(0.8f, 0.15f, 0.12f, 0.92f);
	const FLinearColor Green(0.45f, 0.85f, 0.3f, 1.f);
	// Landing rings and break arrows: red reads against every shade of grass.
	const FLinearColor Target(1.f, 0.16f, 0.12f, 1.f);
	const FLinearColor TargetIdle(1.f, 0.35f, 0.3f, 0.9f);
}

namespace HudLayout
{
	// Left column: player plate, other players, hole map with the lie under it.
	// Right column: hole bar, voice buttons ... wind bar and club panel at the bottom.
	constexpr float Margin = 1.5f;
	constexpr float ColumnWidth = 28.5f;
	constexpr float PlayersTop = 8.4f;
	constexpr float PlayerRow = 2.6f;
	constexpr float RightWidth = 21.f;
	constexpr float WindFromBottom = 23.f;
}

// ---------------------------------------------------------------- drawing helpers

void AGolfHUD::Box(const FVector2D& Position, const FVector2D& Size, const FLinearColor& Color)
{
	Fill(Position, Size, Color);
	// Panels (not thin bars) get a fine light border.
	if (Size.X > 4.f * U && Size.Y > 3.f * U && Color.A < 0.95f)
	{
		const FVector2D A = Position, B = Position + FVector2D(Size.X, 0.f), C = Position + Size, D = Position + FVector2D(0.f, Size.Y);
		Line(B, C, Palette::Hairline, 1.f);
		Line(C, D, Palette::Hairline, 1.f);
		Line(D, A, Palette::Hairline, 1.f);
	}
}

namespace
{
	FLinearColor HudLighten(const FLinearColor& C, float T)
	{
		return FLinearColor(FMath::Lerp(C.R, 1.f, T), FMath::Lerp(C.G, 1.f, T), FMath::Lerp(C.B, 1.f, T), C.A);
	}
	FLinearColor HudDarken(const FLinearColor& C, float T)
	{
		return FLinearColor(C.R * (1.f - T), C.G * (1.f - T), C.B * (1.f - T), C.A);
	}
}

void AGolfHUD::Gradient(const FVector2D& Position, const FVector2D& Size, const FLinearColor& Top, const FLinearColor& Bottom)
{
	FCanvasUVTri A, B;
	A.V0_Pos = Position;                                A.V0_Color = Top;
	A.V1_Pos = Position + FVector2D(Size.X, 0.f);       A.V1_Color = Top;
	A.V2_Pos = Position + Size;                         A.V2_Color = Bottom;
	B.V0_Pos = Position;                                B.V0_Color = Top;
	B.V1_Pos = Position + Size;                         B.V1_Color = Bottom;
	B.V2_Pos = Position + FVector2D(0.f, Size.Y);       B.V2_Color = Bottom;
	TArray<FCanvasUVTri> Triangles;
	Triangles.Add(A);
	Triangles.Add(B);
	FCanvasTriangleItem Item(Triangles, GWhiteTexture);
	Item.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Item);
}

void AGolfHUD::GradientDisc(const FVector2D& Center, float Radius, const FLinearColor& Inner, const FLinearColor& Outer)
{
	constexpr int32 Segments = 40;
	TArray<FCanvasUVTri> Triangles;
	// Lit from above: the centre sits a little high, like a domed button.
	const FVector2D Hot = Center - FVector2D(0.f, Radius * 0.3f);
	for (int32 Index = 0; Index < Segments; ++Index)
	{
		const float A0 = 2.f * PI * Index / Segments, A1 = 2.f * PI * (Index + 1) / Segments;
		FCanvasUVTri Tri;
		Tri.V0_Pos = Hot;                                                     Tri.V0_Color = Inner;
		Tri.V1_Pos = Center + FVector2D(FMath::Cos(A0), FMath::Sin(A0)) * Radius; Tri.V1_Color = Outer;
		Tri.V2_Pos = Center + FVector2D(FMath::Cos(A1), FMath::Sin(A1)) * Radius; Tri.V2_Color = Outer;
		Triangles.Add(Tri);
	}
	FCanvasTriangleItem Item(Triangles, GWhiteTexture);
	Item.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Item);
}

void AGolfHUD::Fill(const FVector2D& Position, const FVector2D& Size, const FLinearColor& Color)
{
	const bool bHeader = Color.B > 0.7f && Color.B > Color.R * 3.f;
	if (bHeader)
	{
		// Glossy blue bar: bright top fading to deep blue, a sheen over the upper half, a dark line underneath.
		Gradient(Position, Size, HudLighten(Color, 0.28f), HudDarken(Color, 0.45f));
		Gradient(Position, FVector2D(Size.X, Size.Y * 0.48f), FLinearColor(1.f, 1.f, 1.f, 0.26f), FLinearColor(1.f, 1.f, 1.f, 0.06f));
		Line(Position + FVector2D(0.f, 0.5f), Position + FVector2D(Size.X, 0.5f), FLinearColor(0.75f, 0.9f, 1.f, 0.8f), 1.f);
		Line(Position + FVector2D(0.f, Size.Y - 0.5f), Position + FVector2D(Size.X, Size.Y - 0.5f), FLinearColor(0.f, 0.05f, 0.25f, 0.9f), 1.f);
		return;
	}
	// Plates: lighter slate at the top blending to near black, a soft highlight line on the top edge.
	FLinearColor Top = HudLighten(Color, 0.1f);
	Top = FLinearColor(Top.R + 0.03f, Top.G + 0.07f, Top.B + 0.16f, Color.A);
	FLinearColor Bottom = HudDarken(Color, 0.5f);
	Bottom.A = FMath::Min(1.f, Color.A + 0.08f);
	Gradient(Position, Size, Top, Bottom);
	if (Size.Y > 1.5f * U)
	{
		Line(Position + FVector2D(0.f, 0.5f), Position + FVector2D(Size.X, 0.5f), FLinearColor(0.55f, 0.75f, 1.f, 0.55f * Color.A), 1.f);
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
	// Blue header strip with bold white capitals.
	const float Left = bCenter ? Position.X - Width * 0.5f : Position.X;
	const float StripHeight = Height * 1.6f * U;
	Fill(FVector2D(Left, Position.Y), FVector2D(Width, StripHeight), Palette::Blue);
	if (bCenter)
	{
		Label(Text.ToUpper(), FVector2D(Position.X, Position.Y + StripHeight * 0.5f), Height, Palette::White, true);
	}
	else
	{
		Label(Text.ToUpper(), FVector2D(Left + 0.8f * U, Position.Y + StripHeight * 0.5f - Height * 0.55f * U), Height, Palette::White, false);
	}
}

void AGolfHUD::RoundButton(EGolfHudButton Id, const FVector2D& Center, float Radius, const FString& Text, const FLinearColor& FillColor, int32 Payload)
{
	// Solid disc in the button's colour with a bright blue rim.
	FLinearColor Solid = FillColor;
	Solid.A = FMath::Max(FillColor.A, 0.85f);
	FLinearColor Inner = HudLighten(Solid, 0.3f);
	Inner = FLinearColor(Inner.R + 0.04f, Inner.G + 0.1f, Inner.B + 0.2f, Solid.A);
	GradientDisc(Center, Radius, Inner, HudDarken(Solid, 0.45f));
	Ring(Center, Radius, Palette::Glow, 0.2f * U);
	Arc(Center, Radius * 0.86f, 200.f, 140.f, FLinearColor(1.f, 1.f, 1.f, 0.35f), 0.15f * U);
	Label(Text, Center, Radius * 0.42f / U, Palette::White, true);
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
	if (!TActorIterator<ASkyLinksWindDebris>(GetWorld()))
	{
		FActorSpawnParameters Params;
		Params.Owner = this;
		GetWorld()->SpawnActor<ASkyLinksWindDebris>(ASkyLinksWindDebris::StaticClass(), FTransform::Identity, Params);
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
	RoundButton(EGolfHudButton::Microphone, FVector2D(Canvas->ClipX - 3.9f * U, 11.5f * U), 2.3f * U,
		MicLabel, bMuted ? Palette::Red : Voice->IsReady() ? Palette::Accept : Palette::PanelSolid);
	RoundButton(EGolfHudButton::VoicePanel, FVector2D(Canvas->ClipX - 9.f * U, 11.5f * U), 2.3f * U,
		TEXT("GROUP"), Palette::PanelSolid);
	if (!Controller->IsVoicePanelOpen()) return;
	const FVector2D Origin(Canvas->ClipX - 54.f * U, 15.f * U);
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
		Fill(Chip, FVector2D(ChipWidth, 3.8f * U), Palette::Panel);
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
	const float GapLeft = (HudLayout::Margin + HudLayout::ColumnWidth + 2.f) * U;
	const float GapRight = Canvas->ClipX - (HudLayout::RightWidth + HudLayout::Margin + 2.f) * U;
	const float Width = FMath::Clamp(GapRight - GapLeft, 24.f * U, 44.f * U);
	const FVector2D Size(Width, Width * 9.f / 16.f);
	const FVector2D Pos(FMath::Max(GapLeft, (GapLeft + GapRight - Width) * 0.5f), HudLayout::Margin * U);
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
	Heading(TEXT("Landing"), Pos, 12.f * U, 1.3f);
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
	const AGolfPlayerState* Current = Cast<AGolfPlayerState>(State->ActivePlayer);
	const int32 Others = FMath::Max(0, Rows - (Current && Current->bInRound ? 1 : 0));
	const float HeaderH = 2.4f * U;
	const float Top = (HudLayout::PlayersTop + (HudLayout::PlayerRow + 0.3f) * Others + 0.6f) * U + HeaderH;
	const float Aspect = static_cast<float>(Picture->SizeX) / FMath::Max(1, Picture->SizeY);
	float Height = FMath::Clamp(Canvas->ClipY - HudLayout::Margin * U - HeaderH - Top, 14.f * U, 52.f * U);
	if (Height * Aspect > 20.f * U)
	{
		Height = 20.f * U / Aspect;
	}
	const FVector2D Size(Height * Aspect, Height);
	const FVector2D Pos(HudLayout::Margin * U, Top);
	const FVector2D Center = Pos + Size * 0.5f;
	Box(Pos - FVector2D(0.4f * U, 0.4f * U), Size + FVector2D(0.8f * U, 0.8f * U), Palette::PanelSolid);
	FCanvasTileItem Tile(Pos, Picture->GetResource(), Size, FLinearColor::White);
	Tile.BlendMode = SE_BLEND_Opaque;
	Canvas->DrawItem(Tile);

	Heading(TEXT("Hole map"), Pos - FVector2D(0.4f * U, HeaderH + 0.4f * U), Size.X + 0.8f * U, 1.4f);
	if (Current && Current->Ball)
	{
		// The lie on a dark bar under the map.
		const FVector2D LiePos(Pos.X - 0.4f * U, Pos.Y + Size.Y + 0.4f);
		Fill(LiePos, FVector2D(Size.X + 0.8f * U, HeaderH), Palette::PanelSolid);
		Label(TEXT("LIE"), LiePos + FVector2D(0.8f * U, 0.5f * U), 1.2f, Palette::Dim, false);
		Label(GolfPhysics::LieName(Current->Ball->GetLie()).ToUpper(), LiePos + FVector2D((Size.X + 0.8f * U) * 0.6f, HeaderH * 0.5f), 1.4f, Palette::Gold, true);
	}

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
		const FVector2D Tag = Top - FVector2D(0.f, 2.f * U);
		Fill(Tag - FVector2D(3.8f * U, 1.1f * U), FVector2D(7.6f * U, 2.2f * U), Palette::Panel);
		Line(Tag - FVector2D(3.8f * U, 1.1f * U), Tag + FVector2D(-3.8f * U, 1.1f * U), Yellow, 0.3f * U);
		Label(Distance, Tag, 1.5f, Palette::White, true);
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
	const FVector2D Compass(Canvas->ClipX * 0.5f, 7.f * U);
	Disc(Compass, 4.6f * U, Palette::Panel);
	Ring(Compass, 4.6f * U, Palette::Trim, 0.12f * U);
	for (int32 Tick = 0; Tick < 12; ++Tick)
	{
		const FVector2D TickDir(FMath::Cos(Tick * PI / 6.f), FMath::Sin(Tick * PI / 6.f));
		Line(Compass + TickDir * 4.f * U, Compass + TickDir * 4.5f * U, Palette::Hairline, 0.12f * U);
	}
	Arc(Compass, 5.2f * U, -120.f, 60.f, Palette::Glow, 0.3f * U);
	const FVector ToBall = Ball->GetRestLocation() - From->GetActorLocation();
	const float CameraYaw = PlayerOwner->PlayerCameraManager ? PlayerOwner->PlayerCameraManager->GetCameraRotation().Yaw : From->GetActorRotation().Yaw;
	const float Bearing = FMath::DegreesToRadians(ToBall.Rotation().Yaw - CameraYaw);
	const FVector2D Dir(FMath::Sin(Bearing), -FMath::Cos(Bearing));
	const FVector2D Side(-Dir.Y, Dir.X);
	const FVector2D Tip = Compass + Dir * 3.4f * U;
	Line(Compass - Dir * 2.2f * U, Tip, Palette::Glow, 0.4f * U);
	Line(Tip, Tip - Dir * 1.3f * U + Side * 1.f * U, Palette::Glow, 0.4f * U);
	Line(Tip, Tip - Dir * 1.3f * U - Side * 1.f * U, Palette::Glow, 0.4f * U);
	Label(FString::Printf(TEXT("BALL  %.0f m"), Controller->GetDistanceToBall()), Compass + FVector2D(0.f, 6.4f * U), 1.7f, Palette::White, true);

	// Marker over the ball when it is in view.
	FVector2D BallScreen;
	if (ToScreen(Ball->GetRestLocation() + FVector(0.f, 0.f, 120.f), BallScreen))
	{
		Ring(BallScreen, 1.4f * U, Palette::Glow, 0.3f * U);
		Line(BallScreen + FVector2D(0.f, 1.4f * U), BallScreen + FVector2D(0.f, 4.f * U), Palette::Glow, 0.25f * U);
	}

	RoundButton(EGolfHudButton::SkipDrive, FVector2D(Canvas->ClipX - 8.f * U, 33.f * U), 3.4f * U, TEXT("SKIP"), Palette::PanelSolid);
	if (Controller->CanPlayShot())
	{
		RoundButton(EGolfHudButton::PlayShot, FVector2D(Canvas->ClipX * 0.5f, Canvas->ClipY - 10.f * U), 6.5f * U, TEXT("PLAY SHOT"), Palette::Accept);
	}
	else
	{
		Label(TEXT("GET WITHIN 15 M OF YOUR BALL"), FVector2D(Canvas->ClipX * 0.5f, Canvas->ClipY - 3.f * U), 1.6f, Palette::Dim, true);
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
	const FVector2D Pad(15.f * U, Canvas->ClipY - 12.f * U);
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
	const FVector2D Go(Canvas->ClipX - 11.f * U, Canvas->ClipY - 12.f * U);
	RoundButton(EGolfHudButton::Throttle, Go, 7.5f * U, TEXT("GO"), Palette::Accept);
	RoundButton(EGolfHudButton::Reverse, FVector2D(Canvas->ClipX - 26.f * U, Canvas->ClipY - 7.f * U), 4.5f * U, TEXT("REV"), Palette::PanelSolid);
	RoundButton(EGolfHudButton::Buggy, FVector2D(Canvas->ClipX - 8.f * U, 42.f * U), 3.4f * U, TEXT("GET OUT"), Palette::PanelSolid);

	// Speedo arc over the GO pedal.
	const float Kmh = FMath::Abs(Buggy->GetSpeed()) * 0.036f;
	Arc(Go, 9.8f * U, 200.f, 140.f, Palette::Hairline, 0.18f * U);
	Arc(Go, 9.8f * U, 200.f, 140.f * FMath::Clamp(Kmh / 30.f, 0.f, 1.f), Palette::Glow, 0.4f * U);
	Label(FString::Printf(TEXT("%.0f KM/H"), Kmh), Go - FVector2D(0.f, 11.8f * U), 1.8f, Palette::White, true);
}

void AGolfHUD::DrawWalking(AGolfPlayerController* Controller)
{
	DrawBallCompass(Controller, Controller->GetPawn());

	// Thumb stick on the left: glass ring with ticks and a glowing arc toward the push, the knob follows the thumb.
	const FVector2D Pad(12.f * U, Canvas->ClipY - 12.f * U);
	Disc(Pad, 7.f * U, Palette::Panel);
	Ring(Pad, 7.f * U, Palette::Trim, 0.15f * U);
	Ring(Pad, 4.f * U, Palette::Hairline, 0.1f * U);
	for (int32 Tick = 0; Tick < 8; ++Tick)
	{
		const FVector2D Dir(FMath::Cos(Tick * PI / 4.f), FMath::Sin(Tick * PI / 4.f));
		Line(Pad + Dir * 6.2f * U, Pad + Dir * 6.9f * U, Palette::Hairline, 0.12f * U);
	}
	const FVector2D Stick = Controller->GetWalkStick();
	const FVector2D Offset(Stick.X, -Stick.Y);
	if (Offset.SizeSquared() > 0.01f)
	{
		const float Push = FMath::RadiansToDegrees(FMath::Atan2(Offset.Y, Offset.X));
		Arc(Pad, 7.8f * U, Push - 25.f, 50.f, Palette::Glow, 0.35f * U);
	}
	const FVector2D Knob = Pad + Offset * 5.2f * U;
	Disc(Knob, 2.3f * U, FLinearColor(0.55f, 0.88f, 1.f, 0.3f));
	Ring(Knob, 2.3f * U, Palette::Trim, 0.15f * U);
	Disc(Knob, 0.6f * U, Palette::White);
	Label(TEXT("DRAG TO WALK"), Pad + FVector2D(0.f, 8.6f * U), 1.4f, Palette::Dim, true);

	if (Controller->CanTeeUp())
	{
		RoundButton(EGolfHudButton::Start, FVector2D(Canvas->ClipX - 11.f * U, Canvas->ClipY - 12.f * U), 6.f * U, TEXT("TEE UP"), Palette::Accept);
		Label(TEXT("[ E ]"), FVector2D(Canvas->ClipX - 11.f * U, Canvas->ClipY - 3.8f * U), 1.5f, Palette::Dim, true);
	}
	else if (Controller->GetBuggyInReach())
	{
		RoundButton(EGolfHudButton::Buggy, FVector2D(Canvas->ClipX - 11.f * U, Canvas->ClipY - 12.f * U), 6.f * U, TEXT("GET IN"), Palette::Accept);
		Label(TEXT("[ E ]"), FVector2D(Canvas->ClipX - 11.f * U, Canvas->ClipY - 3.8f * U), 1.5f, Palette::Dim, true);
	}
}

void AGolfHUD::DrawHoleCard(AGolfGameState* State)
{
	const AGolfHole* Hole = State->CurrentHole;
	if (!Hole)
	{
		return;
	}
	// Top right: blue HOLE bar, par and distance to the pin on a dark bar underneath.
	const float Width = HudLayout::RightWidth * U;
	const FVector2D Pos(Canvas->ClipX - Width - HudLayout::Margin * U, HudLayout::Margin * U);
	Fill(Pos, FVector2D(Width, 4.f * U), Palette::Blue);
	Label(FString::Printf(TEXT("HOLE %d"), State->HoleIndex + 1), Pos + FVector2D(Width * 0.5f, 2.f * U), 2.6f, Palette::White, true);

	const FVector2D Sub = Pos + FVector2D(0.f, 4.f * U);
	Fill(Sub, FVector2D(Width, 2.6f * U), Palette::PanelSolid);
	Label(FString::Printf(TEXT("PAR %d"), Hole->Par), Sub + FVector2D(1.f * U, 0.5f * U), 1.4f, Palette::White, false);
	if (const AGolfPlayerState* Active = Cast<AGolfPlayerState>(State->ActivePlayer); Active && Active->Ball)
	{
		const float Meters = FVector::Dist2D(Active->Ball->GetRestLocation(), Hole->GetCupLocation()) / 100.f;
		const FString PinDistance = Meters < 1.f ? FString::Printf(TEXT("%.0f CM TO PIN"), Meters * 100.f)
			: (Meters < 10.f ? FString::Printf(TEXT("%.1f M TO PIN"), Meters) : FString::Printf(TEXT("%.0f M TO PIN"), Meters));
		Label(PinDistance, Sub + FVector2D(Width * 0.45f, 0.5f * U), 1.4f, Palette::Gold, false);
	}
}

void AGolfHUD::DrawPlayers(AGolfGameState* State)
{
	// Top left: the player whose turn it is on a big name plate with a score box, strokes this hole beneath;
	// everyone else on slim rows under that.
	const float X = HudLayout::Margin * U;
	const float W = HudLayout::ColumnWidth * U;
	const AGolfPlayerState* Active = Cast<AGolfPlayerState>(State->ActivePlayer);
	auto ScoreText = [&State](const AGolfPlayerState* Player, int32& OutToPar)
	{
		OutToPar = Player->GetToPar(State->Pars);
		return OutToPar == 0 ? FString(TEXT("E")) : FString::Printf(TEXT("%+d"), OutToPar);
	};
	if (Active && Active->bInRound)
	{
		const float Y = HudLayout::Margin * U;
		const float ScoreW = 4.6f * U;
		Fill(FVector2D(X, Y), FVector2D(W - ScoreW, 4.f * U), Palette::PanelSolid);
		Label(Active->GetPlayerName().Left(14).ToUpper(), FVector2D(X + 1.f * U, Y + 0.7f * U), 2.2f, Palette::White, false);
		Fill(FVector2D(X + W - ScoreW, Y), FVector2D(ScoreW, 4.f * U), FLinearColor(0.92f, 0.95f, 1.f, 0.95f));
		int32 ToPar = 0;
		const FString Score = ScoreText(Active, ToPar);
		const FLinearColor ScoreColour = ToPar < 0 ? FLinearColor(0.f, 0.4f, 0.2f, 1.f) : ToPar > 0 ? FLinearColor(0.7f, 0.08f, 0.05f, 1.f) : FLinearColor(0.02f, 0.1f, 0.3f, 1.f);
		FCanvasTextItem ScoreItem(FVector2D(X + W - ScoreW * 0.5f, Y + 2.f * U), FText::FromString(Score), GEngine->GetLargeFont(), ScoreColour);
		const float ScoreScale = 2.6f * U / FMath::Max(1.f, (float)GEngine->GetLargeFont()->GetMaxCharHeight());
		ScoreItem.Scale = FVector2D(ScoreScale, ScoreScale);
		ScoreItem.bCentreX = ScoreItem.bCentreY = true;
		Canvas->DrawItem(ScoreItem);

		// Stroke counter: this hole's strokes lit, the rest faint.
		const float SY = Y + 4.f * U;
		Fill(FVector2D(X, SY), FVector2D(W, 2.4f * U), Palette::Panel);
		Label(TEXT("STROKE"), FVector2D(X + 1.f * U, SY + 0.5f * U), 1.2f, Palette::White, false);
		const int32 Current = Active->Strokes + 1;
		for (int32 Number = 1; Number <= 8; ++Number)
		{
			const bool bNow = Number == Current;
			const FLinearColor Colour = bNow ? Palette::Gold : Number < Current ? Palette::White : FLinearColor(0.7f, 0.8f, 0.95f, 0.35f);
			Label(FString::FromInt(Number), FVector2D(X + 8.f * U + (Number - 1) * 2.1f * U, SY + 1.2f * U), bNow ? 1.6f : 1.2f, Colour, true);
		}
	}

	float Y = HudLayout::PlayersTop * U;
	for (APlayerState* Base : State->PlayerArray)
	{
		const AGolfPlayerState* Player = Cast<AGolfPlayerState>(Base);
		if (!Player || !Player->bInRound || Player == Active)
		{
			continue;
		}
		Fill(FVector2D(X, Y), FVector2D(W, HudLayout::PlayerRow * U), Palette::Panel);
		int32 ToPar = 0;
		const FString Score = ScoreText(Player, ToPar);
		Label(Player->GetPlayerName().Left(14).ToUpper(), FVector2D(X + 1.f * U, Y + 0.45f * U), 1.4f, Palette::Dim, false);
		Label(Player->bHoledOut ? TEXT("IN") : FString::Printf(TEXT("%d"), Player->Strokes), FVector2D(X + W - 6.5f * U, Y + 0.45f * U), 1.4f, Palette::White, false);
		Label(Score, FVector2D(X + W - 3.f * U, Y + 0.45f * U), 1.4f, ToPar < 0 ? Palette::Under : ToPar > 0 ? Palette::Over : Palette::White, false);
		Y += (HudLayout::PlayerRow + 0.3f) * U;
	}
}

void AGolfHUD::DrawWind(AGolfGameState* State)
{
	// Right side: blue bar with the wind arrow in a dark square and the speed in big type.
	const float Width = HudLayout::RightWidth * U;
	const FVector2D Pos(Canvas->ClipX - Width - HudLayout::Margin * U, Canvas->ClipY - HudLayout::WindFromBottom * U);
	const float H = 4.4f * U;
	Fill(Pos, FVector2D(Width, H), Palette::Blue);
	Fill(Pos, FVector2D(H, H), Palette::PanelSolid);

	const float Speed = State->Wind.Size2D() / 100.f;
	const FVector2D Center = Pos + FVector2D(H * 0.5f, H * 0.5f);
	if (Speed > 0.05f && PlayerOwner && PlayerOwner->PlayerCameraManager)
	{
		// Screen-up is the camera's forward direction.
		const float Relative = FMath::DegreesToRadians(State->Wind.Rotation().Yaw - PlayerOwner->PlayerCameraManager->GetCameraRotation().Yaw);
		const FVector2D Dir(FMath::Sin(Relative), -FMath::Cos(Relative));
		const FVector2D Side(-Dir.Y, Dir.X);
		const FVector2D Tip = Center + Dir * 1.6f * U;
		Line(Center - Dir * 1.5f * U, Tip, Palette::White, 0.4f * U);
		Line(Tip, Tip - Dir * 1.f * U + Side * 0.8f * U, Palette::White, 0.4f * U);
		Line(Tip, Tip - Dir * 1.f * U - Side * 0.8f * U, Palette::White, 0.4f * U);
	}
	Label(TEXT("WIND"), Pos + FVector2D(H + 1.f * U, 1.4f * U), 1.2f, Palette::White, false);
	Label(FString::Printf(TEXT("%.1f M/S"), Speed), Pos + FVector2D(Width - 1.f * U - 9.f * U, 0.9f * U), 2.4f, Palette::White, false);
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
	// Bottom right: club panel (club, carry, spin) over a blue bar with arrows to change club.
	const float Width = HudLayout::RightWidth * U;
	const float X = Canvas->ClipX - Width - HudLayout::Margin * U;
	const float BarH = 3.6f * U;
	const float BarY = Canvas->ClipY - HudLayout::Margin * U - BarH;
	const float PanelH = 12.f * U;
	const float PanelY = BarY - PanelH;
	Fill(FVector2D(X, PanelY), FVector2D(Width, PanelH), Palette::Panel);
	Label(TEXT("CLUB"), FVector2D(X + 1.f * U, PanelY + 0.6f * U), 1.2f, Palette::Dim, false);
	Label(Bag[Index].ShortName, FVector2D(X + Width * 0.28f, PanelY + 5.2f * U), 5.f, Palette::White, true);
	Label(FString::Printf(TEXT("%.0f M"), Controller->GetClubCarry(Index) / 100.f), FVector2D(X + Width * 0.72f, PanelY + 4.2f * U), 2.6f, Palette::White, true);
	Label(TEXT("CARRY"), FVector2D(X + Width * 0.72f, PanelY + 6.6f * U), 1.1f, Palette::Dim, true);
	Buttons.Add({ EGolfHudButton::Club, FVector2D(X + Width * 0.5f, PanelY + 5.f * U), 0.f, 1, FVector2D(Width, 8.f * U) });

	// Spin: a strip along the bottom of the panel; tap to change.
	const FVector2D SpinPos(X + 0.6f * U, PanelY + PanelH - 3.2f * U);
	const FVector2D SpinSize(Width - 1.2f * U, 2.6f * U);
	Fill(SpinPos, SpinSize, Palette::PanelSolid);
	Label(TEXT("SPIN"), SpinPos + FVector2D(0.8f * U, 0.6f * U), 1.2f, Palette::Dim, false);
	Label(Controller->GetSpinLabel().ToUpper(), SpinPos + FVector2D(SpinSize.X * 0.6f, SpinSize.Y * 0.5f), 1.4f, Palette::Gold, true);
	Buttons.Add({ EGolfHudButton::Spin, SpinPos + SpinSize * 0.5f, 0.f, 0, SpinSize });

	// Blue bar: < CHANGE CLUB >, the arrows step through the bag.
	Fill(FVector2D(X, BarY), FVector2D(Width, BarH), Palette::Blue);
	Label(FString::Printf(TEXT("%d / %d"), Index + 1, Bag.Num()), FVector2D(X + Width * 0.5f, BarY + BarH * 0.5f), 1.5f, Palette::White, true);
	for (const int32 Step : { -1, 1 })
	{
		const FVector2D ArrowCenter(Step < 0 ? X + BarH * 0.6f : X + Width - BarH * 0.6f, BarY + BarH * 0.5f);
		const float S = 0.8f * U;
		const FVector2D Point = ArrowCenter + FVector2D(Step * S, 0.f);
		Line(Point, ArrowCenter + FVector2D(-Step * S * 0.6f, -S), Palette::White, 0.35f * U);
		Line(Point, ArrowCenter + FVector2D(-Step * S * 0.6f, S), Palette::White, 0.35f * U);
		Buttons.Add({ EGolfHudButton::Club, ArrowCenter, 0.f, Step, FVector2D(BarH * 1.4f, BarH) });
	}
}

void AGolfHUD::DrawPowerMeter(AGolfPlayerController* Controller)
{
	using PC = AGolfPlayerController;

	// Slim vertical track left of the right-hand panels: blue cells fill as the finger travels up. The swipe
	// itself can start anywhere low on screen.
	const float Bottom = Canvas->ClipY - HudLayout::Margin * U;
	const float Length = FMath::Min(PC::FullPowerSwipe * Canvas->ClipY, 40.f * U);
	const float CenterX = Canvas->ClipX - (HudLayout::RightWidth + HudLayout::Margin + 2.4f) * U;
	const float Width = 1.8f * U;
	const float Power = Controller->GetSwingPower();

	Fill(FVector2D(CenterX - Width * 0.5f - 0.3f * U, Bottom - Length - 0.3f * U), FVector2D(Width + 0.6f * U, Length + 0.6f * U), Palette::Panel);
	constexpr int32 Segments = 20;
	const float Gap = 0.2f * U;
	const float SegmentLength = (Length - Gap * (Segments - 1)) / Segments;
	for (int32 Segment = 0; Segment < Segments; ++Segment)
	{
		const float From = static_cast<float>(Segment) / Segments;
		// Blue low down, through cyan and green to gold, and red right at the top.
		const FLinearColor Ramp = From < 0.5f ? FMath::Lerp(FLinearColor(0.05f, 0.35f, 1.f, 0.95f), FLinearColor(0.2f, 0.85f, 0.95f, 0.95f), From / 0.5f)
			: From < 0.85f ? FMath::Lerp(FLinearColor(0.3f, 0.95f, 0.45f, 0.95f), FLinearColor(1.f, 0.8f, 0.2f, 0.95f), (From - 0.5f) / 0.35f)
			: FLinearColor(1.f, 0.3f, 0.15f, 0.95f);
		const FLinearColor Colour = Power > From ? Ramp : FLinearColor(0.8f, 0.9f, 1.f, 0.08f);
		Fill(FVector2D(CenterX - Width * 0.5f, Bottom - (Segment + 1) * SegmentLength - Segment * Gap), FVector2D(Width, SegmentLength), Colour);
	}
	for (const float Notch : { 0.25f, 0.5f, 0.75f, 1.f })
	{
		const float Y = Bottom - Length * Notch;
		Line(FVector2D(CenterX - Width * 0.9f, Y), FVector2D(CenterX - Width * 0.55f, Y), Palette::White, 1.f);
		Label(FString::Printf(TEXT("%d"), FMath::RoundToInt(Notch * 100.f)), FVector2D(CenterX - Width * 2.f, Y), 1.1f, Palette::Dim, true);
	}

	// Straightness: a marker beside the top of the track slides left or right as the swipe drifts.
	if (Controller->IsSwinging())
	{
		const float Accuracy = Controller->GetSwingAccuracy();
		const FVector2D Straight(CenterX, Bottom - Length - 1.6f * U);
		Line(Straight - FVector2D(2.5f * U, 0.f), Straight + FVector2D(2.5f * U, 0.f), Palette::Hairline, 1.f);
		Disc(Straight + FVector2D(Accuracy * 2.5f * U, 0.f), 0.5f * U, FMath::IsNearlyZero(Accuracy) ? Palette::White : Palette::Over);
	}
	Label(Controller->IsSwinging() ? FString::Printf(TEXT("%d%%"), FMath::RoundToInt(Power * 100.f)) : FString(TEXT("POWER")),
		FVector2D(CenterX, Bottom - Length - 3.4f * U), 1.4f, Palette::White, true);

	const AGolfGameState* State = GetWorld()->GetGameState<AGolfGameState>();
	const bool bAnnouncing = State && !State->Announcement.IsEmpty() && GetWorld()->GetTimeSeconds() - State->AnnouncementTime < 3.f;
	if (!Controller->IsSwinging() && !bAnnouncing)
	{
		Notice(TEXT("Swipe up to swing  ·  drag the top of the screen to aim"), 1.f);
	}
	if (GetWorld()->GetTimeSeconds() - Controller->GetPerfectFlashTime() < 1.2f)
	{
		const FVector2D Flash(Canvas->ClipX * 0.5f, Canvas->ClipY * 0.42f);
		Heading(TEXT("Pure strike"), Flash, 24.f * U, 2.6f, true);
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
		Fill(FVector2D(Left + NameWidth + Cell * State->HoleIndex, Top), FVector2D(Cell, Height), FLinearColor(0.4f, 0.8f, 1.f, 0.14f));
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
	Notice(State->Announcement, FMath::Clamp(3.f - Age, 0.f, 1.f));
}

void AGolfHUD::Notice(const FString& Text, float Alpha)
{
	// Bottom middle: a dark banner with a blue "!" square, like an arcade cabinet's message line.
	const float H = 3.4f * U;
	const float W = FMath::Min(Canvas->ClipX * 0.5f, 48.f * U);
	const FVector2D Pos(Canvas->ClipX * 0.5f - W * 0.5f, Canvas->ClipY - HudLayout::Margin * U - H);
	Fill(Pos, FVector2D(W, H), FLinearColor(0.01f, 0.03f, 0.09f, 0.82f * Alpha));
	Fill(Pos, FVector2D(H, H), FLinearColor(0.02f, 0.28f, 0.9f, 0.95f * Alpha));
	Label(TEXT("!"), Pos + FVector2D(H * 0.5f, H * 0.5f), 2.2f, FLinearColor(1.f, 1.f, 1.f, Alpha), true);
	Label(Text.ToUpper(), Pos + FVector2D(H + (W - H) * 0.5f, H * 0.5f), 1.5f, FLinearColor(1.f, 1.f, 1.f, Alpha), true);
}
