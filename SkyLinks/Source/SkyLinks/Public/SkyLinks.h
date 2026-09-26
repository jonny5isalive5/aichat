#pragma once

#include "CoreMinimal.h"

// Trace channel every golf ball sweep uses (see DefaultEngine.ini). Pawns and balls ignore it.
#define ECC_GolfBall ECC_GameTraceChannel1

// Physical surface types (see DefaultEngine.ini). Assign them through Physical Materials.
#define SURFACE_Fairway     SurfaceType1
#define SURFACE_Rough       SurfaceType2
#define SURFACE_Bunker      SurfaceType3
#define SURFACE_Green       SurfaceType4
#define SURFACE_Water       SurfaceType5
#define SURFACE_OutOfBounds SurfaceType6

DECLARE_LOG_CATEGORY_EXTERN(LogSkyLinks, Log, All);
