#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "GolfTypes.h"
#include "GolfCharacter.generated.h"

class USpringArmComponent;
class UCameraComponent;
class UAnimSequence;
class USkeletalMesh;
class UStaticMesh;
class AGolfBuggy;

/**
 * The golfer. Stands addressing the ball; the camera sits low behind the ball looking down the
 * aim line, with the golfer on the left of frame. Its position is derived on every machine from
 * the replicated ball location and aim, so no movement replication is needed.
 *
 * The body is the owner's Mixamo-rigged golfer (/Game/Characters/Golfer, imported by
 * Scripts/import_golfer.py). Animations play directly on the mesh (no Anim Blueprint needed):
 * the first frame of a swing is the address pose, and the swing plays when a shot is struck.
 * Until the assets exist the character shows a placeholder cylinder.
 */
UCLASS()
class SKYLINKS_API AGolfCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	AGolfCharacter();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Server: walk up to a ball and face this direction. bPutting picks the putting stance. */
	void SetAddress(const FVector& InBallLocation, float InAimYaw, bool bPutting = false);

	/** Owning client: turn to aim now, and tell the server so spectators see it. */
	void SetLocalAim(float InAimYaw);

	/** Centres an overhead camera on a short-shot landing zone, or restores the address view. */
	void SetPreviewCamera(const FVector& LandingLocation, bool bUseLandingView);

	float GetAimYaw() const { return AimYaw; }
	FVector GetAddressBallLocation() const { return BallLocation; }

	/** Everyone: play the swing from the address pose. The ball should leave GetImpactDelay() later. */
	UFUNCTION(NetMulticast, Reliable)
	void MulticastPlaySwing(EGolferSwing Swing);

	/** Everyone: play a celebration or reaction after a shot. */
	UFUNCTION(NetMulticast, Reliable)
	void MulticastPlayReaction(EGolferReaction Reaction);

	/** Seconds from the start of the swing to club-on-ball; 0 while the golfer has no animations. */
	float GetImpactDelay(EGolferSwing Swing) const;

	/** How long a reaction is worth watching before play moves on (0 if none). */
	float GetReactionDuration(EGolferReaction Reaction) const;

	/** Everyone: stand by the buggy's driver door and climb in (bEnter) or sit in it and climb out. */
	UFUNCTION(NetMulticast, Reliable)
	void MulticastBuggyTransition(AGolfBuggy* Buggy, bool bEnter);

	/** Seconds the climb in/out takes (0 while the golfer has no animations). */
	float GetBuggyTransitionDuration(bool bEnter) const;

	UPROPERTY(VisibleAnywhere, Category = "Golf")
	TObjectPtr<USpringArmComponent> CameraArm;

	UPROPERTY(VisibleAnywhere, Category = "Golf")
	TObjectPtr<UCameraComponent> Camera;

	/** The club in the golfer's right hand. Positioned at address so the head sits behind the ball. */
	UPROPERTY(VisibleAnywhere, Category = "Golf")
	TObjectPtr<UStaticMeshComponent> Club;

	/** Shown until you assign a skeletal mesh to the character Blueprint. */
	UPROPERTY(VisibleAnywhere, Category = "Golf")
	TObjectPtr<UStaticMeshComponent> PlaceholderBody;

	UPROPERTY(EditDefaultsOnly, Category = "Golf|Body")
	TSoftObjectPtr<USkeletalMesh> GolferMeshAsset;

	/** The Mixamo golfer was rigged at about 95 cm tall; 1.9 makes it about 180 cm. Animations scale with it. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Body")
	float GolferScale = 1.9f;

	/** Mixamo characters face +Y after import; -90 turns them to face the actor's forward. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Body")
	float MeshYawOffset = -90.f;

	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> DriveAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> ChipAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> PuttAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> HoleInOneAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> CelebrateAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> PuttVictoryAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> PuttMissAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> BadShotAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> EnterBuggyAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> ExitBuggyAnim;

	/** The Mixamo car clips are slow for a golf cart; play them faster. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Buggy") float BuggyAnimRate = 1.5f;
	/** Driver's seat on the buggy, buggy-local cm at ground level (left seat). */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Buggy") FVector DriverSeat = FVector(-9.f, -28.f, 0.f);
	/** Where the enter clip starts, relative to the seat in buggy space (measured from the clip). */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Buggy") FVector EnterStartFromSeat = FVector(20.5f, -193.f, 0.f);

	UPROPERTY(EditDefaultsOnly, Category = "Golf|Club") TSoftObjectPtr<UStaticMesh> IronClubAsset;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Club") TSoftObjectPtr<UStaticMesh> PutterClubAsset;
	/** Hand bone the club follows through the swing (matched by suffix, so importer renaming doesn't matter). */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Club") FString ClubHandBone = TEXT("RightHand");
	/** How far the club sticks out past the middle of the hands (cm). */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Club") float ClubGripOverhang = 12.f;

	/** Club-on-ball times measured from the Mixamo clips (hands' fastest point, 30 fps). */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") float DriveImpactTime = 1.67f;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") float ChipImpactTime = 1.77f;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") float PuttImpactTime = 0.6f;

	/** Distance from the ball to the golfer's feet. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf")
	float StanceDistance = 70.f;

	/** How far the golfer stands back from the ball along the target line, so the ball sits mid-stance. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf")
	float AddressBackOffset = 30.f;

protected:
	virtual void BeginPlay() override;
	virtual void Restart() override;

	UFUNCTION(Server, Unreliable)
	void ServerSetAim(float InAimYaw);

	UFUNCTION()
	void OnRep_Address();

	void ApplyAddress();
	void LoadBody();
	UAnimSequence* SwingAsset(EGolferSwing Swing) const;
	UAnimSequence* ReactionAsset(EGolferReaction Reaction) const;
	void HoldAddressPose();
	void PlaceClub();
	/** Bone whose name is Suffix, or ends in ":Suffix" / "_Suffix"; NAME_None if the mesh has none. */
	FName FindBone(const TCHAR* Suffix) const;

	UPROPERTY(ReplicatedUsing = OnRep_Address)
	FVector BallLocation = FVector::ZeroVector;

	UPROPERTY(ReplicatedUsing = OnRep_Address)
	float AimYaw = 0.f;

	UPROPERTY(ReplicatedUsing = OnRep_Address)
	bool bPuttingStance = false;

	bool bHasBody = false;
	FVector LastPosedBall = FVector::ZeroVector;
	bool bLastPosedPutting = false;
	/** True while a swing or reaction is playing, so address updates don't cut it off. */
	bool bPlayingAction = false;
	FTimerHandle ClubTimer;
};
