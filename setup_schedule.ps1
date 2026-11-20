# Schedules the morning digest (run once in PowerShell from this folder).
# Checks every 30 minutes from 7 AM to midnight, and at sign-in; if a check was
# missed because the laptop was off or asleep, it runs as soon as it's back.
# scheduled_run.py makes sure the digest is delivered only once a day.

$dir = $PSScriptRoot
$action = New-ScheduledTaskAction -Execute "$dir\.venv\Scripts\pythonw.exe" `
    -Argument "`"$dir\scheduled_run.py`"" -WorkingDirectory $dir

$daily = New-ScheduledTaskTrigger -Daily -At 7:00AM
$every30 = New-ScheduledTaskTrigger -Once -At 7:00AM `
    -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Hours 17)
$daily.Repetition = $every30.Repetition
$atSignIn = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "Home Help Desk morning digest" -Action $action `
    -Trigger @($daily, $atSignIn) -Settings $settings -Force `
    -Description "Delivers the Home Help Desk morning digest once a day (7 AM, or first check after the laptop is on)." |
    Select-Object TaskName, State
