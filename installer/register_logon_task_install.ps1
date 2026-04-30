# Called by Inno Setup after install (and on uninstall). Registers or removes the logon task for VictusMorningBriefing.exe.
#
# Strategy: try the modern ScheduledTasks PowerShell module first; if anything
# in that path fails (security software, restricted environment, missing
# module), fall back to schtasks.exe with a hand-rolled task XML — which has
# been on Windows since XP and works without PowerShell module loading.
# Always verify after registering and exit non-zero if the task is missing,
# so the installer can show the user a clear warning instead of silently
# leaving them without autostart.
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

function Test-LogonTask {
    $r = & schtasks.exe /Query /TN $TaskName 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Remove-LogonTask {
    try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue } catch {}
    & schtasks.exe /Delete /TN $TaskName /F 2>$null | Out-Null
}

function Set-OptOutFlag   { New-Item -Path $FlagPath -ItemType File -Force | Out-Null }
function Remove-OptOutFlag { Remove-Item -Path $FlagPath -Force -ErrorAction SilentlyContinue }

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

# ----- Register --------------------------------------------------------------

$exe = Join-Path $InstallDir "VictusMorningBriefing.exe"
if (-not (Test-Path $exe)) {
    Write-Error "VictusMorningBriefing.exe not found in $InstallDir"
    exit 1
}

$DelaySeconds = [Math]::Max(0, [Math]::Min($DelaySeconds, 600))

# Username with optional domain (matches Task Scheduler "Run only when user is logged on")
$userId = if ($env:USERDOMAIN -and $env:USERDOMAIN -ne $env:COMPUTERNAME) {
    "$env:USERDOMAIN\$env:USERNAME"
} else {
    $env:USERNAME
}

# Strategy A: ScheduledTasks PowerShell module
try {
    $sta = New-ScheduledTaskAction -Execute $exe -Argument "--autostart" -WorkingDirectory $InstallDir
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
} catch {
    Write-Output "Strategy A (Register-ScheduledTask) failed: $($_.Exception.Message)"
}

if (Test-LogonTask) {
    Remove-OptOutFlag
    exit 0
}

# Strategy B: schtasks.exe /Create /XML with hand-rolled XML (no PS modules required)
$xmlPath = Join-Path ([System.IO.Path]::GetTempPath()) ("VictusLogonTask_{0}.xml" -f ([System.Guid]::NewGuid().ToString("N")))
$exeXml = [System.Security.SecurityElement]::Escape($exe)
$dirXml = [System.Security.SecurityElement]::Escape($InstallDir)
$userXml = [System.Security.SecurityElement]::Escape($userId)
$nowIso = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Date>$nowIso</Date>
    <Author>$userXml</Author>
    <Description>Launches Victus Voice Assistant after the user signs in.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>$userXml</UserId>
      <Delay>PT${DelaySeconds}S</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$userXml</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <DisallowStartOnRemoteAppSession>false</DisallowStartOnRemoteAppSession>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$exeXml</Command>
      <Arguments>--autostart</Arguments>
      <WorkingDirectory>$dirXml</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

# Task Scheduler XML must be UTF-16 with BOM.
[System.IO.File]::WriteAllText($xmlPath, $xml, [System.Text.Encoding]::Unicode)

try {
    & schtasks.exe /Create /TN $TaskName /XML "$xmlPath" /F | Out-Null
} catch {
    Write-Output "Strategy B (schtasks /XML) threw: $($_.Exception.Message)"
} finally {
    Remove-Item -Path $xmlPath -Force -ErrorAction SilentlyContinue
}

if (Test-LogonTask) {
    Remove-OptOutFlag
    exit 0
}

Write-Output "Both registration strategies failed for $TaskName."
exit 1
