"""Import the owner's Meshy buggy parts into the existing runtime mesh paths.
Run through Aura after creating M_MeshyBuggy. Does not rebuild or save Course.
"""
import unreal
from pathlib import Path
src=Path(unreal.Paths.project_dir())/'Art/BuggyMeshy'
lib=unreal.EditorAssetLibrary
tools=unreal.AssetToolsHelpers.get_asset_tools()
pm=unreal.load_asset('/Game/Course/Materials/PM_Rough')
assert pm
def imp(path,dest,name,options=None):
 t=unreal.AssetImportTask()
 for k,v in [('filename',str(path)),('destination_path',dest),('destination_name',name),('automated',True),('replace_existing',True),('save',True)]:t.set_editor_property(k,v)
 if options:t.set_editor_property('options',options)
 tools.import_asset_tasks([t])
 obj=unreal.load_asset(dest+'/'+name);assert obj
 return obj
for p in sorted(src.glob('T_Buggy_*.png')):
 t=imp(p,'/Game/Vehicles/MeshyBuggy',p.stem);t.modify()
 if 'Normal' in p.stem:
  t.set_editor_property('CompressionSettings',unreal.TextureCompressionSettings.TC_NORMALMAP);t.set_editor_property('SRGB',False)
 elif 'BaseColor' not in p.stem:
  t.set_editor_property('CompressionSettings',unreal.TextureCompressionSettings.TC_MASKS);t.set_editor_property('SRGB',False)
 lib.save_loaded_asset(t)
print('Meshy buggy textures imported')
