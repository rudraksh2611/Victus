# Called by Inno Setup after install (and on uninstall). Registers or removes the logon task for VictusMorningBriefing.exe.
param(
    [Parameter(Mandatory = $true)]
    [string] $InstallDir,
    [ValidateSet("Register", "Unregister", "Uninstall")]
    [string] $Action = "Register",
    [int] $DelaySeconds = 45
)

$ErrorActionPreference = "Stop"
$TaskName = "VictusMorningBriefing"
$FlagName = "VictusNoLogonAutostart.txt"
$InstallDir = [System.IO.Path]::GetFullPath($InstallDir.TrimEnd('\', '/'))
$FlagPath = Join-Path $InstallDir $FlagName

function Remove-LogonTask {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
}

function Set-OptOutFlag {
    New-Item -Path $FlagPath -ItemType File -Force | Out-Null
}

function Remove-OptOutFlag {
    Remove-Item -Path $FlagPath -Force -ErrorAction SilentlyContinue
}

if ($Action -eq "Uninstall") {
    Remove-LogonTask
    Remove-OptOutFlag
    exit 0
}

if ($Action -eq "Unregister") {
    Remove-LogonTask
    Set-OptOutFlag
    exit 0
}

# Register
$launcher = Join-Path $InstallDir "launch_exe_at_logon.cmd"
$exe = Join-Path $InstallDir "VictusMorningBriefing.exe"
if (-not (Test-Path $launcher) -and -not (Test-Path $exe)) {
    Write-Error "VictusMorningBriefing.exe not found in $InstallDir"
    exit 1
}

$DelaySeconds = [Math]::Max(0, [Math]::Min($DelaySeconds, 600))

if (Test-Path $launcher) {
    $sta = New-ScheduledTaskAction -Execute $launcher -WorkingDirectory $InstallDir
}
else {
    $arg = "/c set `"VICTUS_AUTOSTART=1`" && cd /d `"$InstallDir`" && `"$exe`""
    $sta = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $arg
}

$userId = if ($env:USERDOMAIN -and $env:USERDOMAIN -ne $env:COMPUTERNAME) {
    "$env:USERDOMAIN\$env:USERNAME"
} else {
    $env:USERNAME
}
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT${DelaySeconds}S"
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $sta -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Remove-OptOutFlag
exit 0
