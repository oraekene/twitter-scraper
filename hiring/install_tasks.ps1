# One-time setup. Registers the four weekly report tasks on separate days, so
# the hiring reports and the opportunities reports never share a slot.
#
#   hiring-weekly                Monday 8am    weekly.ps1         -Only hiring
#   hiring-twitter-weekly        Tuesday 8am   weekly-twitter.ps1 -Only hiring
#   opportunities-weekly         Thursday 8am  weekly.ps1         -Only opportunities
#   opportunities-twitter-weekly Friday 8am    weekly-twitter.ps1 -Only opportunities
#
# Change a day by editing the table below and running this file again; -Force
# replaces the existing task instead of failing.
#
# Safe to re-run. Runs as you in your logged-in session, so the laptop must be
# on and you logged in, which is fine: every report reads .env or the database
# and never a browser. Interactive principal, so no admin rights are needed.
#
#   pwsh -File install_tasks.ps1
#
# Remove one with:
#   Unregister-ScheduledTask -TaskName opportunities-weekly -Confirm:$false

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
$pwsh = (Get-Command pwsh).Source

$jobs = @(
    @{ Name = 'hiring-weekly';                Script = 'weekly.ps1';         Only = 'hiring';        Day = 'Monday';   Minutes = 30 },
    @{ Name = 'hiring-twitter-weekly';        Script = 'weekly-twitter.ps1'; Only = 'hiring';        Day = 'Tuesday';  Minutes = 45 },
    @{ Name = 'opportunities-weekly';         Script = 'weekly.ps1';         Only = 'opportunities'; Day = 'Thursday'; Minutes = 30 },
    @{ Name = 'opportunities-twitter-weekly'; Script = 'weekly-twitter.ps1'; Only = 'opportunities'; Day = 'Friday';   Minutes = 45 }
)

foreach ($job in $jobs) {
    $action = New-ScheduledTaskAction `
        -Execute $pwsh `
        -Argument "-NoProfile -WindowStyle Hidden -File `"$root\hiring\$($job.Script)`" -Only $($job.Only)" `
        -WorkingDirectory "$root\hiring"

    # StartWhenAvailable covers "laptop was asleep at 8am".
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $job.Day -At 8am

    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Minutes $job.Minutes) `
        -DontStopIfGoingOnBatteries `
        -AllowStartIfOnBatteries

    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Limited

    Register-ScheduledTask `
        -TaskName $job.Name `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Weekly $($job.Only) report from $($job.Script)" `
        -Force | Out-Null

    Write-Host "registered $($job.Name): $($job.Day) 8am, -Only $($job.Only)"
}

Get-ScheduledTask -TaskName ($jobs.Name) | Select-Object TaskName, State
