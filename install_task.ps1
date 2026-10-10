# One-time setup. Creates the Sunday 10:00 weekly scan task.
# Safe to re-run: it replaces any previous version.
# Runs as you, in your session, so the laptop must be on and you logged in.
# That is fine here: the sync reads credentials from .env, not from a browser.

$taskName = "TwitterBookmarkWeeklyScan"
$workDir  = "C:\Users\rotim\Documents\twitter scraper"
$python   = "C:\Users\rotim\AppData\Local\Python\pythoncore-3.14-64\python.exe"

$action = New-ScheduledTaskAction `
    -Execute $python `
    -Argument "weekly_scan.py" `
    -WorkingDirectory $workDir

# One trigger. StartWhenAvailable covers "laptop was asleep at 10:00": Windows runs
# the missed task as soon as the session comes up. Hourly retry triggers would be
# seven no-op wake-ups, because each sync is incremental.
# RestartCount covers a crash mid-thread-expansion. Safe to restart because
# weekly_scan.py checkpoints threads-index.json after every tweet, so a restart
# resumes rather than redoing.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At ([DateTime]::Today.AddHours(10))

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

# Interactive: runs in your logged-in session. S4U would need admin rights.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Weekly X/Twitter bookmark sync and thread expansion" `
    -Force | Out-Null

Write-Host "Task '$taskName' created. Sunday 10:00, runs on wake if missed."
Get-ScheduledTask -TaskName $taskName |
    Get-ScheduledTaskInfo |
    Format-List TaskName, NextRunTime, LastRunTime, LastTaskResult