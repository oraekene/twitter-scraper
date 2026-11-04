# Keep the 3-year account crawl alive: restart after a crash, stop when done.
# X allows 50 UserTweets calls per 15 minutes, so --delay 19 paces under it.
Set-Location $PSScriptRoot
$log = "$PSScriptRoot\out\history-ascully789.log"

# Two runners would double the request rate and fight over the state file.
if (Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'crawl_history\.py' }) { exit }

$py = "$env:APPDATA\uv\tools\twitter-cli\Scripts\python.exe"
while ($true) {
    & $py crawl_history.py ascully789 --since 2023-10-28 --delay 19 2>&1 |
        Out-File -FilePath $log -Append -Encoding utf8
    if (Test-Path out\history-ascully789.state.json) {
        $s = Get-Content out\history-ascully789.state.json -Raw | ConvertFrom-Json
        if ($s.done) { break }
    }
    Start-Sleep 60
}
