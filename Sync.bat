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

echo Saving your work...
git checkout -q %BRANCH% || goto fail
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
