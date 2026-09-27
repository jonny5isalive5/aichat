#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "GolfHUD.generated.h"

class AGolfGameState;
class AGolfPlayerController;

UENUM()
enum class EGolfHudButton : uint8
{
	None,
	Club,
	Spin,
	Swing,
	Start,
	Host,
	Join,
	KeypadDigit,
	KeypadDelete,
	KeypadGo,
	KeypadCancel,
	Friends,
	Friend,
	AcceptInvite,
	DeclineInvite,
	Throttle,
	Reverse,
	PlayShot,
	SkipDrive,
	Microphone,
	VoicePanel,
	VoicePanelBackground,
	MutePlayer
};

/**
 * Landscape HUD drawn straight to the canvas so the game runs with no UI assets.
 * Layout: hole card top-left, players under it, wind top-right, club disc bottom-left,
 * swipe power meter bottom-right, shot preview and green-reading grid on the course.
 * All sizes are in units of 1% of screen height, so it scales across phones.
 */
UCLASS()
class SKYLINKS_API AGolfHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;

	/** OutPayload carries the digit for keypad keys and the list index for friends. */
	EGolfHudButton HitTest(const FVector2D& ScreenPosition, int32& OutPayload) const;

private:
	struct FButton
	{
		EGolfHudButton Id;
		FVector2D Center;
		float Radius;
		int32 Payload;
		FVector2D RectSize = FVector2D::ZeroVector;
	};
	TArray<FButton> Buttons;
	float U = 1.f;

	void DrawLobby(AGolfGameState* State, AGolfPlayerController* Controller);
	void DrawKeypad(AGolfPlayerController* Controller);
	void DrawFriends();
	void DrawInvitePopup();
	void DrawVoice(AGolfGameState* State, AGolfPlayerController* Controller);
	void DrawPlaying(AGolfGameState* State, AGolfPlayerController* Controller);
	void DrawHoleCard(AGolfGameState* State);
	void DrawPlayers(AGolfGameState* State);
	void DrawWind(AGolfGameState* State);
	void DrawDriving(AGolfPlayerController* Controller);
	void DrawGreenGrid(AGolfPlayerController* Controller);
	void DrawPreview(AGolfPlayerController* Controller);
	void DrawClubDisc(AGolfPlayerController* Controller);
	void DrawPowerMeter(AGolfPlayerController* Controller);
	void DrawScorecard(AGolfGameState* State);
	void DrawAnnouncement(AGolfGameState* State);

	void Box(const FVector2D& Position, const FVector2D& Size, const FLinearColor& Color);
	void Disc(const FVector2D& Center, float Radius, const FLinearColor& Color);
	void Ring(const FVector2D& Center, float Radius, const FLinearColor& Color, float Thickness);
	void Line(const FVector2D& A, const FVector2D& B, const FLinearColor& Color, float Thickness);
	void Label(const FString& Text, const FVector2D& Position, float Height, const FLinearColor& Color, bool bCenter);
	void RoundButton(EGolfHudButton Id, const FVector2D& Center, float Radius, const FString& Text, const FLinearColor& Fill, int32 Payload = 0);
	bool ToScreen(const FVector& World, FVector2D& OutScreen) const;
};
