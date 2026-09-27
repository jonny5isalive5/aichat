using UnrealBuildTool;

public class SkyLinks : ModuleRules
{
	public SkyLinks(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput",
			"PhysicsCore", "NetCore", "OnlineSubsystem", "OnlineSubsystemUtils",
			"OnlineSubsystemEOS", "VoiceChat", "EOSSDK"
		});

		DynamicallyLoadedModuleNames.Add("OnlineSubsystemNull");
	}
}
