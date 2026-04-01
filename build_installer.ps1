# Build VictusMorningBriefing.exe, then compile the Inno Setup wizard installer (Next -> Next -> Finish).
#
# Prerequisites:
#   1) Python venv + PyInstaller (build_windows.ps1 handles this)
#   2) Inno Setup 6: https://jrsoftware.org/isinfo.php  (install with default options)
#
# From the project folder:
#   powershell -ExecutionPolicy Bypass -File .\build_installer.ps1
#
# Output: Output\VictusVoiceAssistant_Setup.exe

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "Step 1: Building application (.exe)..."
& (Join-Path $Root "build_windows.ps1")

$DistExe = Join-Path $Root "dist\VictusMorningBriefing.exe"
if (-not (Test-Path $DistExe)) {
    Write-Error "dist\VictusMorningBriefing.exe not found after build. Fix PyInstaller errors above."
    exit 1
}

$Iscc = $null
foreach ($p in @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )) {
    if (Test-Path $p) {
        $Iscc = $p
        break
    }
}

if (-not $Iscc) {
    Write-Error @"
Inno Setup 6 compiler (ISCC.exe) not found.

Install Inno Setup 6 from: https://jrsoftware.org/isinfo.php
Then run this script again.
"@
    exit 1
}

$Iss = Join-Path $Root "installer\VictusSetup.iss"
if (-not (Test-Path $Iss)) {
    Write-Error "Missing $Iss"
    exit 1
}

Write-Host ""
Write-Host "Step 2: Compiling installer with Inno Setup..."
& $Iscc $Iss

$Out = Join-Path $Root "Output\VictusVoiceAssistant_Setup.exe"
Write-Host ""
if (Test-Path $Out) {
    Write-Host "Done: $Out"
} else {
    Write-Warning "Expected output not found at $Out (check ISCC output above)."
}
