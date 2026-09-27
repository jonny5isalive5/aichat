#include "GolfHUD.h"
#include "GolfBall.h"
#include "GolfBuggy.h"
#include "GolfGameState.h"
#include "GolfHole.h"
#include "GolfPhysics.h"
#include "GolfPlayerController.h"
#include "GolfPlayerState.h"
#include "GolfSessionSubsystem.h"
#include "Engine/GameInstance.h"
#include "CanvasItem.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Engine/World.h"
#include "Camera/PlayerCameraManager.h"

namespace Palette
{
	// Broadcast-style golf sim: dark glass panels, white type, a single green accent.
	const FLinearColor Panel(0.f, 0.f, 0.f, 0.5f);
	const FLinearColor PanelSolid(0.02f, 0.02f, 0.02f, 0.8f);
	const FLinearColor Trim(1.f, 1.f, 1.f, 0.85f);
	const FLinearColor Gold(0.95f, 0.9f, 0.75f, 1.f);
	const FLinearColor White(1.f, 1.f, 1.f, 1.f);
	const FLinearColor Dim(0.72f, 0.74f, 0.72f, 1.f);
	const FLinearColor Red(0.9f, 0.22f, 0.18f, 1.f);
	const FLinearColor Green(0.45f, 0.85f, 0.3f, 1.f);
}

// ---------------------------------------------------------------- drawing helpers

void AGolfHUD::Box(const FVector2D& Position, const FVector2D& Size, const FLinearColor& Color)
{
	FCanvasTileItem Item(Position, Size, Color);
	Item.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Item);
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
	Item.EnableShadow(FLinearColor(0.f, 0.f, 0.f, 0.7f), FVector2D(1.5f, 1.5f));
	Canvas->DrawItem(Item);
}

void AGolfHUD::RoundButton(EGolfHudButton Id, const FVector2D& Center, float Radius, const FString& Text, const FLinearColor& Fill, int32 Payload)
{
	Disc(Center, Radius, Fill);
	Ring(Center, Radius, Palette::Trim, 0.5f * U);
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
		if (FVector2D::Distance(ScreenPosition, Button.Center) <= Button.Radius * 1.1f)
		{
			OutPayload = Button.Payload;
			return Button.Id;
		}
	}
	return EGolfHudButton::None;
}

// ---------------------------------------------------------------- frame

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
		DrawLobby(State, Controller);
		break;
	case EGolfMatchPhase::PlayingHole:
		DrawPlaying(State, Controller);
		break;
	case EGolfMatchPhase::HoleSummary:
		DrawHoleCard(State);
		DrawScorecard(State);
		break;
	case EGolfMatchPhase::RoundOver:
		DrawScorecard(State);
		if (Controller->IsLocalController() && GetNetMode() != NM_Client)
		{
			RoundButton(EGolfHudButton::Start, FVector2D(Canvas->ClipX * 0.5f, Canvas->ClipY - 12.f * U), 8.f * U, TEXT("AGAIN"), Palette::PanelSolid);
		}
		break;
	}
	DrawAnnouncement(State);
	DrawInvitePopup();
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
	Box(Center - FVector2D(45.f * U, 38.f * U), FVector2D(90.f * U, 76.f * U), Palette::Panel);
	Label(TEXT("SKY LINKS"), Center - FVector2D(0.f, 30.f * U), 9.f, Palette::Gold, true);

	int32 TotalPar = 0;
	for (const int32 Par : State->Pars)
	{
		TotalPar += Par;
	}
	if (State->Pars.Num() == 0)
	{
		Label(TEXT("No course in this level. Run Scripts/build_blockout_course.py, then open Maps/Course."),
			Center - FVector2D(0.f, 22.f * U), 2.8f, Palette::Red, true);
	}
	else
	{
		Label(FString::Printf(TEXT("%d HOLES  ·  PAR %d"), State->Pars.Num(), TotalPar), Center - FVector2D(0.f, 22.f * U), 3.5f, Palette::Dim, true);
	}

	// Room code, big, so it can be read out to friends.
	if (!State->RoomCode.IsEmpty())
	{
		Label(TEXT("ROOM CODE"), Center - FVector2D(0.f, 16.f * U), 3.f, Palette::Trim, true);
		Label(State->RoomCode, Center - FVector2D(0.f, 9.f * U), 10.f, Palette::White, true);
	}

	float Y = Center.Y - (State->RoomCode.IsEmpty() ? 12.f : 1.f) * U;
	for (APlayerState* Player : State->PlayerArray)
	{
		Label(Player->GetPlayerName(), FVector2D(Center.X, Y), 3.3f, Palette::White, true);
		Y += 4.2f * U;
	}

	const ENetMode NetMode = GetNetMode();
	const float ButtonY = Center.Y + 24.f * U;
	if (NetMode == NM_Standalone)
	{
		RoundButton(EGolfHudButton::Start, FVector2D(Center.X - 22.f * U, ButtonY), 8.f * U, TEXT("SOLO"), Palette::PanelSolid);
		RoundButton(EGolfHudButton::Host, FVector2D(Center.X, ButtonY), 8.f * U, TEXT("HOST"), Palette::PanelSolid);
		RoundButton(EGolfHudButton::Join, FVector2D(Center.X + 22.f * U, ButtonY), 8.f * U, TEXT("JOIN"), Palette::PanelSolid);
	}
	else if (NetMode == NM_ListenServer)
	{
		RoundButton(EGolfHudButton::Start, FVector2D(Center.X - 11.f * U, ButtonY), 8.f * U, TEXT("TEE OFF"), Palette::PanelSolid);
		if (Sessions && Sessions->SupportsFriends())
		{
			RoundButton(EGolfHudButton::Friends, FVector2D(Center.X + 11.f * U, ButtonY), 8.f * U, TEXT("INVITE"), Palette::PanelSolid);
		}
		Label(FString::Printf(TEXT("%d / %d players"), State->PlayerArray.Num(), UGolfSessionSubsystem::MaxPlayers),
			FVector2D(Center.X, ButtonY - 11.f * U), 3.f, Palette::Dim, true);
	}
	else
	{
		Label(TEXT("Waiting for the host to tee off"), FVector2D(Center.X, ButtonY), 3.6f, Palette::Dim, true);
	}

	if (Sessions && !Sessions->GetStatus().IsEmpty())
	{
		Label(Sessions->GetStatus(), FVector2D(Center.X, Center.Y + 35.f * U), 3.f, Palette::Gold, true);
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
	Label(TEXT("ENTER ROOM CODE"), Center - FVector2D(0.f, 38.f * U), 3.5f, Palette::Trim, true);

	// Four boxes for the digits typed so far.
	const FString Code = Controller->GetEnteredCode();
	for (int32 Index = 0; Index < 4; ++Index)
	{
		const FVector2D Slot(Center.X + (Index - 1.5f) * 9.f * U, Center.Y - 28.f * U);
		Box(Slot - FVector2D(3.5f * U, 4.f * U), FVector2D(7.f * U, 8.f * U), Palette::PanelSolid);
		if (Index < Code.Len())
		{
			Label(Code.Mid(Index, 1), Slot, 6.f, Palette::White, true);
		}
	}

	// Phone-style grid: 1-9, then delete / 0 / go.
	const float Step = 13.f * U;
	const float Radius = 5.5f * U;
	for (int32 Digit = 1; Digit <= 9; ++Digit)
	{
		const int32 Row = (Digit - 1) / 3;
		const int32 Column = (Digit - 1) % 3;
		RoundButton(EGolfHudButton::KeypadDigit, FVector2D(Center.X + (Column - 1) * Step, Center.Y - 12.f * U + Row * Step), Radius,
			FString::FromInt(Digit), Palette::PanelSolid, Digit);
	}
	const float LastRow = Center.Y - 12.f * U + 3.f * Step;
	RoundButton(EGolfHudButton::KeypadDelete, FVector2D(Center.X - Step, LastRow), Radius, TEXT("DEL"), Palette::PanelSolid);
	RoundButton(EGolfHudButton::KeypadDigit, FVector2D(Center.X, LastRow), Radius, TEXT("0"), Palette::PanelSolid, 0);
	RoundButton(EGolfHudButton::KeypadGo, FVector2D(Center.X + Step, LastRow), Radius, TEXT("GO"),
		Code.Len() == 4 ? FLinearColor(0.1f, 0.55f, 0.2f, 1.f) : Palette::PanelSolid);
	RoundButton(EGolfHudButton::KeypadCancel, FVector2D(Center.X + 29.f * U, Center.Y - 38.f * U), 3.5f * U, TEXT("X"), Palette::PanelSolid);
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
	Label(TEXT("INVITE FRIENDS"), FVector2D(Left + Width * 0.5f, 17.f * U), 3.5f, Palette::Trim, true);

	const TArray<FGolfFriend>& Friends = Sessions->GetFriends();
	if (Friends.Num() == 0)
	{
		Label(TEXT("No friends found yet"), FVector2D(Left + Width * 0.5f, 40.f * U), 3.f, Palette::Dim, true);
		return;
	}
	float Y = 24.f * U;
	for (int32 Index = 0; Index < Friends.Num() && Index < 8; ++Index)
	{
		const FGolfFriend& Friend = Friends[Index];
		Disc(FVector2D(Left + 3.f * U, Y + 2.f * U), 0.9f * U, Friend.bOnline ? Palette::Green : Palette::Dim);
		Label(Friend.Name.Left(16), FVector2D(Left + 5.5f * U, Y), 3.f, Friend.bOnline ? Palette::White : Palette::Dim, false);
		RoundButton(EGolfHudButton::Friend, FVector2D(Left + Width - 5.f * U, Y + 2.f * U), 3.f * U, TEXT("+"), Palette::PanelSolid, Index);
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
	Box(Center - FVector2D(40.f * U, 16.f * U), FVector2D(80.f * U, 32.f * U), Palette::PanelSolid);
	Label(FString::Printf(TEXT("%s invited you to play"), *Sessions->GetPendingInviteFrom()), Center - FVector2D(0.f, 9.f * U), 4.f, Palette::White, true);
	RoundButton(EGolfHudButton::AcceptInvite, Center + FVector2D(-12.f * U, 5.f * U), 6.5f * U, TEXT("JOIN"), FLinearColor(0.1f, 0.55f, 0.2f, 1.f));
	RoundButton(EGolfHudButton::DeclineInvite, Center + FVector2D(12.f * U, 5.f * U), 6.5f * U, TEXT("LATER"), Palette::Panel);
}

void AGolfHUD::DrawPlaying(AGolfGameState* State, AGolfPlayerController* Controller)
{
	if (Controller->IsMyTurn())
	{
		DrawGreenGrid(Controller);
		DrawPreview(Controller);
	}
	DrawHoleCard(State);
	DrawPlayers(State);
	DrawWind(State);

	if (const AGolfPlayerState* Active = Cast<AGolfPlayerState>(State->ActivePlayer); Active && Active->Ball)
	{
		const FVector2D LiePos(Canvas->ClipX - 12.f * U, 24.f * U);
		Label(GolfPhysics::LieName(Active->Ball->GetLie()), LiePos, 3.2f, Palette::Gold, true);
	}

	if (Controller->IsMyTurn())
	{
		DrawClubDisc(Controller);
		DrawPowerMeter(Controller);
	}
	if (Controller->IsDriving())
	{
		DrawDriving(Controller);
	}
}

void AGolfHUD::DrawDriving(AGolfPlayerController* Controller)
{
	const AGolfBuggy* Buggy = Controller->GetMyBuggy();
	const AGolfBall* Ball = Controller->GetMyBall();
	if (!Buggy || !Ball)
	{
		return;
	}

	// Direction and distance to the ball, top centre. Screen-up is where the camera looks.
	const FVector2D Compass(Canvas->ClipX * 0.5f, 9.f * U);
	Disc(Compass, 6.f * U, Palette::Panel);
	Ring(Compass, 6.f * U, Palette::Trim, 0.3f * U);
	const FVector ToBall = Ball->GetRestLocation() - Buggy->GetActorLocation();
	const float CameraYaw = PlayerOwner->PlayerCameraManager ? PlayerOwner->PlayerCameraManager->GetCameraRotation().Yaw : Buggy->GetActorRotation().Yaw;
	const float Bearing = FMath::DegreesToRadians(ToBall.Rotation().Yaw - CameraYaw);
	const FVector2D Dir(FMath::Sin(Bearing), -FMath::Cos(Bearing));
	const FVector2D Side(-Dir.Y, Dir.X);
	const FVector2D Tip = Compass + Dir * 4.5f * U;
	Line(Compass - Dir * 3.f * U, Tip, Palette::Green, 0.6f * U);
	Line(Tip, Tip - Dir * 1.8f * U + Side * 1.4f * U, Palette::Green, 0.6f * U);
	Line(Tip, Tip - Dir * 1.8f * U - Side * 1.4f * U, Palette::Green, 0.6f * U);
	Label(FString::Printf(TEXT("BALL  %.0f m"), Controller->GetDistanceToBall()), Compass + FVector2D(0.f, 9.f * U), 3.2f, Palette::White, true);

	// Marker over the ball when it is in view.
	FVector2D BallScreen;
	if (ToScreen(Ball->GetRestLocation() + FVector(0.f, 0.f, 120.f), BallScreen))
	{
		Ring(BallScreen, 1.4f * U, Palette::Green, 0.4f * U);
		Line(BallScreen + FVector2D(0.f, 1.4f * U), BallScreen + FVector2D(0.f, 4.f * U), Palette::Green, 0.3f * U);
	}

	// Steering pad on the left: the knob follows the thumb.
	const FVector2D Pad(18.f * U, Canvas->ClipY - 18.f * U);
	Box(Pad - FVector2D(12.f * U, 1.f * U), FVector2D(24.f * U, 2.f * U), Palette::Panel);
	Disc(Pad + FVector2D(Controller->GetDriveSteer() * 11.f * U, 0.f), 3.2f * U, FLinearColor(1.f, 1.f, 1.f, 0.85f));
	Label(TEXT("DRAG TO STEER"), Pad + FVector2D(0.f, 6.f * U), 2.4f, Palette::Dim, true);

	// Pedals on the right.
	RoundButton(EGolfHudButton::Throttle, FVector2D(Canvas->ClipX - 14.f * U, Canvas->ClipY - 16.f * U), 10.f * U, TEXT("GO"), FLinearColor(0.1f, 0.4f, 0.12f, 0.9f));
	RoundButton(EGolfHudButton::Reverse, FVector2D(Canvas->ClipX - 33.f * U, Canvas->ClipY - 10.f * U), 6.f * U, TEXT("REV"), Palette::PanelSolid);
	Label(FString::Printf(TEXT("%.0f km/h"), FMath::Abs(Buggy->GetSpeed()) * 0.036f), FVector2D(Canvas->ClipX - 14.f * U, Canvas->ClipY - 30.f * U), 3.f, Palette::White, true);

	RoundButton(EGolfHudButton::SkipDrive, FVector2D(Canvas->ClipX - 12.f * U, 36.f * U), 4.5f * U, TEXT("SKIP"), Palette::PanelSolid);
	if (Controller->CanPlayShotFromBuggy())
	{
		RoundButton(EGolfHudButton::PlayShot, FVector2D(Canvas->ClipX * 0.5f, Canvas->ClipY - 14.f * U), 9.f * U, TEXT("PLAY SHOT"), FLinearColor(0.1f, 0.45f, 0.15f, 0.95f));
	}
	else
	{
		Label(TEXT("Drive within 15 m of your ball"), FVector2D(Canvas->ClipX * 0.5f, Canvas->ClipY - 5.f * U), 2.6f, Palette::Dim, true);
	}
}

void AGolfHUD::DrawHoleCard(AGolfGameState* State)
{
	const AGolfHole* Hole = State->CurrentHole;
	if (!Hole)
	{
		return;
	}
	Box(FVector2D(2.f * U, 2.f * U), FVector2D(40.f * U, 15.f * U), Palette::Panel);
	Line(FVector2D(2.f * U, 17.f * U), FVector2D(42.f * U, 17.f * U), Palette::Trim, 0.4f * U);
	Label(FString::Printf(TEXT("%d"), State->HoleIndex + 1), FVector2D(4.f * U, 3.f * U), 10.f, Palette::Gold, false);
	Label(Hole->HoleName.ToUpper(), FVector2D(15.f * U, 3.5f * U), 3.6f, Palette::White, false);
	Label(FString::Printf(TEXT("PAR %d"), Hole->Par), FVector2D(15.f * U, 8.f * U), 3.2f, Palette::Trim, false);

	if (const AGolfPlayerState* Active = Cast<AGolfPlayerState>(State->ActivePlayer); Active && Active->Ball)
	{
		const float Meters = FVector::Dist2D(Active->Ball->GetRestLocation(), Hole->GetCupLocation()) / 100.f;
		const FString PinDistance = Meters < 1.f
			? FString::Printf(TEXT("PIN %.0f cm"), Meters * 100.f)
			: (Meters < 10.f ? FString::Printf(TEXT("PIN %.1f m"), Meters) : FString::Printf(TEXT("PIN %.0f m"), Meters));
		Label(PinDistance, FVector2D(15.f * U, 12.f * U), 3.2f, Palette::White, false);
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
		Box(FVector2D(2.f * U, Y), FVector2D(40.f * U, 4.6f * U), bActive ? FLinearColor(0.05f, 0.3f, 0.5f, 0.85f) : Palette::Panel);

		const int32 ToPar = Player->GetToPar(State->Pars);
		const FString ToParText = ToPar == 0 ? TEXT("E") : FString::Printf(TEXT("%+d"), ToPar);
		Label(Player->GetPlayerName().Left(12), FVector2D(3.5f * U, Y + 0.6f * U), 3.f, bActive ? Palette::Gold : Palette::White, false);
		Label(Player->bHoledOut ? TEXT("IN") : FString::Printf(TEXT("%d"), Player->Strokes), FVector2D(30.f * U, Y + 0.6f * U), 3.f, Palette::Dim, false);
		Label(ToParText, FVector2D(36.f * U, Y + 0.6f * U), 3.f, ToPar < 0 ? Palette::Red : Palette::White, false);
		Y += 5.2f * U;
	}
}

void AGolfHUD::DrawWind(AGolfGameState* State)
{
	const FVector2D Center(Canvas->ClipX - 12.f * U, 11.f * U);
	const float Radius = 8.f * U;
	Disc(Center, Radius, Palette::Panel);
	Ring(Center, Radius, Palette::Trim, 0.4f * U);

	const float Speed = State->Wind.Size2D() / 100.f;
	if (Speed > 0.05f && PlayerOwner && PlayerOwner->PlayerCameraManager)
	{
		// Screen-up is the camera's forward direction.
		const float Relative = FMath::DegreesToRadians(State->Wind.Rotation().Yaw - PlayerOwner->PlayerCameraManager->GetCameraRotation().Yaw);
		const FVector2D Dir(FMath::Sin(Relative), -FMath::Cos(Relative));
		const FVector2D Tip = Center + Dir * Radius * 0.75f;
		const FVector2D Tail = Center - Dir * Radius * 0.55f;
		const FVector2D Side(-Dir.Y, Dir.X);
		Line(Tail, Tip, Palette::Gold, 0.7f * U);
		Line(Tip, Tip - Dir * 2.f * U + Side * 1.6f * U, Palette::Gold, 0.7f * U);
		Line(Tip, Tip - Dir * 2.f * U - Side * 1.6f * U, Palette::Gold, 0.7f * U);
	}
	Label(FString::Printf(TEXT("%.1fm"), Speed), Center + FVector2D(0.f, Radius + 2.5f * U), 3.f, Palette::White, true);
}

void AGolfHUD::DrawGreenGrid(AGolfPlayerController* Controller)
{
	// Slope arrows point downhill. White is nearly flat, amber is a few percent, red is steep.
	const TArray<FVector>& Points = Controller->GetGreenGridPoints();
	const TArray<FVector>& Slopes = Controller->GetGreenGridSlopes();
	for (int32 Index = 0; Index < Points.Num() && Index < Slopes.Num(); ++Index)
	{
		const float Percent = Slopes[Index].Size() * 100.f;
		const FLinearColor Color = Percent < 1.f ? FLinearColor(1.f, 1.f, 1.f, 0.45f)
			: Percent < 3.f ? FLinearColor(1.f, 0.8f, 0.3f, 0.8f) : FLinearColor(1.f, 0.3f, 0.2f, 0.9f);

		FVector2D From;
		if (!ToScreen(Points[Index] + FVector(0.f, 0.f, 1.f), From))
		{
			continue;
		}
		Disc(From, 0.25f * U, Color);
		if (Percent >= 0.3f)
		{
			const FVector Tip = Points[Index] + Slopes[Index].GetSafeNormal() * FMath::Clamp(Percent * 8.f, 12.f, 45.f) + FVector(0.f, 0.f, 1.f);
			FVector2D To;
			if (ToScreen(Tip, To))
			{
				Line(From, To, Color, 0.25f * U);
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
			Line(Previous, Screen, Controller->IsSwinging() ? Palette::Green : Palette::White, 0.4f * U);
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
	const FVector2D Center(15.f * U, Canvas->ClipY - 16.f * U);
	const float Radius = 12.f * U;
	Disc(Center, Radius, Palette::PanelSolid);
	Ring(Center, Radius, Palette::Trim, 0.6f * U);
	Ring(Center, Radius * 0.82f, FLinearColor(0.2f, 0.85f, 1.f, 0.35f), 0.3f * U);
	Label(Bag[Index].ShortName, Center - FVector2D(0.f, 2.f * U), 8.f, Palette::White, true);
	Label(FString::Printf(TEXT("%.0f m"), Controller->GetClubCarry(Index) / 100.f), Center + FVector2D(0.f, 5.5f * U), 3.f, Palette::Gold, true);
	Buttons.Add({ EGolfHudButton::Club, Center, Radius, 0 });

	RoundButton(EGolfHudButton::Spin, FVector2D(34.f * U, Canvas->ClipY - 8.f * U), 6.f * U, Controller->GetSpinLabel(), Palette::PanelSolid);
}

void AGolfHUD::DrawPowerMeter(AGolfPlayerController* Controller)
{
	using PC = AGolfPlayerController;

	// Swipe track on the right: fills as the finger travels up. The swipe itself can start anywhere low on screen.
	const float Bottom = Canvas->ClipY - 8.f * U;
	const float Length = PC::FullPowerSwipe * Canvas->ClipY;
	const float CenterX = Canvas->ClipX - 9.f * U;
	const float Width = 2.4f * U;
	const float Power = Controller->GetSwingPower();

	Box(FVector2D(CenterX - Width * 0.5f, Bottom - Length), FVector2D(Width, Length), Palette::Panel);
	for (const float Notch : { 0.25f, 0.5f, 0.75f, 1.f })
	{
		const float Y = Bottom - Length * Notch;
		Line(FVector2D(CenterX - Width, Y), FVector2D(CenterX + Width, Y), Palette::Dim, 0.2f * U);
	}
	if (Power > 0.f)
	{
		Box(FVector2D(CenterX - Width * 0.5f, Bottom - Length * Power), FVector2D(Width, Length * Power), FLinearColor(0.45f, 0.85f, 0.3f, 0.85f));
	}

	// Straightness: the marker slides left or right as the swipe drifts.
	const float Accuracy = Controller->GetSwingAccuracy();
	const FVector2D Straight(CenterX, Bottom + 3.f * U);
	Line(Straight - FVector2D(4.f * U, 0.f), Straight + FVector2D(4.f * U, 0.f), Palette::Dim, 0.2f * U);
	if (Controller->IsSwinging())
	{
		Disc(Straight + FVector2D(Accuracy * 4.f * U, 0.f), 0.8f * U, FMath::IsNearlyZero(Accuracy) ? Palette::Green : Palette::Red);
	}

	const FString Text = Controller->IsSwinging() ? FString::Printf(TEXT("%d%%"), FMath::RoundToInt(Power * 100.f)) : TEXT("SWIPE UP");
	Label(Text, FVector2D(CenterX, Bottom - Length - 3.f * U), 2.8f, Palette::White, true);

	if (!Controller->IsSwinging())
	{
		Label(TEXT("Swipe up from the bottom to swing  ·  drag the top to aim"), FVector2D(Canvas->ClipX * 0.5f, Canvas->ClipY - 4.f * U), 2.6f, Palette::Dim, true);
	}
	if (GetWorld()->GetTimeSeconds() - Controller->GetPerfectFlashTime() < 1.2f)
	{
		Label(TEXT("PURE STRIKE"), FVector2D(Canvas->ClipX * 0.5f, Canvas->ClipY * 0.42f), 6.f, Palette::White, true);
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
	const float TotalWidth = 9.f * U;
	const float Cell = (Width - NameWidth - TotalWidth) / Holes;
	const float Row = 6.f * U;
	float Y = 30.f * U;

	TArray<AGolfPlayerState*> Players;
	for (APlayerState* Base : State->PlayerArray)
	{
		if (AGolfPlayerState* Player = Cast<AGolfPlayerState>(Base); Player && Player->bInRound)
		{
			Players.Add(Player);
		}
	}

	Box(FVector2D(Left, Y), FVector2D(Width, Row * (2 + Players.Num())), FLinearColor(0.95f, 0.93f, 0.85f, 0.95f));
	const FLinearColor Ink(0.08f, 0.12f, 0.2f, 1.f);
	const FLinearColor Rule(0.6f, 0.62f, 0.6f, 1.f);
	auto CellCenter = [&](int32 Column, float RowY) { return FVector2D(Left + NameWidth + Cell * (Column + 0.5f), RowY + Row * 0.5f); };

	// Header rows: hole numbers and par.
	Label(TEXT("HOLE"), FVector2D(Left + U, Y + U), 3.f, Ink, false);
	Label(TEXT("PAR"), FVector2D(Left + U, Y + Row + U), 3.f, Ink, false);
	int32 ParTotal = 0;
	for (int32 Hole = 0; Hole < Holes; ++Hole)
	{
		const bool bCurrent = Hole == State->HoleIndex;
		Label(FString::Printf(TEXT("%d"), Hole + 1), CellCenter(Hole, Y), 2.8f, bCurrent ? Palette::Red : Ink, true);
		Label(FString::Printf(TEXT("%d"), State->Pars[Hole]), CellCenter(Hole, Y + Row), 2.8f, Ink, true);
		ParTotal += State->Pars[Hole];
	}
	Label(TEXT("TOT"), FVector2D(Left + Width - TotalWidth * 0.5f, Y + Row * 0.5f), 2.8f, Ink, true);
	Label(FString::Printf(TEXT("%d"), ParTotal), FVector2D(Left + Width - TotalWidth * 0.5f, Y + Row * 1.5f), 2.8f, Ink, true);

	// Player rows. Birdie or better is circled and bogey or worse boxed, as on a paper card.
	float RowY = Y + Row * 2.f;
	for (AGolfPlayerState* Player : Players)
	{
		Line(FVector2D(Left, RowY), FVector2D(Left + Width, RowY), Rule, 1.f);
		Label(Player->GetPlayerName().Left(10), FVector2D(Left + U, RowY + U), 3.f, Ink, false);
		for (int32 Hole = 0; Hole < Holes && Hole < Player->HoleScores.Num(); ++Hole)
		{
			const int32 Score = Player->HoleScores[Hole];
			if (Score <= 0)
			{
				continue;
			}
			const FVector2D Center = CellCenter(Hole, RowY);
			const int32 Diff = Score - State->Pars[Hole];
			const float Mark = FMath::Min(Cell, Row) * 0.4f;
			if (Diff < 0)
			{
				Ring(Center, Mark, Ink, 1.5f);
				if (Diff < -1) Ring(Center, Mark * 1.25f, Ink, 1.5f);
			}
			else if (Diff > 0)
			{
				auto Square = [&](float S)
				{
					Line(Center + FVector2D(-S, -S), Center + FVector2D(S, -S), Ink, 1.5f);
					Line(Center + FVector2D(S, -S), Center + FVector2D(S, S), Ink, 1.5f);
					Line(Center + FVector2D(S, S), Center + FVector2D(-S, S), Ink, 1.5f);
					Line(Center + FVector2D(-S, S), Center + FVector2D(-S, -S), Ink, 1.5f);
				};
				Square(Mark);
				if (Diff > 1) Square(Mark * 1.25f);
			}
			Label(FString::Printf(TEXT("%d"), Score), Center, 2.8f, Ink, true);
		}
		const int32 ToPar = Player->GetToPar(State->Pars);
		Label(FString::Printf(TEXT("%d (%s)"), Player->GetTotalStrokes(), ToPar == 0 ? TEXT("E") : *FString::Printf(TEXT("%+d"), ToPar)),
			FVector2D(Left + Width - TotalWidth * 0.5f, RowY + Row * 0.5f), 2.6f, Ink, true);
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
	Box(FVector2D(Canvas->ClipX * 0.25f, Center.Y - 4.5f * U), FVector2D(Canvas->ClipX * 0.5f, 9.f * U), FLinearColor(0.02f, 0.05f, 0.16f, 0.7f * Alpha));
	Label(State->Announcement, Center, 5.f, FLinearColor(1.f, 0.82f, 0.25f, Alpha), true);
}
