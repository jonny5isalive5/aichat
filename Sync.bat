@echo off
rem Double-click to save your editor work to GitHub AND get Claude's latest changes, in one go.
rem Close Unreal Editor first. No vim, no merge messages: everything is automatic.
setlocal
cd /d "%~dp0"
set BRANCH=claude/admiring-volta-8o59gg
set GIT_EDITOR=true
set GIT_MERGE_AUTOEDIT=no
where git >nul 2>nul || set "PATH=C:\Program Files\Git\cmd;%PATH%"

tasklist /FI "IMAGENAME eq UnrealEditor.exe" | find /I "UnrealEditor.exe" >nul
if not errorlevel 1 (
    echo Unreal Editor is still open. Save All, close it, then run Sync again.
    pause
    exit /b 1
)

echo Checking this copy is up to date...
git checkout -q %BRANCH% || goto fail
git fetch -q origin %BRANCH% || goto fail
rem Danger only if GitHub has new Unreal content AND this copy has its own unsaved content changes: uploading
rem could then overwrite newer maps/assets with old ones (that happened once with an old copy). Code, scripts and
rem island exports from Claude are fine to pull on top of your editor work.
set REMOTE_CONTENT=
for /f %%f in ('git diff --name-only HEAD...origin/%BRANCH% -- SkyLinks/Content') do set REMOTE_CONTENT=1
set LOCAL_CONTENT=
for /f %%f in ('git status --porcelain -- SkyLinks/Content') do set LOCAL_CONTENT=1
if defined REMOTE_CONTENT if defined LOCAL_CONTENT (
    echo.
    echo STOPPED: GitHub has newer Unreal content AND this copy has its own content changes.
    echo Uploading could overwrite newer work, so nothing was changed. Send this window to Claude.
    pause
    exit /b 1
)

echo Saving your work...
git add -A || goto fail
rem Finish any merge left half-done from before, otherwise commit what you changed (if anything).
git rev-parse -q --verify MERGE_HEAD >nul 2>nul
if not errorlevel 1 (
    git commit -q --no-edit || goto fail
) else (
    git diff --cached --quiet || git commit -q -m "Editor work %DATE% %TIME%" || goto fail
)

echo Getting the latest changes...
rem If both sides touched the same file, YOUR version wins (your maps and assets are never overwritten).
git pull -q --no-rebase --no-edit -X ours origin %BRANCH% || goto fail

echo Uploading...
git push -q origin %BRANCH% || goto fail

echo.
echo ALL SYNCED. Your work is on GitHub and you have the latest updates.
echo If C++ changed, build before opening the editor.
pause
exit /b 0

:fail
echo.
echo Something went wrong. Take a screenshot of this window and send it to Claude.
pause
exit /b 1
