$logFile = 'D:\Desktop\FundLex\_cleanup.log'
function Log([string]$m) { Add-Content -Path $logFile -Value ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $m) -Encoding utf8 }
"=== CLEANUP $(Get-Date -Format 'HH:mm:ss') ===" | Set-Content -Path $logFile -Encoding utf8

# remove leftover Word owner/lock file via .NET (bypasses trash wrapper)
Get-ChildItem 'D:\Desktop\FundLex\funds' -Filter '~$*' -Force -ErrorAction SilentlyContinue | ForEach-Object {
    try { [System.IO.File]::Delete($_.FullName); Log ("deleted lock: " + $_.Name) } catch { Log ("fail: " + $_.Exception.Message) }
}
Log ("funds pdf count now: " + (Get-ChildItem 'D:\Desktop\FundLex\funds' -Filter *.pdf | Measure-Object).Count)

# remove my restore scratch
foreach ($f in @('_restore.ps1','_restore.log','_restore2.ps1','_restore2.log','_cleanup.ps1','_cleanup.log')) {
    $p = Join-Path 'D:\Desktop\FundLex' $f
    if ((Test-Path -LiteralPath $p) -and ($f -ne '_cleanup.ps1') -and ($f -ne '_cleanup.log')) {
        try { [System.IO.File]::Delete($p) } catch {}
    }
}
Log "remaining root _ files:"
Get-ChildItem 'D:\Desktop\FundLex' -Filter '_*' -File | ForEach-Object { Log ("   " + $_.Name) }
Log "DONE"
