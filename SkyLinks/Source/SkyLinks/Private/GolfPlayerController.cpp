#include "GolfPlayerController.h"
#include "SkyLinks.h"
#include "GolfBall.h"
#include "GolfCharacter.h"
#include "GolfGameMode.h"
#include "GolfGameState.h"
#include "GolfHole.h"
#include "GolfHUD.h"
#include "GolfPhysics.h"
#include "GolfPlayerState.h"
#include "GolfSessionSubsystem.h"
#include "Components/InputComponent.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"

namespace
{
	constexpr float RiseSeconds = 1.0f;       // 0 -> 100% power
	constexpr float ReturnSeconds = 0.7f;     // 100% -> impact point
	constexpr float AimDegreesPerPixel = 0.08f;
	constexpr float KeyAimDegreesPerSecond = 40.f;

	const FVector2D SpinPresets[] = { { 0.f, 0.f }, { 0.f, -1.f }, { 0.f, 1.f } };
	const TCHAR* SpinLabels[] = { TEXT("SPIN"), TEXT("BACK"), TEXT("TOP") };
}

AGolfPlayerController::AGolfPlayerController()
{
	PrimaryActorTick.bCanEverTick = true;
	bShowMouseCursor = true;
}

void AGolfPlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();

	InputComponent->BindTouch(IE_Pressed, this, &AGolfPlayerController::OnTouchPressed);
	InputComponent->BindTouch(IE_Repeat, this, &AGolfPlayerController::OnTouchMoved);
	InputComponent->BindTouch(IE_Released, this, &AGolfPlayerController::OnTouchReleased);

	InputComponent->BindKey(EKeys::SpaceBar, IE_Pressed, this, &AGolfPlayerController::OnSwingKey);
	InputComponent->BindKey(EKeys::E, IE_Pressed, this, &AGolfPlayerController::OnNextClub);
	InputComponent->BindKey(EKeys::Q, IE_Pressed, this, &AGolfPlayerController::OnPrevClub);
	InputComponent->BindKey(EKeys::R, IE_Pressed, this, &AGolfPlayerController::OnSpinKey);
	InputComponent->BindKey(EKeys::A, IE_Pressed, this, &AGolfPlayerController::OnAimLeftPressed);
	InputComponent->BindKey(EKeys::A, IE_Released, this, &AGolfPlayerController::OnAimLeftReleased);
	InputComponent->BindKey(EKeys::D, IE_Pressed, this, &AGolfPlayerController::OnAimRightPressed);
	InputComponent->BindKey(EKeys::D, IE_Released, this, &AGolfPlayerController::OnAimRightReleased);
}

AGolfGameState* AGolfPlayerController::GetGolfState() const
{
	return GetWorld() ? GetWorld()->GetGameState<AGolfGameState>() : nullptr;
}

AGolfBall* AGolfPlayerController::GetMyBall() const
{
	const AGolfPlayerState* GolfState = GetPlayerState<AGolfPlayerState>();
	return GolfState ? GolfState->Ball.Get() : nullptr;
}

AGolfCharacter* AGolfPlayerController::GetMyGolfer() const
{
	return GetPawn<AGolfCharacter>();
}

bool AGolfPlayerController::IsMyTurn() const
{
	const AGolfGameState* State = GetGolfState();
	const AGolfBall* Ball = GetMyBall();
	return State && Ball && State->Phase == EGolfMatchPhase::PlayingHole && State->ActivePlayer == PlayerState && Ball->IsAtRest();
}

FString AGolfPlayerController::GetSpinLabel() const
{
	return SpinLabels[SpinPreset];
}

void AGolfPlayerController::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!IsLocalController())
	{
		return;
	}

	const bool bMyTurn = IsMyTurn();
	if (bMyTurn)
	{
		// A new turn, or the golfer walked to a new spot (the address replicates a moment after the turn).
		const AGolfCharacter* Golfer = GetMyGolfer();
		const FVector BallSpot = Golfer ? Golfer->GetAddressBallLocation() : FVector::ZeroVector;
		if (!bWasMyTurn || FVector::DistSquared(BallSpot, LastTurnBall) > 1.f)
		{
			LastTurnBall = BallSpot;
			OnTurnStarted();
		}
	}
	else
	{
		Gauge = EGauge::Idle;
		bHasPreview = false;
	}
	bWasMyTurn = bMyTurn;
	if (!bMyTurn)
	{
		return;
	}

	if (AimInput != 0.f && Gauge == EGauge::Idle)
	{
		SetAim(AimYaw + AimInput * KeyAimDegreesPerSecond * DeltaSeconds);
	}

	switch (Gauge)
	{
	case EGauge::Rising:
		GaugePos += GaugeDirection * DeltaSeconds / RiseSeconds;
		if (GaugePos >= GaugeMax)
		{
			GaugePos = GaugeMax;
			GaugeDirection = -1.f;
		}
		else if (GaugePos <= 0.f && GaugeDirection < 0.f)
		{
			Gauge = EGauge::Idle; // Never set the power: cancel.
			GaugePos = 0.f;
		}
		break;

	case EGauge::Returning:
		GaugePos -= DeltaSeconds / ReturnSeconds;
		if (GaugePos <= GaugeMin)
		{
			Fire(-1.f); // Missed the impact tap: a full hook.
		}
		break;

	default:
		break;
	}

	PreviewCooldown -= DeltaSeconds;
	if (bPreviewDirty && PreviewCooldown <= 0.f)
	{
		RefreshPreview();
	}
}

void AGolfPlayerController::OnTurnStarted()
{
	Gauge = EGauge::Idle;
	GaugePos = 0.f;

	const AGolfBall* Ball = GetMyBall();
	const AGolfGameState* State = GetGolfState();
	const AGolfCharacter* Golfer = GetMyGolfer();
	if (!Ball || !State || !State->CurrentHole)
	{
		return;
	}
	AimYaw = Golfer ? Golfer->GetAimYaw() : 0.f;

	// Club carries from this lie, then pick the shortest club that reaches the pin.
	const TArray<FGolfClub>& Bag = GolfPhysics::GetClubBag();
	const EGolfLie Lie = Ball->GetLie();
	ClubCarry.SetNum(Bag.Num());
	for (int32 Index = 0; Index < Bag.Num(); ++Index)
	{
		ClubCarry[Index] = GolfPhysics::FlatCarry(Bag[Index], Lie);
	}

	if (Lie == EGolfLie::Green)
	{
		ClubIndex = GolfPhysics::GetPutterIndex();
	}
	else
	{
		const float ToPin = FVector::Dist2D(Ball->GetRestLocation(), State->CurrentHole->GetCupLocation());
		ClubIndex = 0;
		for (int32 Index = Bag.Num() - 1; Index >= 0; --Index)
		{
			if (!Bag[Index].bIsPutter && ClubCarry[Index] >= ToPin * 0.9f)
			{
				ClubIndex = Index;
				break;
			}
		}
	}
	bPreviewDirty = true;
}

void AGolfPlayerController::SetAim(float Yaw)
{
	AimYaw = FRotator::NormalizeAxis(Yaw);
	if (AGolfCharacter* Golfer = GetMyGolfer())
	{
		Golfer->SetLocalAim(AimYaw);
	}
	bPreviewDirty = true;
}

void AGolfPlayerController::CycleClub(int32 Direction)
{
	if (!IsMyTurn() || Gauge != EGauge::Idle)
	{
		return;
	}
	const int32 Count = GolfPhysics::GetClubBag().Num();
	ClubIndex = (ClubIndex + Direction + Count) % Count;
	bPreviewDirty = true;
}

void AGolfPlayerController::CycleSpin()
{
	if (!IsMyTurn() || Gauge != EGauge::Idle)
	{
		return;
	}
	SpinPreset = (SpinPreset + 1) % UE_ARRAY_COUNT(SpinPresets);
	Spin = SpinPresets[SpinPreset];
	bPreviewDirty = true;
}

void AGolfPlayerController::GaugeTap()
{
	if (!IsMyTurn())
	{
		return;
	}
	switch (Gauge)
	{
	case EGauge::Idle:
		Gauge = EGauge::Rising;
		GaugePos = 0.f;
		GaugeDirection = 1.f;
		break;

	case EGauge::Rising:
		GaugePower = FMath::Max(GaugePos, 0.02f);
		Gauge = EGauge::Returning;
		break;

	case EGauge::Returning:
		if (FMath::Abs(GaugePos) <= PerfectWindow)
		{
			PerfectFlashTime = GetWorld()->GetTimeSeconds();
			Fire(0.f);
		}
		else
		{
			// Early (still right of the impact point) pushes and slices; late hooks.
			Fire(FMath::Clamp(GaugePos / ImpactWindow, -1.f, 1.f));
		}
		break;
	}
}

void AGolfPlayerController::Fire(float Accuracy)
{
	FGolfShotInput Input;
	Input.AimYaw = AimYaw;
	Input.Power = GaugePower;
	Input.Accuracy = Accuracy;
	Input.ClubIndex = ClubIndex;
	Input.Spin = Spin;
	ServerTakeShot(Input);

	Gauge = EGauge::Idle;
	GaugePos = 0.f;
	bHasPreview = false;
}

void AGolfPlayerController::RefreshPreview()
{
	bPreviewDirty = false;
	PreviewCooldown = 0.1f;

	AGolfBall* Ball = GetMyBall();
	const TArray<FGolfClub>& Bag = GolfPhysics::GetClubBag();
	if (!Ball || !Bag.IsValidIndex(ClubIndex))
	{
		bHasPreview = false;
		return;
	}

	const FGolfClub& Club = Bag[ClubIndex];
	const FVector Start = Ball->GetRestLocation() + FVector(0.f, 0.f, 0.5f);
	if (Club.bIsPutter)
	{
		const FVector Direction = FRotator(0.f, AimYaw, 0.f).Vector();
		PreviewLanding = Start + Direction * GolfPhysics::PuttDistance(Club.LaunchSpeed);
		PreviewPath = { Start, PreviewLanding };
	}
	else
	{
		FGolfShotInput Input;
		Input.AimYaw = AimYaw;
		Input.Power = 1.f;
		Input.ClubIndex = ClubIndex;
		Input.Spin = Spin;
		GolfPhysics::PredictCarry(GetWorld(), GolfPhysics::MakeLaunch(Club, Input, Ball->GetLie(), Start), Ball, PreviewPath, PreviewLanding);
	}
	bHasPreview = true;
}

void AGolfPlayerController::OnTouchPressed(ETouchIndex::Type FingerIndex, FVector Location)
{
	if (FingerIndex != ETouchIndex::Touch1)
	{
		return;
	}
	const FVector2D Screen(Location.X, Location.Y);
	const AGolfHUD* Hud = GetHUD<AGolfHUD>();
	UGolfSessionSubsystem* Sessions = GetGameInstance()->GetSubsystem<UGolfSessionSubsystem>();
	int32 Payload = 0;
	switch (Hud ? Hud->HitTest(Screen, Payload) : EGolfHudButton::None)
	{
	case EGolfHudButton::Start: ServerRequestStart(); return;
	case EGolfHudButton::Host:  HostGame(); return;
	case EGolfHudButton::Join:
		bKeypadOpen = true;
		EnteredCode.Reset();
		return;
	case EGolfHudButton::KeypadDigit:
		if (EnteredCode.Len() < 4)
		{
			EnteredCode.AppendInt(Payload);
		}
		return;
	case EGolfHudButton::KeypadDelete:
		EnteredCode.LeftChopInline(1);
		return;
	case EGolfHudButton::KeypadGo:
		if (EnteredCode.Len() == 4)
		{
			bKeypadOpen = false;
			JoinGame(EnteredCode);
		}
		return;
	case EGolfHudButton::KeypadCancel:
		bKeypadOpen = false;
		return;
	case EGolfHudButton::Friends:
		bFriendsOpen = !bFriendsOpen;
		if (bFriendsOpen && Sessions)
		{
			Sessions->RefreshFriends();
		}
		return;
	case EGolfHudButton::Friend:
		if (Sessions)
		{
			Sessions->InviteFriend(Payload);
		}
		return;
	case EGolfHudButton::AcceptInvite:
		if (Sessions)
		{
			Sessions->AcceptPendingInvite();
		}
		return;
	case EGolfHudButton::DeclineInvite:
		if (Sessions)
		{
			Sessions->DeclinePendingInvite();
		}
		return;
	case EGolfHudButton::Club:  CycleClub(1); return;
	case EGolfHudButton::Spin:  CycleSpin(); return;
	case EGolfHudButton::Swing: GaugeTap(); return;
	default: break;
	}

	if (Gauge != EGauge::Idle)
	{
		GaugeTap();
		return;
	}
	bDragging = true;
	DragLastX = Screen.X;
}

void AGolfPlayerController::OnTouchMoved(ETouchIndex::Type FingerIndex, FVector Location)
{
	if (FingerIndex != ETouchIndex::Touch1 || !bDragging)
	{
		return;
	}
	if (IsMyTurn() && Gauge == EGauge::Idle)
	{
		SetAim(AimYaw + (Location.X - DragLastX) * AimDegreesPerPixel);
	}
	DragLastX = Location.X;
}

void AGolfPlayerController::OnTouchReleased(ETouchIndex::Type FingerIndex, FVector Location)
{
	if (FingerIndex == ETouchIndex::Touch1)
	{
		bDragging = false;
	}
}

void AGolfPlayerController::ServerTakeShot_Implementation(const FGolfShotInput& Input)
{
	if (AGolfGameMode* Mode = GetWorld()->GetAuthGameMode<AGolfGameMode>())
	{
		Mode->HandleShot(this, Input);
	}
}

void AGolfPlayerController::ServerRequestStart_Implementation()
{
	if (AGolfGameMode* Mode = GetWorld()->GetAuthGameMode<AGolfGameMode>())
	{
		Mode->RequestStartRound(this);
	}
}

void AGolfPlayerController::HostGame()
{
	if (UGolfSessionSubsystem* Sessions = GetGameInstance()->GetSubsystem<UGolfSessionSubsystem>())
	{
		Sessions->HostOnline();
	}
}

void AGolfPlayerController::JoinGame(const FString& RoomCode)
{
	if (UGolfSessionSubsystem* Sessions = GetGameInstance()->GetSubsystem<UGolfSessionSubsystem>())
	{
		Sessions->JoinByCode(RoomCode);
	}
}
