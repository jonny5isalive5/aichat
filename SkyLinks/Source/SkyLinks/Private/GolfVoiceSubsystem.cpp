#include "GolfVoiceSubsystem.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerState.h"
#include "Interfaces/OnlineIdentityInterface.h"
#include "Interfaces/OnlineSessionInterface.h"
#include "Interfaces/VoiceInterface.h"
#include "Online/OnlineSessionNames.h"
#include "OnlineSubsystem.h"
#include "OnlineSubsystemUtils.h"
#include "OnlineSessionSettings.h"
#include "IOnlineSubsystemEOS.h"
#include "OnlineSubsystemEOSTypesPublic.h"
#include "VoiceChat.h"

bool UGolfVoiceSubsystem::IsTickable() const
{
	return !IsTemplate() && !bShuttingDown && GetGameInstance() && GetGameInstance()->GetWorld()
		&& GetGameInstance()->GetWorld()->IsGameWorld();
}

TStatId UGolfVoiceSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UGolfVoiceSubsystem, STATGROUP_Tickables);
}

void UGolfVoiceSubsystem::Tick(float DeltaTime)
{
	RefreshDelay -= DeltaTime;
	if (RefreshDelay <= 0.f)
	{
		RefreshDelay = 0.5f;
		Refresh();
	}
}

IVoiceChatUser* UGolfVoiceSubsystem::GetEOSUser() const
{
	if (!GetGameInstance() || !GetGameInstance()->GetWorld()) return nullptr;
	IOnlineSubsystem* OnlineService = Online::GetSubsystem(GetGameInstance()->GetWorld());
	if (!OnlineService || OnlineService->GetSubsystemName() != FName(TEXT("EOS"))) return nullptr;
	const IOnlineIdentityPtr Identity = OnlineService->GetIdentityInterface();
	const FUniqueNetIdPtr LocalId = Identity ? Identity->GetUniquePlayerId(0) : nullptr;
	return LocalId.IsValid() && Identity->GetLoginStatus(0) == ELoginStatus::LoggedIn
		? static_cast<IOnlineSubsystemEOS*>(OnlineService)->GetVoiceChatUserInterface(*LocalId) : nullptr;
}

FString UGolfVoiceSubsystem::GetVoiceName(const APlayerState* PlayerState) const
{
	if (!PlayerState || !PlayerState->GetUniqueId().IsValid()) return FString();
	const FUniqueNetId& Id = *PlayerState->GetUniqueId();
#if WITH_EOS_SDK
	if (Id.GetType() == FName(TEXT("EOS")))
	{
		const EOS_ProductUserId ProductId = static_cast<const IUniqueNetIdEOS&>(Id).GetProductUserId();
		char Buffer[EOS_PRODUCTUSERID_MAX_LENGTH + 1] = {};
		int32 BufferLength = sizeof(Buffer);
		if (EOS_ProductUserId_ToString(ProductId, Buffer, &BufferLength) == EOS_EResult::EOS_Success)
			return UTF8_TO_TCHAR(Buffer);
		return FString();
	}
#endif
	return Id.ToString();
}

void UGolfVoiceSubsystem::StopTransmission()
{
	if (!GetGameInstance() || !GetGameInstance()->GetWorld()) return;
	if (!bTransmissionApplied && !bLanRegistered) return;
	if (IVoiceChatUser* VoiceUser = GetEOSUser())
	{
		VoiceUser->SetAudioInputDeviceMuted(true);
		VoiceUser->TransmitToNoChannels();
	}
	else if (const IOnlineSubsystem* OnlineService = Online::GetSubsystem(GetGameInstance()->GetWorld()))
	{
		if (const IOnlineVoicePtr Voice = OnlineService->GetVoiceInterface()) Voice->StopNetworkedVoice(0);
	}
	bReady = false;
	bTransmissionApplied = false;
	bTransmitting = false;
}

void UGolfVoiceSubsystem::Refresh(bool bForce)
{
	UWorld* World = GetGameInstance()->GetWorld();
	if (!World || World->GetNetMode() == NM_DedicatedServer) return;
	const IOnlineSubsystem* OnlineService = Online::GetSubsystem(World);
	const IOnlineSessionPtr Sessions = OnlineService ? OnlineService->GetSessionInterface() : nullptr;
	const FNamedOnlineSession* Room = Sessions ? Sessions->GetNamedSession(NAME_GameSession) : nullptr;
	if (!Room || Room->SessionState == EOnlineSessionState::Destroying)
	{
		StopTransmission();
		bReady = false;
		bLanRegistered = false;
		RegisteredPlayers.Reset();
		RegisteredRoom.Reset();
		Status = TEXT("Join a room for voice");
		return;
	}
	if (RegisteredRoom != Room->GetSessionIdStr())
	{
		RegisteredRoom = Room->GetSessionIdStr();
		RegisteredPlayers.Reset();
		bLanRegistered = false;
	}

	if (OnlineService->GetSubsystemName() == FName(TEXT("EOS")))
	{
		IVoiceChatUser* VoiceUser = GetEOSUser();
		bReady = VoiceUser && !VoiceUser->GetChannels().IsEmpty() && !VoiceUser->GetAvailableInputDeviceInfos().IsEmpty();
		if (VoiceUser)
		{
			VoiceUser->SetAudioInputDeviceMuted(bMicrophoneMuted || !bReady);
			if (bReady && !bMicrophoneMuted) VoiceUser->TransmitToAllChannels();
			else VoiceUser->TransmitToNoChannels();
			bTransmissionApplied = true;
		}
		Status = bReady ? TEXT("Group voice connected") : TEXT("Voice connecting / unavailable");
	}
	else
	{
		const IOnlineVoicePtr Voice = OnlineService->GetVoiceInterface();
		// Registration starts transmission: apply our preference in the same frame.
		if (Voice && !bLanRegistered)
		{
			bLanRegistered = Voice->RegisterLocalTalker(0);
			bTransmissionApplied = false;
		}
		bReady = Voice && bLanRegistered && Voice->IsHeadsetPresent(0);
		const bool bShouldTransmit = bReady && !bMicrophoneMuted;
		if (Voice && (bForce || !bTransmissionApplied || bTransmitting != bShouldTransmit))
		{
			if (bShouldTransmit) Voice->StartNetworkedVoice(0);
			else Voice->StopNetworkedVoice(0);
			bTransmitting = bShouldTransmit;
			bTransmissionApplied = true;
		}
		Status = bReady ? TEXT("LAN voice ready") : TEXT("Voice unavailable: check microphone");
	}

	if (const AGameStateBase* GameState = World->GetGameState())
	{
		for (const APlayerState* RemotePlayer : GameState->PlayerArray)
		{
			const FString VoiceName = GetVoiceName(RemotePlayer);
			if (VoiceName.IsEmpty()) continue;
			if (IVoiceChatUser* VoiceUser = GetEOSUser())
			{
				const bool bMuted = MutedPlayers.Contains(VoiceName);
				if (bMuted && !VoiceUser->IsPlayerMuted(VoiceName)) VoiceUser->SetPlayerMuted(VoiceName, true);
			}
			else if (const IOnlineVoicePtr Voice = OnlineService->GetVoiceInterface())
			{
				const APlayerController* LocalController = GetGameInstance()->GetFirstLocalPlayerController();
				if (LocalController && LocalController->PlayerState == RemotePlayer) continue;
				if (!RegisteredPlayers.Contains(VoiceName) && Voice->RegisterRemoteTalker(*RemotePlayer->GetUniqueId()))
					RegisteredPlayers.Add(VoiceName);
				const bool bMuted = MutedPlayers.Contains(VoiceName);
				if (bMuted && !Voice->IsMuted(0, *RemotePlayer->GetUniqueId()))
				{
					Voice->MuteRemoteTalker(0, *RemotePlayer->GetUniqueId(), false);
				}
			}
		}
	}
}

void UGolfVoiceSubsystem::ToggleMicrophone()
{
	bMicrophoneMuted = !bMicrophoneMuted;
	Refresh();
}

bool UGolfVoiceSubsystem::IsPlayerMuted(const APlayerState* PlayerState) const
{
	return MutedPlayers.Contains(GetVoiceName(PlayerState));
}

void UGolfVoiceSubsystem::TogglePlayerMute(const APlayerState* PlayerState)
{
	const FString VoiceName = GetVoiceName(PlayerState);
	if (VoiceName.IsEmpty()) return;
	if (MutedPlayers.Contains(VoiceName))
	{
		MutedPlayers.Remove(VoiceName);
		if (IVoiceChatUser* VoiceUser = GetEOSUser()) VoiceUser->SetPlayerMuted(VoiceName, false);
		else if (const IOnlineSubsystem* OnlineService = Online::GetSubsystem(GetGameInstance()->GetWorld()))
		{
			if (const IOnlineVoicePtr Voice = OnlineService->GetVoiceInterface())
				Voice->UnmuteRemoteTalker(0, *PlayerState->GetUniqueId(), false);
		}
	}
	else MutedPlayers.Add(VoiceName);
	Refresh();
}

bool UGolfVoiceSubsystem::IsPlayerTalking(const APlayerState* PlayerState) const
{
	if (!bReady || !PlayerState || IsPlayerMuted(PlayerState) || !PlayerState->GetUniqueId().IsValid()) return false;
	if (IVoiceChatUser* VoiceUser = GetEOSUser()) return VoiceUser->IsPlayerTalking(GetVoiceName(PlayerState));
	const IOnlineSubsystem* OnlineService = Online::GetSubsystem(GetGameInstance()->GetWorld());
	const IOnlineVoicePtr Voice = OnlineService ? OnlineService->GetVoiceInterface() : nullptr;
	const APlayerController* LocalController = GetGameInstance()->GetFirstLocalPlayerController();
	return Voice && (LocalController && LocalController->PlayerState == PlayerState
		? !bMicrophoneMuted && Voice->IsLocalPlayerTalking(0) : Voice->IsRemotePlayerTalking(*PlayerState->GetUniqueId()));
}

void UGolfVoiceSubsystem::Deinitialize()
{
	bShuttingDown = true;
	StopTransmission();
	Super::Deinitialize();
}
