# Weekly booking hunt: read the bookmark database and write two reports.
#
#   pwsh -File weekly.ps1                        both halves, last 8 days
#   pwsh -File weekly.ps1 -Only hiring           the openings report only
#   pwsh -File weekly.ps1 -Only opportunities    the grants and hackathons report only
#   pwsh -File weekly.ps1 -Days 14               hunt a wider window
#   pwsh -File weekly.ps1 -Sync                  also pull new bookmarks first (rarely needed)
#
# The two halves are scheduled separately, so one task runs -Only hiring and
# another runs -Only opportunities on a different day.
#
# Sync is opt-in because the machine already has a task called
# TwitterBookmarkWeeklyScan that syncs bookmarks every Sunday. Do not run both
# at once: ft cannot rename bookmarks.db over itself while this script holds it
# open, and that failure is what weekly_scan.py logs as EPERM.

param(
    [int]$Days = 8,
    [switch]$Sync,
    [int]$KeepRuns = 12,
    [ValidateSet('all', 'hiring', 'opportunities')]
    [string]$Only = 'all'
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

Say "bookmark report started, half=$Only, looking back $Days days, mode $(if ($Sync) { 'sync + search' } else { 'search only' })"

if ($Sync) {
    Say 'warning: TwitterBookmarkWeeklyScan may already be syncing, check for EPERM'
    & python (Join-Path $Root '..\sync_bookmarks.py') *>> $Log
    if ($LASTEXITCODE -ne 0) { Say "sync returned $LASTEXITCODE, searching anyway" }
}

if ($Only -in 'all', 'hiring') {
    $Md = Join-Path $RunDir "$Stamp.md"
    $Json = Join-Path $RunDir "$Stamp.json"

    & python (Join-Path $Root 'search.py') --search hiring-bookmarks --days $Days --md $Md --json $Json *>> $Log
    if ($LASTEXITCODE -ne 0) {
        Say "search failed, code $LASTEXITCODE. See $Log"
        exit $LASTEXITCODE
    }

    Say "wrote $Md"
    Say "wrote $Json"
}

if ($Only -in 'all', 'opportunities') {
    # Grants, hackathons and funds answer a different question from a role, so
    # they get their own report from the same bookmarks.
    & python (Join-Path $Root 'opportunities.py') --days $Days *>> $Log
    if ($LASTEXITCODE -ne 0) {
        Say "opportunities failed, code $LASTEXITCODE. See $Log"
    } else {
        Say 'wrote out\opportunities-<today>.md'
    }
    # The AI-researched sweep, rendered as a table. It needs research.py merge to
    # have run at least once; an empty file is not an error.
    & python (Join-Path $Root 'opportunities.py') --candidates *>> $Log
    if ($LASTEXITCODE -ne 0) {
        Say "candidates failed, code $LASTEXITCODE. See $Log"
    } else {
        Say 'wrote out\single-candidates.md'
    }
}

# Keep the last N runs so the folder does not grow forever.
Get-ChildItem -Path $RunDir -Filter '*.md' | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $KeepRuns | Remove-Item -Force
Get-ChildItem -Path $RunDir -Filter '*.json' | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $KeepRuns | Remove-Item -Force

# -------- registering with Task Scheduler, run once --------
# pwsh -File install_tasks.ps1 registers both halves, on separate days, with the
# right -Only argument. The laptop must be on and you logged in at 8am, and
# StartWhenAvailable runs a missed one as soon as the session comes up.
#
# Unregister-ScheduledTask -TaskName 'hiring-weekly' -Confirm:$false
# Unregister-ScheduledTask -TaskName 'opportunities-weekly' -Confirm:$false
