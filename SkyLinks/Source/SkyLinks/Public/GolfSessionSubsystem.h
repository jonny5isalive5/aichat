#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Interfaces/OnlineSessionInterface.h"
#include "OnlineSessionSettings.h"
#include "GolfSessionSubsystem.generated.h"

class FOnlineSessionSearch;

struct FGolfFriend
{
	FString Name;
	FUniqueNetIdPtr Id;
	bool bOnline = false;
};

/**
 * Playing with friends:
 *  - Room codes: the host gets a 4-digit code; friends type it to join. Works on LAN (Null) and online (EOS).
 *  - Invites: with EOS, the lobby lists your Epic friends; tap one to invite. Invites pop up in the
 *    friend's lobby and can be accepted from there (or from the Epic overlay on PC).
 *  - Fallback: the console command `open <host IP>`.
 */
UCLASS()
class SKYLINKS_API UGolfSessionSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	void HostOnline();
	/** Joins the game with this room code, or the first open game if the code is empty. */
	void JoinByCode(const FString& Code);

	void RefreshFriends();
	const TArray<FGolfFriend>& GetFriends() const { return Friends; }
	bool SupportsFriends() const;
	void InviteFriend(int32 Index);

	bool HasPendingInvite() const { return bHasPendingInvite; }
	FString GetPendingInviteFrom() const { return PendingInviteFrom; }
	void AcceptPendingInvite();
	void DeclinePendingInvite() { bHasPendingInvite = false; }

	FString GetRoomCode() const { return RoomCode; }
	FString GetStatus() const { return Status; }

	/** The course map the host travels to with ?listen. */
	UPROPERTY(EditAnywhere, Category = "Golf")
	FString CourseMap = TEXT("/Game/Maps/Course");

	static constexpr int32 MaxPlayers = 4;
	static const FName RoomCodeKey;

private:
	IOnlineSessionPtr GetSessions() const;
	bool IsLan() const;
	void EnsureLoggedIn(TFunction<void()> Then);
	void TryLogin(const FString& Type);

	void JoinResult(const FOnlineSessionSearchResult& Result);
	void OnCreateComplete(FName SessionName, bool bSuccess);
	void OnFindComplete(bool bSuccess);
	void OnJoinComplete(FName SessionName, EOnJoinSessionCompleteResult::Type Result);
	void OnInviteReceived(const FUniqueNetId& UserId, const FUniqueNetId& FromId, const FString& AppId, const FOnlineSessionSearchResult& Invite);
	void OnInviteAccepted(bool bWasSuccessful, int32 ControllerId, FUniqueNetIdPtr UserId, const FOnlineSessionSearchResult& Invite);
	void OnFriendsRead(int32 LocalUserNum, bool bWasSuccessful, const FString& ListName, const FString& Error);
	void OnLoginComplete(int32 LocalUserNum, bool bWasSuccessful, const FUniqueNetId& UserId, const FString& Error);

	TSharedPtr<FOnlineSessionSearch> Search;
	FString SearchCode;
	FDelegateHandle CreateHandle, FindHandle, JoinHandle, InviteReceivedHandle, InviteAcceptedHandle, LoginHandle;

	TArray<FGolfFriend> Friends;
	FOnlineSessionSearchResult PendingInvite;
	bool bHasPendingInvite = false;
	FString PendingInviteFrom;

	TFunction<void()> AfterLogin;
	bool bTriedAccountPortal = false;

	FString RoomCode;
	FString Status;
};
