param(
    [string]$TaskName = "GitHub Radar",
    [string]$ProjectRoot = "D:\Documents\Utilcode\github\github-radar",
    [string]$Time = "09:00"
)

$scriptPath = Join-Path $ProjectRoot "scripts\run-radar.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
$triggerMonday = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday -At $Time
$triggerThursday = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Thursday -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($triggerMonday, $triggerThursday) -Settings $settings -Description "Generate GitHub Radar reports twice a week."
