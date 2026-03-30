# Removes the Victus morning briefing scheduled task.
$TaskName = "VictusMorningBriefing"
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
if ($?) {
    Write-Host "Removed task: $TaskName"
} else {
    Write-Host "Task '$TaskName' was not found (already removed?)."
}
