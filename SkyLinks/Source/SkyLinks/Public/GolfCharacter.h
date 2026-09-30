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
 * the replicated ball location and aim. Between shots (and in the lobby) the golfer roams: walks
 * under the player's control with a follow camera, and movement replicates like any character.
 *
 * The body is the owner's Meshy "Eccentric Golfer" with the golf clips retargeted onto him
 * (/Game/Characters/Eccentric, built by Art/Blender/build_eccentric_golfer.py, imported by Scripts/import_golfer.py). Animations play directly on the mesh (no Anim Blueprint needed):
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

	/** Everyone: play a celebration or reaction after a shot (the putt victory walks to CupLocation). */
	UFUNCTION(NetMulticast, Reliable)
	void MulticastPlayReaction(EGolferReaction Reaction, FVector CupLocation);

	/** Seconds from the start of the swing to club-on-ball; 0 while the golfer has no animations. */
	float GetImpactDelay(EGolferSwing Swing) const;

	/** How long a reaction is worth watching before play moves on (0 if none). */
	float GetReactionDuration(EGolferReaction Reaction) const;

	/** Everyone: stand by the buggy's driver door and climb in (bEnter) or sit in it and climb out. */
	UFUNCTION(NetMulticast, Reliable)
	void MulticastBuggyTransition(AGolfBuggy* Buggy, bool bEnter);

	/** Seconds the climb in/out takes (0 while the golfer has no animations). */
	float GetBuggyTransitionDuration(bool bEnter) const;

	/** Everyone: stay in the driver's seat (last frame of the climb in) and ride along with the buggy. */
	UFUNCTION(NetMulticast, Reliable)
	void MulticastSeatInBuggy(AGolfBuggy* Buggy);

	virtual void Tick(float DeltaSeconds) override;

	/** Server: walk freely (on foot, player-controlled) or stand still to be placed by code (address, buggy). */
	void SetRoaming(bool bRoam);
	bool IsRoaming() const { return bRoaming; }

	/** Everyone: out of the buggy and standing beside its driver's door (where the climb-out clip ends). */
	UFUNCTION(NetMulticast, Reliable)
	void MulticastStandBesideBuggy(AGolfBuggy* Buggy);

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

	/** Standing height in game (cm). The body is scaled to it from its own size (the Meshy golfer is about
	 *  171 cm, so about 1.05x); animations scale with it. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Body")
	float GolferHeight = 180.f;

	/** Mixamo characters face +Y after import; -90 turns them to face the actor's forward. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Body")
	float MeshYawOffset = -90.f;

	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> DriveAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> ChipAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> PuttAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> HoleInOneAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> CelebrateAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> PuttVictoryAnim;
	/** Where the putt victory clip's right hand goes into the cup, actor-local cm (measured at 3.7 s). */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") FVector CupPickupOffset = FVector(142.f, 54.f, 0.f);
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> PuttMissAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> BadShotAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> TeeUpAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> EnterBuggyAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> ExitBuggyAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> IdleAnim;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> WalkAnim;
	/** Ground speed (cm/s) the walk clip matches at play rate 1: about two 72 cm steps per 1.4 s cycle. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") float WalkAnimSpeed = 105.f;

	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") TSoftObjectPtr<UAnimSequence> RunAnim;
	/** Ground speed (cm/s) the run clip matches at play rate 1 (slower = a jog, faster = a sprint). */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") float RunAnimSpeed = 420.f;

	/** On-foot speed at pace 0 (a walk) and pace 1 (a run), cm/s. The player sets the pace by sliding up the GO bar. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Walking") float WalkSpeed = 170.f;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Walking") float RunSpeed = 600.f;
	/** Above this ground speed (cm/s) the legs switch from the walk clip to the run clip (a jog, then a run). */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Walking") float JogFromSpeed = 310.f;

	/** Which golfer this player is (0 the man, 1 his wife): the main menu will set it; C swaps it for now. */
	void ChooseBody(uint8 InBody);
	uint8 GetBody() const { return Body; }
	static int32 NumBodies();

	/** How fast to go on foot, 0 (walk) .. 1 (run). Local player: set every frame; sent on to the server. */
	void SetPace(float InPace);
	float GetPace() const { return Pace; }
	/** WALK / FAST WALK / JOG / RUN for a pace. */
	static FString GaitName(float InPace);

	/** The Mixamo car clips are slow for a golf cart; play them faster. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Buggy") float BuggyAnimRate = 1.5f;
	/** Driver's seat on the buggy, buggy-local cm at ground level (left seat). */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Buggy") FVector DriverSeat = FVector(-9.f, -28.f, 0.f);
	/** Where the enter clip starts, relative to the seat in buggy space (measured from the clip). */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Buggy") FVector EnterStartFromSeat = FVector(20.5f, -193.f, 0.f);
	/** The Mixamo car seat is higher than the buggy's (cushion 68 cm, roof 1.6 m): sink this much when seated. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Buggy") float SeatDrop = 20.f;

	UPROPERTY(EditDefaultsOnly, Category = "Golf|Club") TSoftObjectPtr<UStaticMesh> IronClubAsset;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Club") TSoftObjectPtr<UStaticMesh> PutterClubAsset;
	/** Hand bone the club follows through the swing (matched by suffix, so importer renaming doesn't matter). */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Club") FString ClubHandBone = TEXT("RightHand");
	/** How far the club sticks out past the middle of the hands (cm). */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Club") float ClubGripOverhang = 12.f;
	/** Where the club head rests after the stroke: this far outside (cm) and ahead of the right foot. */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Club") float ClubRestSide = 18.f;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Club") float ClubRestAhead = 12.f;

	/** Club-on-ball times measured from the Mixamo clips (hands' fastest point, 30 fps). */
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") float DriveImpactTime = 1.67f;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") float ChipImpactTime = 1.77f;
	UPROPERTY(EditDefaultsOnly, Category = "Golf|Animations") float PuttImpactTime = 1.24f;  // hands back at the ball

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

	UFUNCTION(Server, Unreliable)
	void ServerSetPace(float InPace);

	UFUNCTION(Server, Reliable)
	void ServerChooseBody(uint8 InBody);

	UPROPERTY(ReplicatedUsing = OnRep_Body)
	uint8 Body = 0;

	UFUNCTION()
	void OnRep_Body();
	void ApplyBody();
	/** Point every mesh / clip / club reference at this body's folder and take its size and speeds. */
	void PointAssetsAt(uint8 InBody);

	float Pace = 0.f;
	void ApplyPace();

	UFUNCTION()
	void OnRep_Address();

	void ApplyAddress();
	void LoadBody();
	UAnimSequence* SwingAsset(EGolferSwing Swing) const;
	UAnimSequence* ReactionAsset(EGolferReaction Reaction) const;
	void HoldAddressPose();
	void PlaceClub();
	void RestClub();
	void SetClubBetween(const FVector& Head, const FVector& Grip, const FVector& Forward, FName HandBone);
	/** Bone whose name is Suffix, or ends in ":Suffix" / "_Suffix"; NAME_None if the mesh has none. */
	FName FindBone(const TCHAR* Suffix) const;

	UPROPERTY(ReplicatedUsing = OnRep_Address)
	FVector BallLocation = FVector::ZeroVector;

	UPROPERTY(ReplicatedUsing = OnRep_Address)
	float AimYaw = 0.f;

	UPROPERTY(ReplicatedUsing = OnRep_Address)
	bool bPuttingStance = false;

	UPROPERTY(ReplicatedUsing = OnRep_Roaming)
	bool bRoaming = false;

	UFUNCTION()
	void OnRep_Roaming();
	void ApplyRoaming();
	void UpdateLocomotion();
	/** Idle or walk clip currently looping while roaming (null when an action or pose owns the mesh). */
	TWeakObjectPtr<UAnimSequence> LocomotionClip;

	bool bHasBody = false;
	FVector LastPosedBall = FVector::ZeroVector;
	bool bLastPosedPutting = false;
	/** True while a swing or reaction is playing, so address updates don't cut it off. */
	bool bPlayingAction = false;
	/** The club rests on the ground by the right foot (after the stroke, through reactions). */
	bool bClubResting = false;
	/** Length of the swing being played (0 when none): once it has run, the club goes to rest. */
	float SwingLength = 0.f;
	FTimerHandle ClubTimer;

	/** Climbing in or out of the buggy: Tick eases the body down into / up out of the low seat. */
	enum class EBuggyStep : uint8 { None, Entering, Seated, Exiting };
	EBuggyStep BuggyStep = EBuggyStep::None;
	TWeakObjectPtr<AGolfBuggy> RiddenBuggy;
	void SetSeatDrop(float Drop);
	void LeaveBuggy();
};
