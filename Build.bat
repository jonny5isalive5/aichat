@echo off
rem Double-click to build the game's C++ (needed whenever Claude says "C++ changed"). Close Unreal Editor first.
setlocal
cd /d "%~dp0"
set "UE=C:\Program Files\Epic Games\UE_5.8"

tasklist /FI "IMAGENAME eq UnrealEditor.exe" | find /I "UnrealEditor.exe" >nul
if not errorlevel 1 (
    echo Unreal Editor is still open. Save All, close it, then run Build again.
    pause
    exit /b 1
)
if not exist "%UE%\Engine\Build\BatchFiles\Build.bat" (
    echo Could not find Unreal Engine 5.8 at %UE%. Send this window to Claude.
    pause
    exit /b 1
)

echo Building SkyLinks... this takes a minute or two.
call "%UE%\Engine\Build\BatchFiles\Build.bat" SkyLinksEditor Win64 Development "-Project=%~dp0SkyLinks\SkyLinks.uproject" -WaitMutex
if errorlevel 1 (
    echo.
    echo BUILD FAILED. Take a screenshot of the red error lines above and send it to Claude.
    pause
    exit /b 1
)
echo.
echo BUILD OK. You can open Unreal now.
pause
exit /b 0
