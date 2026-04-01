# Launched by the Windows scheduled task at sign-in.
# Sets VICTUS_AUTOSTART so morning_briefing can apply extra bootstrap delays.
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptDir = [System.IO.Path]::GetFullPath($ScriptDir)

$env:VICTUS_AUTOSTART = "1"

$VenvPythonW = Join-Path $ScriptDir ".venv\Scripts\pythonw.exe"
$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$Briefing = Join-Path $ScriptDir "morning_briefing.py"

if (-not (Test-Path $Briefing)) {
    exit 1
}

Set-Location $ScriptDir

if (Test-Path $VenvPythonW) {
    & $VenvPythonW $Briefing
} elseif (Test-Path $VenvPython) {
    & $VenvPython $Briefing
} else {
    $py = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $py) { $py = (Get-Command python.exe -ErrorAction SilentlyContinue).Source }
    if (-not $py) { exit 1 }
    & $py $Briefing
}
