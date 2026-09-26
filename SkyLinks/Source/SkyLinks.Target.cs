using UnrealBuildTool;

public class SkyLinksTarget : TargetRules
{
	public SkyLinksTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.V7;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("SkyLinks");
	}
}
