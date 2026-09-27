#include "GolfSessionSubsystem.h"
#include "SkyLinks.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Interfaces/OnlineFriendsInterface.h"
#include "Interfaces/OnlineIdentityInterface.h"
#include "Interfaces/OnlinePresenceInterface.h"
#include "Online/OnlineSessionNames.h"
#include "OnlineSubsystem.h"
#include "OnlineSubsystemUtils.h"

const FName UGolfSessionSubsystem::RoomCodeKey(TEXT("ROOMCODE"));

void UGolfSessionSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	if (IOnlineSessionPtr Sessions = GetSessions())
	{
		InviteReceivedHandle = Sessions->AddOnSessionInviteReceivedDelegate_Handle(
			FOnSessionInviteReceivedDelegate::CreateUObject(this, &UGolfSessionSubsystem::OnInviteReceived));
		InviteAcceptedHandle = Sessions->AddOnSessionUserInviteAcceptedDelegate_Handle(
			FOnSessionUserInviteAcceptedDelegate::CreateUObject(this, &UGolfSessionSubsystem::OnInviteAccepted));
	}
}

void UGolfSessionSubsystem::Deinitialize()
{
	if (IOnlineSessionPtr Sessions = GetSessions())
	{
		Sessions->ClearOnCreateSessionCompleteDelegate_Handle(CreateHandle);
		Sessions->ClearOnFindSessionsCompleteDelegate_Handle(FindHandle);
		Sessions->ClearOnJoinSessionCompleteDelegate_Handle(JoinHandle);
		Sessions->ClearOnDestroySessionCompleteDelegate_Handle(DestroyHandle);
		Sessions->ClearOnSessionInviteReceivedDelegate_Handle(InviteReceivedHandle);
		Sessions->ClearOnSessionUserInviteAcceptedDelegate_Handle(InviteAcceptedHandle);
	}
	if (const IOnlineSubsystem* Subsystem = Online::GetSubsystem(GetWorld()))
	{
		if (IOnlineIdentityPtr Identity = Subsystem->GetIdentityInterface())
		{
			Identity->ClearOnLoginCompleteDelegate_Handle(0, LoginHandle);
		}
	}
	AfterLogin = nullptr;
	AfterDestroy = nullptr;
	Super::Deinitialize();
}

IOnlineSessionPtr UGolfSessionSubsystem::GetSessions() const
{
	const IOnlineSubsystem* Subsystem = Online::GetSubsystem(GetWorld());
	return Subsystem ? Subsystem->GetSessionInterface() : nullptr;
}

bool UGolfSessionSubsystem::IsLan() const
{
	const IOnlineSubsystem* Subsystem = Online::GetSubsystem(GetWorld());
	return !Subsystem || Subsystem->GetSubsystemName() == TEXT("NULL");
}

bool UGolfSessionSubsystem::SupportsFriends() const
{
	const IOnlineSubsystem* Subsystem = Online::GetSubsystem(GetWorld());
	return !IsLan() && Subsystem && Subsystem->GetFriendsInterface().IsValid();
}

// ---------------------------------------------------------------- login (EOS needs an Epic account for friends and invites)

void UGolfSessionSubsystem::EnsureLoggedIn(TFunction<void()> Then)
{
	const IOnlineSubsystem* Subsystem = Online::GetSubsystem(GetWorld());
	IOnlineIdentityPtr Identity = Subsystem ? Subsystem->GetIdentityInterface() : nullptr;
	if (IsLan() || !Identity.IsValid() || Identity->GetLoginStatus(0) == ELoginStatus::LoggedIn)
	{
		Then();
		return;
	}
	AfterLogin = MoveTemp(Then);
	bTriedAccountPortal = false;
	LoginHandle = Identity->AddOnLoginCompleteDelegate_Handle(0, FOnLoginCompleteDelegate::CreateUObject(this, &UGolfSessionSubsystem::OnLoginComplete));
	// Silent login with a saved token first; fall back to the Epic sign-in page.
	TryLogin(TEXT("persistentauth"));
}

void UGolfSessionSubsystem::TryLogin(const FString& Type)
{
	IOnlineIdentityPtr Identity = Online::GetSubsystem(GetWorld())->GetIdentityInterface();
	FOnlineAccountCredentials Credentials;
	Credentials.Type = Type;
	Status = TEXT("Signing in...");
	Identity->Login(0, Credentials);
}

void UGolfSessionSubsystem::OnLoginComplete(int32 LocalUserNum, bool bWasSuccessful, const FUniqueNetId& UserId, const FString& Error)
{
	if (!bWasSuccessful && !bTriedAccountPortal)
	{
		bTriedAccountPortal = true;
		TryLogin(TEXT("accountportal"));
		return;
	}

	Online::GetSubsystem(GetWorld())->GetIdentityInterface()->ClearOnLoginCompleteDelegate_Handle(0, LoginHandle);
	if (!bWasSuccessful)
	{
		bSessionOperationInProgress = false;
		AfterLogin = nullptr;
		Status = FString::Printf(TEXT("Sign-in failed: %s"), *Error);
		return;
	}
	Status.Reset();
	if (AfterLogin)
	{
		TFunction<void()> Next = MoveTemp(AfterLogin);
		Next();
	}
}

// ---------------------------------------------------------------- hosting

void UGolfSessionSubsystem::HostOnline()
{
	if (bSessionOperationInProgress) return;
	bSessionOperationInProgress = true;
	EnsureLoggedIn([this]()
	{
		IOnlineSessionPtr Sessions = GetSessions();
		RoomCode = FString::Printf(TEXT("%04d"), FMath::RandRange(0, 9999));
		if (!Sessions.IsValid())
		{
			bSessionOperationInProgress = false;
			Status = TEXT("No online service. Hosting directly.");
			GetWorld()->ServerTravel(CourseMap + TEXT("?listen"));
			return;
		}
		CloseExistingSession([this, Sessions]()
		{
			FOnlineSessionSettings Settings;
			Settings.NumPublicConnections = MaxPlayers;
			Settings.bShouldAdvertise = true;
			Settings.bAllowJoinInProgress = true;
			Settings.bIsLANMatch = IsLan();
			Settings.bUsesPresence = true;
			Settings.bUseLobbiesIfAvailable = true;
			Settings.bAllowJoinViaPresence = true;
			Settings.bAllowInvites = true;
			Settings.Set(RoomCodeKey, RoomCode, EOnlineDataAdvertisementType::ViaOnlineServiceAndPing);

			CreateHandle = Sessions->AddOnCreateSessionCompleteDelegate_Handle(
				FOnCreateSessionCompleteDelegate::CreateUObject(this, &UGolfSessionSubsystem::OnCreateComplete));
			Status = TEXT("Creating game...");
			if (!Sessions->CreateSession(0, NAME_GameSession, Settings))
			{
				Sessions->ClearOnCreateSessionCompleteDelegate_Handle(CreateHandle);
				bSessionOperationInProgress = false;
				Status = TEXT("Could not create a game.");
			}
		});
	});
}

void UGolfSessionSubsystem::OnCreateComplete(FName SessionName, bool bSuccess)
{
	bSessionOperationInProgress = false;
	if (IOnlineSessionPtr Sessions = GetSessions())
	{
		Sessions->ClearOnCreateSessionCompleteDelegate_Handle(CreateHandle);
	}
	if (!bSuccess)
	{
		Status = TEXT("Could not create a game.");
		return;
	}
	Status.Reset();
	GetWorld()->ServerTravel(CourseMap + TEXT("?listen"));
}

void UGolfSessionSubsystem::CloseExistingSession(TFunction<void()> Then)
{
	IOnlineSessionPtr Sessions = GetSessions();
	if (!Sessions.IsValid() || !Sessions->GetNamedSession(NAME_GameSession))
	{
		Then();
		return;
	}
	AfterDestroy = MoveTemp(Then);
	DestroyHandle = Sessions->AddOnDestroySessionCompleteDelegate_Handle(
		FOnDestroySessionCompleteDelegate::CreateUObject(this, &UGolfSessionSubsystem::OnDestroyComplete));
	Status = TEXT("Leaving previous game...");
	if (!Sessions->DestroySession(NAME_GameSession))
	{
		Sessions->ClearOnDestroySessionCompleteDelegate_Handle(DestroyHandle);
		AfterDestroy = nullptr;
		bSessionOperationInProgress = false;
		Status = TEXT("Could not leave the previous game. Please try again.");
	}
}

void UGolfSessionSubsystem::OnDestroyComplete(FName SessionName, bool bSuccess)
{
	if (IOnlineSessionPtr Sessions = GetSessions())
	{
		Sessions->ClearOnDestroySessionCompleteDelegate_Handle(DestroyHandle);
	}
	TFunction<void()> Next = MoveTemp(AfterDestroy);
	AfterDestroy = nullptr;
	if (!bSuccess)
	{
		bSessionOperationInProgress = false;
		Status = TEXT("Could not leave the previous game. Please try again.");
		return;
	}
	if (Next) Next();
}

// ---------------------------------------------------------------- joining by room code

void UGolfSessionSubsystem::JoinByCode(const FString& Code)
{
	if (bSessionOperationInProgress) return;
	bSessionOperationInProgress = true;
	SearchCode = Code;
	EnsureLoggedIn([this]()
	{
		IOnlineSessionPtr Sessions = GetSessions();
		if (!Sessions.IsValid())
		{
			bSessionOperationInProgress = false;
			Status = TEXT("No online service. Use the console: open <host IP>");
			return;
		}

		Search = MakeShared<FOnlineSessionSearch>();
		Search->MaxSearchResults = 100;
		Search->bIsLanQuery = IsLan();
		Search->QuerySettings.Set(SEARCH_LOBBIES, true, EOnlineComparisonOp::Equals);
		if (!SearchCode.IsEmpty())
		{
			Search->QuerySettings.Set(RoomCodeKey, SearchCode, EOnlineComparisonOp::Equals);
		}

		FindHandle = Sessions->AddOnFindSessionsCompleteDelegate_Handle(
			FOnFindSessionsCompleteDelegate::CreateUObject(this, &UGolfSessionSubsystem::OnFindComplete));
		Status = SearchCode.IsEmpty() ? TEXT("Looking for games...") : FString::Printf(TEXT("Looking for room %s..."), *SearchCode);
		if (!Sessions->FindSessions(0, Search.ToSharedRef()))
		{
			Sessions->ClearOnFindSessionsCompleteDelegate_Handle(FindHandle);
			bSessionOperationInProgress = false;
			Status = TEXT("Search failed.");
		}
	});
}

void UGolfSessionSubsystem::OnFindComplete(bool bSuccess)
{
	bSessionOperationInProgress = false;
	IOnlineSessionPtr Sessions = GetSessions();
	if (!Sessions.IsValid() || !Search.IsValid())
	{
		return;
	}
	Sessions->ClearOnFindSessionsCompleteDelegate_Handle(FindHandle);
	if (!bSuccess)
	{
		Status = TEXT("Search failed.");
		return;
	}

	for (const FOnlineSessionSearchResult& Result : Search->SearchResults)
	{
		// LAN search ignores query filters, so check the code here as well.
		FString Code;
		Result.Session.SessionSettings.Get(RoomCodeKey, Code);
		if (Result.IsValid() && Result.Session.NumOpenPublicConnections > 0 && (SearchCode.IsEmpty() || Code == SearchCode))
		{
			JoinResult(Result);
			return;
		}
	}
	Status = SearchCode.IsEmpty() ? TEXT("No games found.") : FString::Printf(TEXT("No room %s. Check the code with your host."), *SearchCode);
}

void UGolfSessionSubsystem::JoinResult(const FOnlineSessionSearchResult& Result)
{
	if (bSessionOperationInProgress) return;
	IOnlineSessionPtr Sessions = GetSessions();
	if (!Sessions.IsValid())
	{
		return;
	}
	bSessionOperationInProgress = true;
	CloseExistingSession([this, Sessions, Result]()
	{
		Result.Session.SessionSettings.Get(RoomCodeKey, RoomCode);
		JoinHandle = Sessions->AddOnJoinSessionCompleteDelegate_Handle(
			FOnJoinSessionCompleteDelegate::CreateUObject(this, &UGolfSessionSubsystem::OnJoinComplete));
		Status = TEXT("Joining...");
		if (!Sessions->JoinSession(0, NAME_GameSession, Result))
		{
			Sessions->ClearOnJoinSessionCompleteDelegate_Handle(JoinHandle);
			bSessionOperationInProgress = false;
			Status = TEXT("Could not join that game.");
		}
	});
}

void UGolfSessionSubsystem::OnJoinComplete(FName SessionName, EOnJoinSessionCompleteResult::Type Result)
{
	bSessionOperationInProgress = false;
	IOnlineSessionPtr Sessions = GetSessions();
	if (!Sessions.IsValid())
	{
		return;
	}
	Sessions->ClearOnJoinSessionCompleteDelegate_Handle(JoinHandle);

	FString Address;
	if (Result != EOnJoinSessionCompleteResult::Success || !Sessions->GetResolvedConnectString(SessionName, Address))
	{
		Status = Result == EOnJoinSessionCompleteResult::SessionIsFull ? TEXT("That game is full.") : TEXT("Could not join that game.");
		return;
	}
	Status.Reset();
	if (APlayerController* Controller = GetGameInstance()->GetFirstLocalPlayerController())
	{
		Controller->ClientTravel(Address, TRAVEL_Absolute);
	}
}

// ---------------------------------------------------------------- friends and invites

void UGolfSessionSubsystem::RefreshFriends()
{
	if (!SupportsFriends())
	{
		return;
	}
	EnsureLoggedIn([this]()
	{
		IOnlineFriendsPtr FriendsInterface = Online::GetSubsystem(GetWorld())->GetFriendsInterface();
		FriendsInterface->ReadFriendsList(0, EFriendsLists::ToString(EFriendsLists::Default),
			FOnReadFriendsListComplete::CreateUObject(this, &UGolfSessionSubsystem::OnFriendsRead));
	});
}

void UGolfSessionSubsystem::OnFriendsRead(int32 LocalUserNum, bool bWasSuccessful, const FString& ListName, const FString& Error)
{
	Friends.Reset();
	if (!bWasSuccessful)
	{
		Status = TEXT("Could not load your friends list.");
		return;
	}
	TArray<TSharedRef<FOnlineFriend>> List;
	Online::GetSubsystem(GetWorld())->GetFriendsInterface()->GetFriendsList(0, ListName, List);
	for (const TSharedRef<FOnlineFriend>& Friend : List)
	{
		FGolfFriend Entry;
		Entry.Name = Friend->GetDisplayName();
		Entry.Id = Friend->GetUserId();
		Entry.bOnline = Friend->GetPresence().bIsOnline;
		Friends.Add(MoveTemp(Entry));
	}
	// Online friends first.
	Friends.StableSort([](const FGolfFriend& A, const FGolfFriend& B) { return A.bOnline && !B.bOnline; });
}

void UGolfSessionSubsystem::InviteFriend(int32 Index)
{
	IOnlineSessionPtr Sessions = GetSessions();
	if (!Sessions.IsValid() || !Friends.IsValidIndex(Index) || !Friends[Index].Id.IsValid())
	{
		return;
	}
	if (Sessions->SendSessionInviteToFriend(0, NAME_GameSession, *Friends[Index].Id))
	{
		Status = FString::Printf(TEXT("Invited %s"), *Friends[Index].Name);
	}
	else
	{
		Status = TEXT("Could not send the invite.");
	}
}

void UGolfSessionSubsystem::OnInviteReceived(const FUniqueNetId& UserId, const FUniqueNetId& FromId, const FString& AppId, const FOnlineSessionSearchResult& Invite)
{
	PendingInvite = Invite;
	bHasPendingInvite = true;
	PendingInviteFrom = TEXT("A friend");
	if (IOnlineFriendsPtr FriendsInterface = Online::GetSubsystem(GetWorld())->GetFriendsInterface())
	{
		if (TSharedPtr<FOnlineFriend> Friend = FriendsInterface->GetFriend(0, FromId, EFriendsLists::ToString(EFriendsLists::Default)))
		{
			PendingInviteFrom = Friend->GetDisplayName();
		}
	}
}

void UGolfSessionSubsystem::OnInviteAccepted(bool bWasSuccessful, int32 ControllerId, FUniqueNetIdPtr UserId, const FOnlineSessionSearchResult& Invite)
{
	// Accepted from outside the game (Epic overlay, OS notification).
	if (bWasSuccessful && Invite.IsValid())
	{
		JoinResult(Invite);
	}
}

void UGolfSessionSubsystem::AcceptPendingInvite()
{
	if (bHasPendingInvite)
	{
		bHasPendingInvite = false;
		JoinResult(PendingInvite);
	}
}
