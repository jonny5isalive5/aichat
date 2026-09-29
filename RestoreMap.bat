@echo off
rem Double-click to throw away the map changes on this PC and put back the Course map as it is on GitHub.
rem Use it when a script or a mistake has messed up the level. Close Unreal Editor first.
setlocal
cd /d "%~dp0"
set BRANCH=claude/admiring-volta-8o59gg
where git >nul 2>nul || set "PATH=C:\Program Files\Git\cmd;%PATH%"

tasklist /FI "IMAGENAME eq UnrealEditor.exe" | find /I "UnrealEditor.exe" >nul
if not errorlevel 1 (
    echo Unreal Editor is still open. Close it WITHOUT saving, then run this again.
    pause
    exit /b 1
)

git fetch -q origin %BRANCH% || goto fail
git checkout origin/%BRANCH% -- SkyLinks/Content/Maps/Course.umap || goto fail
echo.
echo MAP RESTORED from GitHub. Open the editor and check it, then use Sync.bat as normal.
pause
exit /b 0

:fail
echo.
echo Something went wrong. Take a screenshot of this window and send it to Claude.
pause
exit /b 1
