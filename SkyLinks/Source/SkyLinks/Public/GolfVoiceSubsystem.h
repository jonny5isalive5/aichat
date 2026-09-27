#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Tickable.h"
#include "GolfVoiceSubsystem.generated.h"

class APlayerState;
class IVoiceChatUser;

/** One conversation for the room. Preferences survive travel and never affect another listener. */
UCLASS()
class SKYLINKS_API UGolfVoiceSubsystem : public UGameInstanceSubsystem, public FTickableGameObject
{
	GENERATED_BODY()
public:
	virtual void Tick(float DeltaTime) override;
	virtual bool IsTickable() const override;
	virtual TStatId GetStatId() const override;
	virtual void Deinitialize() override;
	void Refresh(bool bForce = false);
	void ToggleMicrophone();
	void TogglePlayerMute(const APlayerState* PlayerState);
	bool IsMicrophoneMuted() const { return bMicrophoneMuted; }
	bool IsReady() const { return bReady; }
	bool IsPlayerMuted(const APlayerState* PlayerState) const;
	bool IsPlayerTalking(const APlayerState* PlayerState) const;
	FString GetStatus() const { return Status; }
private:
	IVoiceChatUser* GetEOSUser() const;
	FString GetVoiceName(const APlayerState* PlayerState) const;
	void StopTransmission();
	bool bMicrophoneMuted = false;
	bool bReady = false;
	bool bLanRegistered = false;
	bool bShuttingDown = false;
	bool bTransmissionApplied = false;
	bool bTransmitting = false;
	float RefreshDelay = 0.f;
	FString Status = TEXT("Join a room for voice");
	TSet<FString> MutedPlayers;
	TSet<FString> RegisteredPlayers;
	FString RegisteredRoom;
};
