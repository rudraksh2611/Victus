# Installs a Windows Scheduled Task so the briefing runs when you sign in to Windows
# (after boot or after opening the laptop and logging in).
#
# Run once in PowerShell (your user account is enough — Admin usually not required):
#   cd "D:\RSB Career\Projects\Victus Voice Assistant"
#   powershell -ExecutionPolicy Bypass -File .\setup_login_task.ps1
#
# Remove:  powershell -ExecutionPolicy Bypass -File .\remove_login_task.ps1
#
# After login, the script waits until the internet is reachable (see internet_* in config.json),
# then runs immediately. It does not run again when Wi-Fi reconnects later; only once per logon.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptDir = [System.IO.Path]::GetFullPath($ScriptDir)

$VenvPythonW = Join-Path $ScriptDir ".venv\Scripts\pythonw.exe"
$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPythonW) {
    $Python = $VenvPythonW
} elseif (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $Python) { $Python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source }
}
if (-not $Python) {
    Write-Error "No Python found. In this folder run: python -m venv .venv  then  .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

$Briefing = Join-Path $ScriptDir "morning_briefing.py"
if (-not (Test-Path $Briefing)) {
    Write-Error "morning_briefing.py not found at $Briefing"
    exit 1
}

$TaskName = "VictusMorningBriefing"
$UserId = if ($env:USERDOMAIN -and $env:USERDOMAIN -ne $env:COMPUTERNAME) {
    "$env:USERDOMAIN\$env:USERNAME"
} else {
    $env:USERNAME
}

$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Briefing`"" -WorkingDirectory $ScriptDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

$Desc = "Victus Voice Assistant: weather, India news, time. Runs at Windows sign-in. See config.json in this folder."

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description $Desc -Force | Out-Null

Write-Host ""
Write-Host "Installed scheduled task: $TaskName"
Write-Host "  Runs when you sign in to Windows (after boot or laptop open + login)."
Write-Host "  Waits until internet is available, then starts immediately (no fixed delay)."
Write-Host "  Turning Wi-Fi off/on later does not run it again until your next sign-in."
Write-Host "  If you hear nothing after login, see TROUBLESHOOTING.txt and:"
Write-Host "    %LOCALAPPDATA%\VictusVoiceAssistant\briefing.log"
Write-Host "  Python: $Python"
Write-Host "  Folder: $ScriptDir"
Write-Host ""
Write-Host "Optional - also run when you unlock the PC (wake from sleep without signing out):"
Write-Host "  1. Open Task Scheduler  -> Task Scheduler Library -> $TaskName"
Write-Host "  2. Triggers tab -> New -> Begin the task: On workstation unlock -> OK"
Write-Host ""
Write-Host ('Remove later: powershell -ExecutionPolicy Bypass -File "' + $ScriptDir + '\remove_login_task.ps1"')
Write-Host ""
