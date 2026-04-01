# Installs a Windows Scheduled Task so the briefing runs when you sign in to Windows
# (after boot or after opening the laptop and logging in).
#
# Run once in PowerShell (your user account is enough — Admin usually not required):
#   cd "D:\RSB Career\Projects\Victus Voice Assistant"
#   powershell -ExecutionPolicy Bypass -File .\setup_login_task.ps1
#
# Remove:  powershell -ExecutionPolicy Bypass -File .\remove_login_task.ps1
#
# After login, Windows waits DelayAfterLogonSeconds (gives shell, Wi‑Fi, audio time to settle),
# then launch_at_logon.ps1 runs morning_briefing.py with VICTUS_AUTOSTART=1 for extra in-app delays.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptDir = [System.IO.Path]::GetFullPath($ScriptDir)

# How long after sign-in before the task starts (ISO 8601 duration, e.g. PT45S = 45 seconds).
# Increase if the briefing still starts before Wi‑Fi or speakers are ready.
$DelayAfterLogonSeconds = 45

$Briefing = Join-Path $ScriptDir "morning_briefing.py"
$Launcher = Join-Path $ScriptDir "launch_at_logon.ps1"

if (-not (Test-Path $Briefing)) {
    Write-Error "morning_briefing.py not found at $Briefing"
    exit 1
}
if (-not (Test-Path $Launcher)) {
    Write-Error "launch_at_logon.ps1 not found at $Launcher"
    exit 1
}

$TaskName = "VictusMorningBriefing"
$UserId = if ($env:USERDOMAIN -and $env:USERDOMAIN -ne $env:COMPUTERNAME) {
    "$env:USERDOMAIN\$env:USERNAME"
} else {
    $env:USERNAME
}

$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Launcher`"" `
    -WorkingDirectory $ScriptDir

$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Trigger.Delay = "PT$($DelayAfterLogonSeconds)S"

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
Write-Host "  Starts $DelayAfterLogonSeconds s after sign-in (lets desktop, network, and audio initialize)."
Write-Host "  Then the app waits for internet and applies delays from config.json (login_delay_seconds, etc.)."
Write-Host "  Turning Wi-Fi off/on later does not run it again until your next sign-in."
Write-Host "  If you hear nothing after login, see TROUBLESHOOTING.txt and:"
Write-Host "    %LOCALAPPDATA%\VictusVoiceAssistant\briefing.log"
Write-Host "  Launcher: $Launcher"
Write-Host "  Folder: $ScriptDir"
Write-Host ""
Write-Host "Optional - also run when you unlock the PC (wake from sleep without signing out):"
Write-Host "  1. Open Task Scheduler  -> Task Scheduler Library -> $TaskName"
Write-Host "  2. Triggers tab -> New -> Begin the task: On workstation unlock -> OK"
Write-Host ""
Write-Host ('Remove later: powershell -ExecutionPolicy Bypass -File "' + $ScriptDir + '\remove_login_task.ps1"')
Write-Host ""
