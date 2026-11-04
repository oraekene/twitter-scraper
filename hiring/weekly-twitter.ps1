# Weekly hunt on X. Runs two hiring passes and one opportunities pass, because
# they have different shapes: a search can find anyone, a watchlist only covers
# accounts you already know about. A general search for "hiring" is noisy, so
# the watchlist pass is usually the better read.
#
#   pwsh -File weekly-twitter.ps1                 all passes, last 7 days
#   pwsh -File weekly-twitter.ps1 -Only hiring    search plus watchlist only
#   pwsh -File weekly-twitter.ps1 -Only opportunities   live opportunities only
#   pwsh -File weekly-twitter.ps1 -Days 3         tighter window
#   pwsh -File weekly-twitter.ps1 -WatchlistOnly  skip the noisy search pass
#
# The halves are scheduled separately, so one task runs -Only hiring and another
# runs -Only opportunities on a different day.
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
    [switch]$WatchlistOnly,
    [ValidateSet('all', 'hiring', 'opportunities')]
    [string]$Only = 'all'
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

Say "twitter hunt started, half=$Only, last $Days days"

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

if ($Only -in 'all', 'hiring') {
    if (-not $WatchlistOnly) {
        # The query comes from searches.json, so editing it in the panel changes
        # what this runs. X caps one query at 512 characters, so a saved search
        # has to fit.
        $SearchName = if ($Query) { $null } else { 'hiring-live' }
        $searchArgs = @('--live', '--limit', $Limit, '--days', $Days, '--min-likes', $MinLikes)
        if ($Query) { $searchArgs += @('--query', $Query) } else { $searchArgs += @('--search', $SearchName) }
        Run-Pass 'search' $searchArgs
    }
    Run-Pass 'watchlist' @('--watchlist', (Join-Path $Root 'watchlist.txt'),
                           '--limit', $Limit, '--days', $Days)
}

if ($Only -in 'all', 'opportunities') {
    # The roundup parser again, this time over a live search, so a programme you
    # never bookmarked still reaches the list. Same query shape as the search pass.
    & python (Join-Path $Root 'opportunities.py') --live --days $Days --min-likes $MinLikes *>> $Log
    if ($LASTEXITCODE -ne 0) {
        Say "live opportunities pass FAILED, code $LASTEXITCODE. See $Log"
    } else {
        Say 'wrote the live opportunities report'
    }
}

Get-ChildItem -Path $RunDir -Filter '*.md' | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip ($KeepRuns * 2) | Remove-Item -Force
Get-ChildItem -Path $RunDir -Filter '*.json' | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip ($KeepRuns * 2) | Remove-Item -Force

# -------- registering with Task Scheduler, run once --------
# pwsh -File install_tasks.ps1 registers both halves, on separate days, with the
# right -Only argument. Keep it clear of TwitterBookmarkWeeklyScan, which fires
# Sunday 10:00 to 16:00 and already reads .env; 8am on other days does that.
#
# Unregister-ScheduledTask -TaskName 'hiring-twitter-weekly' -Confirm:$false
# Unregister-ScheduledTask -TaskName 'opportunities-twitter-weekly' -Confirm:$false