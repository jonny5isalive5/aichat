using UnrealBuildTool;

public class SkyLinksEditorTarget : TargetRules
{
	public SkyLinksEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_5;
		ExtraModuleNames.Add("SkyLinks");
	}
}
