@echo off
REM Optional launcher next to VictusMorningBriefing.exe. Passes --autostart (same as Task Scheduler should use).
cd /d "%~dp0"
if not exist "VictusMorningBriefing.exe" (
    echo VictusMorningBriefing.exe not found in this folder.
    exit /b 1
)
"%~dp0VictusMorningBriefing.exe" --autostart
