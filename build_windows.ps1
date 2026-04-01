# Build VictusMorningBriefing.exe (PyInstaller one-file, windowed).
# From the project folder:
#   powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
#
# Output: dist\VictusMorningBriefing.exe
# Copy config.example.json next to the exe, rename to config.json, then edit.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$VenvPip = Join-Path $ScriptDir ".venv\Scripts\pip.exe"
$VenvPyInstaller = Join-Path $ScriptDir ".venv\Scripts\pyinstaller.exe"

if ((Test-Path $VenvPip) -and (Test-Path $VenvPyInstaller)) {
    & $VenvPip install -q -r requirements.txt -r requirements-build.txt
    & $VenvPyInstaller --clean --noconfirm (Join-Path $ScriptDir "VictusMorningBriefing.spec")
} else {
    Write-Host "No .venv PyInstaller found; using python -m pip / PyInstaller."
    python -m pip install -q -r requirements.txt -r requirements-build.txt
    python -m PyInstaller --clean --noconfirm (Join-Path $ScriptDir "VictusMorningBriefing.spec")
}

$DistExe = Join-Path $ScriptDir "dist\VictusMorningBriefing.exe"
$Example = Join-Path $ScriptDir "config.example.json"
$DistExample = Join-Path $ScriptDir "dist\config.example.json"

$LauncherCmd = Join-Path $ScriptDir "launch_exe_at_logon.cmd"
$DistLauncher = Join-Path $ScriptDir "dist\launch_exe_at_logon.cmd"

if (Test-Path $Example) {
    Copy-Item -Force $Example $DistExample
}
if (Test-Path $LauncherCmd) {
    Copy-Item -Force $LauncherCmd $DistLauncher
}

Write-Host ""
Write-Host "Built: $DistExe"
if (Test-Path $DistExample) {
    Write-Host "Copied: $DistExample"
}
if (Test-Path $DistLauncher) {
    Write-Host "Copied: $DistLauncher (optional Task Scheduler launcher with VICTUS_AUTOSTART=1)"
}
Write-Host "First run opens the setup wizard if config.json is missing. Re-run with --setup to change options."
Write-Host ""
