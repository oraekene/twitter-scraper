# Weekly hiring hunt: read the bookmark database and report new openings.
#
#   pwsh -File weekly.ps1                 hunt the last 8 days
#   pwsh -File weekly.ps1 -Days 14        hunt a wider window
#   pwsh -File weekly.ps1 -Sync           also pull new bookmarks first (rarely needed)
#
# Sync is opt-in because the machine already has a task called
# TwitterBookmarkWeeklyScan that syncs bookmarks every Sunday. Do not run both
# at once: ft cannot rename bookmarks.db over itself while this script holds it
# open, and that failure is what weekly_scan.py logs as EPERM.

param(
    [int]$Days = 8,
    [switch]$Sync,
    [int]$KeepRuns = 12
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Env:PYTHONIOENCODING = 'utf-8'

$RunDir = Join-Path (Split-Path -Parent $Root) 'out\weekly'
$LogDir = Join-Path $RunDir 'logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
$Log = Join-Path $LogDir "$Stamp.log"

function Say($m) {
    $line = "$(Get-Date -Format 'HH:mm:ss')  $m"
    Write-Output $line
    Add-Content -LiteralPath $Log -Value $line
}

Say "hiring hunt started, looking back $Days days, mode $(if ($Sync) { 'sync + search' } else { 'search only' })"

if ($Sync) {
    Say 'warning: TwitterBookmarkWeeklyScan may already be syncing, check for EPERM'
    & python (Join-Path $Root '..\sync_bookmarks.py') *>> $Log
    if ($LASTEXITCODE -ne 0) { Say "sync returned $LASTEXITCODE, searching anyway" }
}

$Md = Join-Path $RunDir "$Stamp.md"
$Json = Join-Path $RunDir "$Stamp.json"

& python (Join-Path $Root 'search.py') --search hiring-bookmarks --days $Days --md $Md --json $Json *>> $Log
if ($LASTEXITCODE -ne 0) {
    Say "search failed, code $LASTEXITCODE. See $Log"
    exit $LASTEXITCODE
}

Say "wrote $Md"
Say "wrote $Json"

# Keep the last N runs so the folder does not grow forever.
Get-ChildItem -Path $RunDir -Filter '*.md' | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $KeepRuns | Remove-Item -Force
Get-ChildItem -Path $RunDir -Filter '*.json' | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $KeepRuns | Remove-Item -Force

# -------- registering with Task Scheduler, run once --------
# Pick a time the other task is not using. It fires Sunday 10:00 to 16:00 hourly,
# so anything before 09:00 or after 17:00 avoids contention on bookmarks.db.
#
# pwsh -Command "Register-ScheduledTask -TaskName 'hiring-weekly' -Description 'Weekly hunt for hiring posts' -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 8am) -Action (New-ScheduledTaskAction -Execute 'pwsh' -Argument '-NoProfile -WindowStyle Hidden -File \"C:\Users\rotim\Documents\twitter scraper\hiring\weekly.ps1\"') -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries)"
#
# Unregister-ScheduledTask -TaskName 'hiring-weekly' -Confirm:$false
