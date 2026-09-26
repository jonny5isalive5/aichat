using UnrealBuildTool;

public class SkyLinksTarget : TargetRules
{
	public SkyLinksTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_5;
		ExtraModuleNames.Add("SkyLinks");
	}
}
