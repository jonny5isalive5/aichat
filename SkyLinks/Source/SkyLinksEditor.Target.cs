using UnrealBuildTool;

public class SkyLinksEditorTarget : TargetRules
{
	public SkyLinksEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.V7;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("SkyLinks");
	}
}
