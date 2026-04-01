@echo off
REM Place next to VictusMorningBriefing.exe. Point the scheduled task at this file
REM so VICTUS_AUTOSTART=1 is set (same idea as launch_at_logon.ps1 for Python).
setlocal
set "VICTUS_AUTOSTART=1"
cd /d "%~dp0"
if not exist "VictusMorningBriefing.exe" (
    echo VictusMorningBriefing.exe not found in this folder.
    exit /b 1
)
"%~dp0VictusMorningBriefing.exe"
