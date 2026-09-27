# Windows rendering configuration — 2026-09-27

The editor displayed Missing Project Settings warnings for virtual shadow maps and Nanite because the project enabled those rendering features but inherited D3D12 shader model 5 from BaseEngine.ini.

DefaultEngine.ini now selects DX12 with PCD3D_SM6 for Windows. Android/iOS settings are unchanged. The fresh editor log confirms `RHI D3D12 with Feature Level SM6 is supported and will be used`, rhifeaturelevel=SM6, shaderplatform=PCD3D_SM6. This verifies the active rendering mode on Boss420's RTX 4060, not a mobile performance or lighting-quality acceptance.

A clean Development Editor build also succeeded with the session and HUD changes, after removing temporary swipe diagnostic logging. Editor restarted from the rebuilt DLL. Existing engine-header deprecation and non-preferred Visual Studio toolchain warnings remain.

The later SM6 gameplay preview exposed a separate Lumen warning: neither software distance fields nor hardware ray tracing were available. `r.GenerateMeshDistanceFields=True` now supplies the software tracing data required by the selected Lumen mode. This needs a fresh editor launch and distance-field generation; SM6 alone was not sufficient.
