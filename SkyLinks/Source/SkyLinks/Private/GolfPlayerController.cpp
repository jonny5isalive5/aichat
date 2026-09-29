#include "GolfPlayerController.h"
#include "SkyLinks.h"
#include "GolfBall.h"
#include "GolfBuggy.h"
#include "GolfCharacter.h"
#include "GolfGameMode.h"
#include "GolfGameState.h"
#include "GolfHole.h"
#include "GolfHUD.h"
#include "GolfPhysics.h"
#include "GolfPlayerState.h"
#include "GolfSessionSubsystem.h"
#include "GolfVoiceSubsystem.h"
#include "Components/InputComponent.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "EngineUtils.h"

namespace
{
	constexpr float AimDegreesPerPixel = 0.08f;
	constexpr float KeyAimDegreesPerSecond = 40.f;
	constexpr float LandingViewMargin = 900.f; // cm of ground kept around the landing ring and the pin
	constexpr float KeyChargeSeconds = 1.2f;
	constexpr float MinShotPower = 0.03f;

	const FVector2D SpinPresets[] = { { 0.f, 0.f }, { 0.f, -1.f }, { 0.f, 1.f } };
	const TCHAR* SpinLabels[] = { TEXT("SPIN"), TEXT("BACK"), TEXT("TOP") };
	constexpr int32 MiniMapPixelsX = 256;
	constexpr int32 MiniMapPixelsY = 448;
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

	InputComponent->BindKey(EKeys::SpaceBar, IE_Pressed, this, &AGolfPlayerController::OnSwingKeyPressed);
	InputComponent->BindKey(EKeys::SpaceBar, IE_Released, this, &AGolfPlayerController::OnSwingKeyReleased);
	InputComponent->BindKey(EKeys::E, IE_Pressed, this, &AGolfPlayerController::OnUseKey);
	InputComponent->BindKey(EKeys::Q, IE_Pressed, this, &AGolfPlayerController::OnPrevClub);
	InputComponent->BindKey(EKeys::R, IE_Pressed, this, &AGolfPlayerController::OnSpinKey);
	InputComponent->BindKey(EKeys::A, IE_Pressed, this, &AGolfPlayerController::OnAimLeftPressed);
	InputComponent->BindKey(EKeys::A, IE_Released, this, &AGolfPlayerController::OnAimLeftReleased);
	InputComponent->BindKey(EKeys::D, IE_Pressed, this, &AGolfPlayerController::OnAimRightPressed);
	InputComponent->BindKey(EKeys::D, IE_Released, this, &AGolfPlayerController::OnAimRightReleased);
	InputComponent->BindKey(EKeys::W, IE_Pressed, this, &AGolfPlayerController::OnThrottleForwardPressed);
	InputComponent->BindKey(EKeys::W, IE_Released, this, &AGolfPlayerController::OnThrottleForwardReleased);
	InputComponent->BindKey(EKeys::S, IE_Pressed, this, &AGolfPlayerController::OnThrottleBackPressed);
	InputComponent->BindKey(EKeys::S, IE_Released, this, &AGolfPlayerController::OnThrottleBackReleased);
	InputComponent->BindKey(EKeys::F, IE_Pressed, this, &AGolfPlayerController::OnPlayShotKey);
	InputComponent->BindKey(EKeys::M, IE_Pressed, this, &AGolfPlayerController::ToggleMicrophone);
}

void AGolfPlayerController::ToggleMicrophone()
{
	if (IsLocalController()) GetGameInstance()->GetSubsystem<UGolfVoiceSubsystem>()->ToggleMicrophone();
}

void AGolfPlayerController::ClientEnableNetworkVoice_Implementation(bool bEnable)
{
	// Travel must not let the engine's open-mic handshake undo a player's mute preference.
	GetGameInstance()->GetSubsystem<UGolfVoiceSubsystem>()->Refresh(true);
}

void AGolfPlayerController::TogglePlayerVoiceMute(int32 PlayerId)
{
	if (!IsLocalController()) return;
	if (const AGolfGameState* State = GetGolfState())
	{
		for (const APlayerState* RemotePlayer : State->PlayerArray)
		{
			if (RemotePlayer && RemotePlayer != PlayerState && RemotePlayer->GetPlayerId() == PlayerId)
			{
				GetGameInstance()->GetSubsystem<UGolfVoiceSubsystem>()->TogglePlayerMute(RemotePlayer);
				break;
			}
		}
	}
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
	const AGolfPlayerState* GolfState = GetPlayerState<AGolfPlayerState>();
	return GolfState ? GolfState->Golfer.Get() : nullptr;
}

AGolfBuggy* AGolfPlayerController::GetMyBuggy() const
{
	const AGolfPlayerState* GolfState = GetPlayerState<AGolfPlayerState>();
	return GolfState ? GolfState->Buggy.Get() : nullptr;
}

bool AGolfPlayerController::IsDriving() const
{
	return GetPawn() && GetPawn() == GetMyBuggy();
}

bool AGolfPlayerController::IsWalking() const
{
	const AGolfCharacter* Golfer = GetMyGolfer();
	return Golfer && GetPawn() == Golfer && Golfer->IsRoaming();
}

bool AGolfPlayerController::IsTravelling() const
{
	const AGolfGameState* State = GetGolfState();
	return State && State->Phase == EGolfMatchPhase::PlayingHole && State->bActiveDriving && State->ActivePlayer == PlayerState;
}

AGolfBuggy* AGolfPlayerController::GetBuggyInReach() const
{
	const AGolfCharacter* Golfer = GetMyGolfer();
	const AGolfGameState* State = GetGolfState();
	if (!IsWalking() || !State)
	{
		return nullptr;
	}
	// Mirrors AGolfGameMode::FindBuggyToEnter: my own buggy, or before / after a round any nobody has picked.
	const bool bAnyFree = State->Phase == EGolfMatchPhase::Lobby || State->Phase == EGolfMatchPhase::RoundOver;
	AGolfBuggy* Best = nullptr;
	float BestDistance = AGolfBuggy::EnterReach;
	for (TActorIterator<AGolfBuggy> It(GetWorld()); It; ++It)
	{
		AGolfBuggy* Buggy = *It;
		bool bAllowed = Buggy == GetMyBuggy();
		if (!bAllowed && bAnyFree)
		{
			bAllowed = true;
			for (const APlayerState* Base : State->PlayerArray)
			{
				const AGolfPlayerState* Other = Cast<AGolfPlayerState>(Base);
				bAllowed &= !(Other && Other->Buggy == Buggy);
			}
		}
		const float Distance = FVector::Dist2D(Buggy->GetActorLocation(), Golfer->GetActorLocation());
		if (bAllowed && Distance <= BestDistance)
		{
			Best = Buggy;
			BestDistance = Distance;
		}
	}
	return Best;
}

float AGolfPlayerController::GetDistanceToBall() const
{
	const AGolfBall* Ball = GetMyBall();
	return GetPawn() && Ball ? FVector::Dist2D(GetPawn()->GetActorLocation(), Ball->GetRestLocation()) / 100.f : -1.f;
}

bool AGolfPlayerController::CanPlayShot() const
{
	const float Meters = GetDistanceToBall();
	return IsTravelling() && (IsDriving() || IsWalking()) && Meters >= 0.f && Meters * 100.f <= AGolfBuggy::ArriveDistance;
}

void AGolfPlayerController::OnPlayShotKey()
{
	if (CanPlayShot())
	{
		ServerFinishDriving(false);
	}
}

bool AGolfPlayerController::CanTeeUp() const
{
	const AGolfGameState* State = GetGolfState();
	const AGolfCharacter* Golfer = GetMyGolfer();
	if (!State || State->Phase != EGolfMatchPhase::Lobby || !IsHost() || !IsWalking() || !Golfer)
	{
		return false;
	}
	const AGolfHole* First = nullptr;
	for (TActorIterator<AGolfHole> It(GetWorld()); It; ++It)
	{
		if (!First || It->HoleNumber < First->HoleNumber)
		{
			First = *It;
		}
	}
	return First && FVector::Dist2D(First->GetTeeLocation(), Golfer->GetActorLocation()) <= AGolfGameMode::TeeUpReach;
}

void AGolfPlayerController::OnUseKey()
{
	if (IsMyTurn())
	{
		CycleClub(1); // At the ball, E still changes club.
	}
	else if (CanTeeUp())
	{
		ServerRequestStart();
	}
	else if (IsDriving() || GetBuggyInReach())
	{
		ServerToggleBuggy();
	}
}

void AGolfPlayerController::UpdateWalking()
{
	AGolfCharacter* Golfer = GetMyGolfer();
	if (!Golfer)
	{
		return;
	}
	// W/S and A/D (the keys also used for throttle and aim), plus the left-thumb stick; relative to the camera.
	FVector2D Stick(FMath::Clamp(AimInput, -1.f, 1.f) + TouchWalk.X, FMath::Clamp(KeyThrottle, -1.f, 1.f) + TouchWalk.Y);
	if (Stick.SizeSquared() > 1.f)
	{
		Stick.Normalize();
	}
	if (Stick.IsNearlyZero(0.05f))
	{
		return;
	}
	const float Yaw = PlayerCameraManager ? PlayerCameraManager->GetCameraRotation().Yaw : Golfer->GetActorRotation().Yaw;
	const FRotator Heading(0.f, Yaw, 0.f);
	Golfer->AddMovementInput(Heading.Vector() * Stick.Y + FRotationMatrix(Heading).GetUnitAxis(EAxis::Y) * Stick.X, 1.f);
}

float AGolfPlayerController::ViewportHeight() const
{
	int32 SizeX = 0, SizeY = 0;
	GetViewportSize(SizeX, SizeY);
	return FMath::Max(1, SizeY);
}

bool AGolfPlayerController::IsMyTurn() const
{
	const AGolfGameState* State = GetGolfState();
	const AGolfBall* Ball = GetMyBall();
	return State && Ball && State->Phase == EGolfMatchPhase::PlayingHole && State->ActivePlayer == PlayerState
		&& !State->bActiveDriving && Ball->IsAtRest();
}

bool AGolfPlayerController::IsPutting() const
{
	const TArray<FGolfClub>& Bag = GolfPhysics::GetClubBag();
	return Bag.IsValidIndex(ClubIndex) && Bag[ClubIndex].bIsPutter;
}

float AGolfPlayerController::GetIdlePreviewPower() const
{
	if (!IsPutting())
	{
		return 1.f;
	}

	const AGolfBall* Ball = GetMyBall();
	const AGolfGameState* State = GetGolfState();
	const TArray<FGolfClub>& Bag = GolfPhysics::GetClubBag();
	if (!Ball || !State || !State->CurrentHole || !Bag.IsValidIndex(ClubIndex))
	{
		return 1.f;
	}

	const float FullPowerDistance = GolfPhysics::PuttDistance(Bag[ClubIndex].LaunchSpeed);
	const float ToPin = FVector::Dist2D(Ball->GetRestLocation(), State->CurrentHole->GetCupLocation());
	return FullPowerDistance > KINDA_SMALL_NUMBER
		? FMath::Clamp(FMath::Sqrt(ToPin / FullPowerDistance), MinShotPower, 1.f)
		: 1.f;
}

UTextureRenderTarget2D* AGolfPlayerController::GetLandingViewTexture() const
{
	return bLandingView && bHasPreview && LandingCapture && LandingCapture->bCaptureEveryFrame ? LandingTarget.Get() : nullptr;
}

void AGolfPlayerController::UpdateLandingCapture()
{
	// The main camera stays behind the golfer so aiming works as normal; the overhead view of the
	// landing area is rendered into a small window on the HUD instead.
	const bool bWanted = bLandingView && bHasPreview && IsMyTurn();
	if (!bWanted)
	{
		if (LandingCapture)
		{
			LandingCapture->bCaptureEveryFrame = false;
		}
		return;
	}
	if (!LandingCapture)
	{
		LandingTarget = NewObject<UTextureRenderTarget2D>(this);
		LandingTarget->InitAutoFormat(480, 270);
		LandingCapture = NewObject<USceneCaptureComponent2D>(this);
		LandingCapture->SetUsingAbsoluteLocation(true);
		LandingCapture->SetUsingAbsoluteRotation(true);
		LandingCapture->TextureTarget = LandingTarget;
		LandingCapture->CaptureSource = ESceneCaptureSource::SCS_FinalColorLDR;
		LandingCapture->FOVAngle = LandingViewFOV;
		LandingCapture->bCaptureOnMovement = false;
		// Trees (instanced) render as black blobs in the overhead capture; the window only needs the ground.
		LandingCapture->ShowFlags.SetInstancedStaticMeshes(false);
		LandingCapture->ShowFlags.SetInstancedFoliage(false);
		LandingCapture->ShowFlags.SetInstancedGrass(false);
		LandingCapture->RegisterComponent();
	}
	// Straight down, turned so the shot travels up the window. Frame the landing spot and the pin together,
	// so aiming visibly moves the ring against the flag (centred on the landing alone it looked frozen).
	const FRotator Aim(0.f, AimYaw, 0.f);
	const FVector Forward = Aim.Vector();
	const FVector Right = FRotationMatrix(Aim).GetUnitAxis(EAxis::Y);
	const AGolfGameState* State = GetGolfState();
	const FVector Pin = State && State->CurrentHole ? State->CurrentHole->GetCupLocation() : PreviewLanding;
	LandingViewCenter = (PreviewLanding + Pin) * 0.5f;
	const FVector Half = PreviewLanding - LandingViewCenter;
	const float HalfWidth = FMath::Max(FMath::Abs(FVector::DotProduct(Half, Right)), FMath::Abs(FVector::DotProduct(Half, Forward)) * 16.f / 9.f)
		+ LandingViewMargin;
	LandingViewHeight = FMath::Clamp(HalfWidth / FMath::Tan(FMath::DegreesToRadians(LandingViewFOV * 0.5f)), 2500.f, 20000.f);
	LandingCapture->SetWorldLocationAndRotation(LandingViewCenter + FVector(0.f, 0.f, LandingViewHeight), FRotator(-89.9f, AimYaw, 0.f));
	LandingCapture->bCaptureEveryFrame = true;
}

UTextureRenderTarget2D* AGolfPlayerController::GetMiniMapTexture() const
{
	return MiniMapHole.IsValid() ? MiniMapTarget.Get() : nullptr;
}

void AGolfPlayerController::UpdateMiniMap(float DeltaSeconds)
{
	const AGolfGameState* State = GetGolfState();
	AGolfHole* Hole = State && State->Phase == EGolfMatchPhase::PlayingHole ? State->CurrentHole.Get() : nullptr;
	if (!Hole)
	{
		MiniMapHole.Reset();
		return;
	}
	MiniMapRecapture -= DeltaSeconds;
	if (Hole == MiniMapHole.Get() && MiniMapRecapture > 0.f)
	{
		return;
	}
	const bool bNewHole = Hole != MiniMapHole.Get();
	MiniMapHole = Hole;
	// Capture again a couple of seconds after arriving (trees and textures may still be streaming in).
	MiniMapRecapture = bNewHole ? 2.f : 1.0e9f;

	if (!MiniMapCapture)
	{
		MiniMapTarget = NewObject<UTextureRenderTarget2D>(this);
		MiniMapTarget->InitAutoFormat(MiniMapPixelsX, MiniMapPixelsY);
		MiniMapCapture = NewObject<USceneCaptureComponent2D>(this);
		MiniMapCapture->SetUsingAbsoluteLocation(true);
		MiniMapCapture->SetUsingAbsoluteRotation(true);
		MiniMapCapture->TextureTarget = MiniMapTarget;
		MiniMapCapture->CaptureSource = ESceneCaptureSource::SCS_FinalColorLDR;
		MiniMapCapture->ProjectionType = ECameraProjectionMode::Orthographic;
		MiniMapCapture->bCaptureEveryFrame = false;
		MiniMapCapture->bCaptureOnMovement = false;
		MiniMapCapture->ShowFlags.SetInstancedStaticMeshes(false);
		MiniMapCapture->ShowFlags.SetInstancedFoliage(false);
		MiniMapCapture->ShowFlags.SetInstancedGrass(false);
		MiniMapCapture->ShowFlags.SetFog(false);
		MiniMapCapture->ShowFlags.SetVolumetricFog(false);
		MiniMapCapture->RegisterComponent();
	}
	// Straight down, tee at the bottom and green at the top, the whole hole in frame.
	const FVector Tee = Hole->GetTeeLocation();
	const FVector Cup = Hole->GetCupLocation();
	MiniMapYaw = (Cup - Tee).Rotation().Yaw;
	MiniMapCenter = (Tee + Cup) * 0.5f;
	const float Length = FVector::Dist2D(Tee, Cup) + 9000.f;
	const float Aspect = static_cast<float>(MiniMapPixelsX) / MiniMapPixelsY;
	MiniMapWidth = FMath::Max(Length * Aspect, 12000.f);
	MiniMapCapture->OrthoWidth = MiniMapWidth;
	MiniMapCapture->SetWorldLocationAndRotation(MiniMapCenter + FVector(0.f, 0.f, 30000.f), FRotator(-89.9f, MiniMapYaw, 0.f));
	MiniMapCapture->CaptureScene();
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

	if (IsDriving())
	{
		const float Pedals = (GasFingers > 0 ? 1.f : 0.f) - (ReverseFingers > 0 ? 1.f : 0.f) + KeyThrottle;
		GetMyBuggy()->SetDriveInput(Pedals, GetDriveSteer());
	}
	else if (IsWalking())
	{
		UpdateWalking();
	}
	UpdateMiniMap(DeltaSeconds);

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
	else if (bWasMyTurn)
	{
		CancelSwing();
		bHasPreview = false;
		bLandingView = false;
		UpdateLandingCapture();
		GridPoints.Reset();
		GridSlopes.Reset();
	}
	bWasMyTurn = bMyTurn;
	if (!bMyTurn)
	{
		return;
	}

	if (AimInput != 0.f && !IsSwinging())
	{
		SetAim(AimYaw + AimInput * KeyAimDegreesPerSecond * DeltaSeconds);
	}

	if (bKeyCharging)
	{
		SwingPower += KeyChargeDirection * DeltaSeconds / KeyChargeSeconds;
		if (SwingPower >= 1.f)
		{
			SwingPower = 1.f;
			KeyChargeDirection = -1.f;
		}
		else if (SwingPower <= 0.f)
		{
			SwingPower = 0.f;
			KeyChargeDirection = 1.f;
		}
	}

	// The preview follows the power being swiped; at rest it shows a full-power shot.
	const float WantedPower = IsSwinging() ? FMath::Max(SwingPower, MinShotPower) : GetIdlePreviewPower();
	if (FMath::Abs(WantedPower - PreviewPower) > 0.01f)
	{
		PreviewPower = WantedPower;
		bPreviewDirty = true;
	}

	PreviewCooldown -= DeltaSeconds;
	GridCooldown -= DeltaSeconds;
	if (bPreviewDirty && PreviewCooldown <= 0.f)
	{
		RefreshPreview();
	}
	if (bGridDirty && GridCooldown <= 0.f)
	{
		RefreshGreenGrid();
	}
}

void AGolfPlayerController::OnTurnStarted()
{
	CancelSwing();

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
	bGridDirty = true;
}

void AGolfPlayerController::SetAim(float Yaw)
{
	AimYaw = FRotator::NormalizeAxis(Yaw);
	if (AGolfCharacter* Golfer = GetMyGolfer())
	{
		Golfer->SetLocalAim(AimYaw);
	}
	bPreviewDirty = true;
	bGridDirty = true;
}

void AGolfPlayerController::CycleClub(int32 Direction)
{
	if (!IsMyTurn() || IsSwinging())
	{
		return;
	}
	const int32 Count = GolfPhysics::GetClubBag().Num();
	ClubIndex = (ClubIndex + Direction + Count) % Count;
	bPreviewDirty = true;
	bGridDirty = true;
}

void AGolfPlayerController::CycleSpin()
{
	if (!IsMyTurn() || IsSwinging())
	{
		return;
	}
	SpinPreset = (SpinPreset + 1) % UE_ARRAY_COUNT(SpinPresets);
	Spin = SpinPresets[SpinPreset];
	bPreviewDirty = true;
}

// ---------------------------------------------------------------- swinging

void AGolfPlayerController::UpdateSwipe(const FVector2D& Screen)
{
	const float Height = ViewportHeight();
	SwingPower = FMath::Clamp((SwipeStart.Y - Screen.Y) / (FullPowerSwipe * Height), 0.f, 1.f);

	// Up and down sets the distance; left and right moves the drop zone (the aim) with the finger.
	if (!FMath::IsNearlyEqual(Screen.X, AimLastX))
	{
		SetAim(AimYaw + (Screen.X - AimLastX) * AimDegreesPerPixel);
		AimLastX = Screen.X;
	}
	SwingAccuracy = 0.f;
}

void AGolfPlayerController::ReleaseSwing()
{
	const float Power = SwingPower;
	const float Accuracy = SwingAccuracy;
	CancelSwing();
	if (Power < MinShotPower || !IsMyTurn())
	{
		return; // Too short to count: treat it as a cancelled swipe.
	}
	if (Accuracy == 0.f)
	{
		PerfectFlashTime = GetWorld()->GetTimeSeconds();
	}
	Fire(Power, Accuracy);
}

void AGolfPlayerController::CancelSwing()
{
	bSwiping = false;
	bKeyCharging = false;
	SwingPower = 0.f;
	SwingAccuracy = 0.f;
}

void AGolfPlayerController::Fire(float Power, float Accuracy)
{
	FGolfShotInput Input;
	Input.AimYaw = AimYaw;
	Input.Power = Power;
	Input.Accuracy = Accuracy;
	Input.ClubIndex = ClubIndex;
	Input.Spin = Spin;
	ServerTakeShot(Input);
	bHasPreview = false;
	bLandingView = false;
	UpdateLandingCapture();
	GridPoints.Reset();
	GridSlopes.Reset();
}

void AGolfPlayerController::OnSwingKeyPressed()
{
	if (IsMyTurn() && !IsSwinging())
	{
		bKeyCharging = true;
		KeyChargeDirection = 1.f;
		SwingPower = 0.f;
		SwingAccuracy = 0.f;
	}
}

void AGolfPlayerController::OnSwingKeyReleased()
{
	if (bKeyCharging)
	{
		ReleaseSwing();
	}
}

// ---------------------------------------------------------------- previews

void AGolfPlayerController::RefreshPreview()
{
	bPreviewDirty = false;
	PreviewCooldown = 0.05f;

	AGolfBall* Ball = GetMyBall();
	const TArray<FGolfClub>& Bag = GolfPhysics::GetClubBag();
	if (!Ball || !Bag.IsValidIndex(ClubIndex))
	{
		bHasPreview = false;
		bLandingView = false;
		return;
	}

	const FGolfClub& Club = Bag[ClubIndex];
	const FVector Start = Ball->GetRestLocation() + FVector(0.f, 0.f, 0.5f);
	if (Club.bIsPutter)
	{
		// Aim line laid over the ground, as long as the putt would roll on a flat green.
		const FVector Direction = FRotator(0.f, AimYaw, 0.f).Vector();
		const float Distance = GolfPhysics::PuttDistance(Club.LaunchSpeed * PreviewPower);
		const int32 Steps = FMath::Clamp(FMath::CeilToInt(Distance / 20.f), 2, 400);
		PreviewPath.Reset();
		for (int32 Step = 0; Step <= Steps; ++Step)
		{
			FVector Point = Start + Direction * (Distance * Step / Steps);
			FHitResult Hit;
			if (GolfPhysics::SweepBall(GetWorld(), Point + FVector(0.f, 0.f, 100.f), Point - FVector(0.f, 0.f, 300.f), Hit, Ball))
			{
				Point = Hit.Location;
			}
			PreviewPath.Add(Point);
		}
		PreviewLanding = PreviewPath.Last();
	}
	else
	{
		FGolfShotInput Input;
		Input.AimYaw = AimYaw;
		Input.Power = PreviewPower;
		Input.ClubIndex = ClubIndex;
		Input.Spin = Spin;
		GolfPhysics::PredictCarry(GetWorld(), GolfPhysics::MakeLaunch(Club, Input, Ball->GetLie(), Start), Ball, PreviewPath, PreviewLanding);
	}

	// Any club that can reach the green gets the overhead view of the landing area and the pin, so players
	// can read where it will come down while they adjust power and aim.
	const AGolfGameState* GolfState = GetGolfState();
	const float ToPin = GolfState && GolfState->CurrentHole ? FVector::Dist2D(Start, GolfState->CurrentHole->GetCupLocation()) : 0.f;
	bLandingView = !Club.bIsPutter && ToPin > 0.f && GetClubCarry(ClubIndex) >= ToPin * 0.85f;
	bHasPreview = true;
	UpdateLandingCapture();
}

void AGolfPlayerController::RefreshGreenGrid()
{
	bGridDirty = false;
	GridCooldown = 0.15f;
	GridPoints.Reset();
	GridSlopes.Reset();

	AGolfBall* Ball = GetMyBall();
	if (!Ball || !IsPutting())
	{
		return;
	}

	const FRotator Aim(0.f, AimYaw, 0.f);
	const FVector Forward = Aim.Vector();
	const FVector Right = FRotationMatrix(Aim).GetUnitAxis(EAxis::Y);
	const FVector Origin = Ball->GetRestLocation();
	// Read only the corridor around the selected putt. A full-power putter preview can reach 40m,
	// which made the old grid busy and unrelated to the shot the player was setting up.
	const float PreviewDistance = bHasPreview ? FVector::Dist2D(Origin, PreviewLanding) : 0.f;
	const float Reach = FMath::Clamp(PreviewDistance + 250.f, 500.f, 3000.f);
	constexpr float Spacing = 100.f;
	constexpr float HalfWidth = 150.f;

	for (float Along = -150.f; Along <= Reach; Along += Spacing)
	{
		for (float Side = -HalfWidth; Side <= HalfWidth; Side += Spacing)
		{
			const FVector Sample = Origin + Forward * Along + Right * Side;
			FHitResult Hit;
			if (!GolfPhysics::SweepBall(GetWorld(), Sample + FVector(0.f, 0.f, 150.f), Sample - FVector(0.f, 0.f, 400.f), Hit, Ball)
				|| GolfPhysics::LieFromHit(Hit) != EGolfLie::Green)
			{
				continue;
			}
			GridPoints.Add(Hit.Location);
			// Gravity along the surface: points downhill, length is the sine of the slope.
			GridSlopes.Add(FVector::VectorPlaneProject(FVector(0.f, 0.f, -1.f), Hit.ImpactNormal));
		}
	}
}

// ---------------------------------------------------------------- touch

bool AGolfPlayerController::HandleButton(const FVector2D& Screen, int32 Finger)
{
	const AGolfHUD* Hud = GetHUD<AGolfHUD>();
	UGolfSessionSubsystem* Sessions = GetGameInstance()->GetSubsystem<UGolfSessionSubsystem>();
	int32 Payload = 0;
	switch (Hud ? Hud->HitTest(Screen, Payload) : EGolfHudButton::None)
	{
	case EGolfHudButton::Start: ServerRequestStart(); return true;
	case EGolfHudButton::Microphone: ToggleMicrophone(); return true;
	case EGolfHudButton::VoicePanel: bVoicePanelOpen = !bVoicePanelOpen; return true;
	case EGolfHudButton::VoicePanelBackground: return true;
	case EGolfHudButton::MutePlayer:
		TogglePlayerVoiceMute(Payload);
		return true;
	case EGolfHudButton::Host:  HostGame(); return true;
	case EGolfHudButton::Join:
		bKeypadOpen = true;
		EnteredCode.Reset();
		return true;
	case EGolfHudButton::KeypadDigit:
		if (EnteredCode.Len() < 4)
		{
			EnteredCode.AppendInt(Payload);
		}
		return true;
	case EGolfHudButton::KeypadDelete:
		EnteredCode.LeftChopInline(1);
		return true;
	case EGolfHudButton::KeypadGo:
		if (EnteredCode.Len() == 4)
		{
			bKeypadOpen = false;
			JoinGame(EnteredCode);
		}
		return true;
	case EGolfHudButton::KeypadCancel:
		bKeypadOpen = false;
		return true;
	case EGolfHudButton::Friends:
		bFriendsOpen = !bFriendsOpen;
		if (bFriendsOpen && Sessions)
		{
			Sessions->RefreshFriends();
		}
		return true;
	case EGolfHudButton::Friend:
		if (Sessions)
		{
			Sessions->InviteFriend(Payload);
		}
		return true;
	case EGolfHudButton::AcceptInvite:
		if (Sessions)
		{
			Sessions->AcceptPendingInvite();
		}
		return true;
	case EGolfHudButton::DeclineInvite:
		if (Sessions)
		{
			Sessions->DeclinePendingInvite();
		}
		return true;
	case EGolfHudButton::Throttle:
		TouchRoles[Finger] = ETouchRole::Gas;
		++GasFingers;
		return true;
	case EGolfHudButton::Reverse:
		TouchRoles[Finger] = ETouchRole::Reverse;
		++ReverseFingers;
		return true;
	case EGolfHudButton::PlayShot:
		if (CanPlayShot())
		{
			ServerFinishDriving(false);
		}
		return true;
	case EGolfHudButton::SkipDrive:
		if (IsTravelling())
		{
			ServerFinishDriving(true);
		}
		return true;
	case EGolfHudButton::Buggy:
		ServerToggleBuggy();
		return true;
	case EGolfHudButton::LobbyPanel:
		bLobbyPanelHidden = !bLobbyPanelHidden;
		return true;
	case EGolfHudButton::Club: CycleClub(1); return true;
	case EGolfHudButton::Spin: CycleSpin(); return true;
	default:
		return false;
	}
}

void AGolfPlayerController::OnTouchPressed(ETouchIndex::Type FingerIndex, FVector Location)
{
	const int32 Finger = FingerIndex;
	if (Finger < 0 || Finger >= ETouchIndex::MAX_TOUCHES)
	{
		return;
	}
	const FVector2D Screen(Location.X, Location.Y);
	TouchRoles[Finger] = ETouchRole::None;
	TouchStarts[Finger] = Screen;
	if (HandleButton(Screen, Finger))
	{
		return;
	}

	int32 SizeX = 0, SizeY = 0;
	GetViewportSize(SizeX, SizeY);
	if (IsWalking())
	{
		if (Screen.X < SizeX * 0.5f)
		{
			TouchRoles[Finger] = ETouchRole::Walk; // A floating stick where the thumb went down.
		}
		return;
	}
	if (IsDriving())
	{
		if (Screen.X < SizeX * 0.5f)
		{
			TouchRoles[Finger] = ETouchRole::Steer;
		}
		return;
	}

	if (!IsMyTurn())
	{
		return;
	}
	if (Screen.Y >= ViewportHeight() * SwipeZoneTop)
	{
		if (!IsSwinging())
		{
			TouchRoles[Finger] = ETouchRole::Swipe;
			bSwiping = true;
			SwipeStart = Screen;
			AimLastX = Screen.X;
			SwingPower = 0.f;
			SwingAccuracy = 0.f;
		}
	}
	else
	{
		TouchRoles[Finger] = ETouchRole::Aim;
		AimLastX = Screen.X;
	}
}

void AGolfPlayerController::OnTouchMoved(ETouchIndex::Type FingerIndex, FVector Location)
{
	const int32 Finger = FingerIndex;
	if (Finger < 0 || Finger >= ETouchIndex::MAX_TOUCHES)
	{
		return;
	}
	const FVector2D Screen(Location.X, Location.Y);
	switch (TouchRoles[Finger])
	{
	case ETouchRole::Swipe:
		UpdateSwipe(Screen);
		break;
	case ETouchRole::Aim:
		if (IsMyTurn())
		{
			SetAim(AimYaw + (Screen.X - AimLastX) * AimDegreesPerPixel);
		}
		AimLastX = Screen.X;
		break;
	case ETouchRole::Walk:
	{
		FVector2D Offset = (Screen - TouchStarts[Finger]) / (0.12f * ViewportHeight());
		Offset.Y = -Offset.Y; // screen up = forward
		TouchWalk = Offset.SizeSquared() > 1.f ? Offset.GetSafeNormal() : Offset;
		break;
	}
	case ETouchRole::Steer:
		// Steering is relative to where the thumb went down.
		TouchSteer = FMath::Clamp((Screen.X - TouchStarts[Finger].X) / (0.15f * ViewportHeight()), -1.f, 1.f);
		break;
	default:
		break;
	}
}

void AGolfPlayerController::OnTouchReleased(ETouchIndex::Type FingerIndex, FVector Location)
{
	const int32 Finger = FingerIndex;
	if (Finger < 0 || Finger >= ETouchIndex::MAX_TOUCHES)
	{
		return;
	}
	switch (TouchRoles[Finger])
	{
	case ETouchRole::Swipe:
		UpdateSwipe(FVector2D(Location.X, Location.Y));
		ReleaseSwing();
		break;
	case ETouchRole::Steer:
		TouchSteer = 0.f;
		break;
	case ETouchRole::Walk:
		TouchWalk = FVector2D::ZeroVector;
		break;
	case ETouchRole::Gas:
		GasFingers = FMath::Max(0, GasFingers - 1);
		break;
	case ETouchRole::Reverse:
		ReverseFingers = FMath::Max(0, ReverseFingers - 1);
		break;
	default:
		break;
	}
	TouchRoles[Finger] = ETouchRole::None;
}

// ---------------------------------------------------------------- server and sessions

void AGolfPlayerController::ServerTakeShot_Implementation(const FGolfShotInput& Input)
{
	if (AGolfGameMode* Mode = GetWorld()->GetAuthGameMode<AGolfGameMode>())
	{
		Mode->HandleShot(this, Input);
	}
}

void AGolfPlayerController::ServerToggleBuggy_Implementation()
{
	if (AGolfGameMode* Mode = GetWorld()->GetAuthGameMode<AGolfGameMode>())
	{
		Mode->ToggleBuggy(this);
	}
}

void AGolfPlayerController::ServerFinishDriving_Implementation(bool bSkip)
{
	if (AGolfGameMode* Mode = GetWorld()->GetAuthGameMode<AGolfGameMode>())
	{
		Mode->FinishDriving(this, bSkip);
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
