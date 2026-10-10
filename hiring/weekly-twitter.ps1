# Weekly hunt on X. Runs two passes and writes two reports, because they have
# different shapes: a search can find anyone, a watchlist only covers accounts
# you already know about. A general search for "hiring" is noisy, so the
# watchlist pass is usually the better read.
#
#   pwsh -File weekly-twitter.ps1                 both passes, last 7 days
#   pwsh -File weekly-twitter.ps1 -Days 3         tighter window
#   pwsh -File weekly-twitter.ps1 -WatchlistOnly  skip the noisy search pass
#
# If the search pass dies with HTTP 404, the patch was lost on upgrade. Run
#   node fix-twitter-cli.js
# The watchlist pass does not depend on that patch, so it still works.

param(
    [int]$Days = 7,
    [int]$Limit = 50,
    [int]$MinLikes = 20,
    [int]$KeepRuns = 12,
    [string]$Query = '',
    [switch]$WatchlistOnly
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Env:PYTHONIOENCODING = 'utf-8'

$RunDir = Join-Path (Split-Path -Parent $Root) 'out\weekly-twitter'
$LogDir = Join-Path $RunDir 'logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
$Log = Join-Path $LogDir "$Stamp.log"

function Say($m) {
    $line = "$(Get-Date -Format 'HH:mm:ss')  $m"
    Write-Output $line
    Add-Content -LiteralPath $Log -Value $line
}

Say "twitter hunt started, last $Days days"

function Run-Pass($Name, $ScriptArgs) {
    $Md = Join-Path $RunDir "$Stamp-$Name.md"
    $Json = Join-Path $RunDir "$Stamp-$Name.json"
    & python (Join-Path $Root 'search.py') @ScriptArgs --md $Md --json $Json *>> $Log
    if ($LASTEXITCODE -ne 0) {
        Say "$Name pass FAILED, code $LASTEXITCODE"
        return
    }
    Say "$Name pass wrote $Md"
}

if (-not $WatchlistOnly) {
    # No -Query means the full 81 phrase set, sent in batches. X caps one query
    # at 512 characters and the whole set is 1329, so it is split automatically.
    $searchArgs = @('--live', '--limit', $Limit, '--days', $Days, '--min-likes', $MinLikes)
    if ($Query) { $searchArgs += @('--query', $Query) }
    Run-Pass 'search' $searchArgs
}
Run-Pass 'watchlist' @('--watchlist', (Join-Path $Root 'watchlist.txt'),
                       '--limit', $Limit, '--days', $Days)

Get-ChildItem -Path $RunDir -Filter '*.md' | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip ($KeepRuns * 2) | Remove-Item -Force
Get-ChildItem -Path $RunDir -Filter '*.json' | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip ($KeepRuns * 2) | Remove-Item -Force

# -------- registering with Task Scheduler, run once --------
# Keep this clear of TwitterBookmarkWeeklyScan, which fires Sunday 10:00 to 16:00
# and already reads .env. Two jobs at once is fine here because this one only
# reads bookmarks from a watchlist, but there is no reason to overlap.
#
# pwsh -Command "Register-ScheduledTask -TaskName 'hiring-twitter-weekly' -Description 'Weekly hunt for openings on X' -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At 8am) -Action (New-ScheduledTaskAction -Execute 'pwsh' -Argument '-NoProfile -WindowStyle Hidden -File \"C:\Users\rotim\Documents\twitter scraper\hiring\weekly-twitter.ps1\"') -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries)"
#
# Unregister-ScheduledTask -TaskName 'hiring-twitter-weekly' -Confirm:$false