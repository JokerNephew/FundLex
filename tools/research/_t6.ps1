$logFile = 'D:\Desktop\FundLex\_t6.log'
function Log([string]$m) {
    [System.IO.File]::AppendAllText($logFile, ("[{0}] {1}`r`n" -f (Get-Date -Format 'HH:mm:ss.fff'), $m), [System.Text.UTF8Encoding]::new($false))
}
"=== TEST6 (Excel vs Word save) $(Get-Date -Format 'HH:mm:ss') ===" | Set-Content -Path $logFile -Encoding utf8

Log "--- security processes re-check ---"
foreach ($n in @('HipsDaemon','HipsTray','MSPCManagerService','QQPCExternal','wsctrlsvc','usysdiag','wsctrl','360tray','ZhuDongFangYu')) {
    $ps = @(Get-Process -Name $n -ErrorAction SilentlyContinue)
    if ($ps.Count -gt 0) {
        foreach ($p in $ps) { $path=''; try { $path = $p.Path } catch {}; Log ("   FOUND $n pid=$($p.Id) path=[$path]") }
    }
}
Log "   (end security check)"

$tmp = $env:TEMP

# ---- Excel probe ----
$t = Get-Date
try {
    $xl = New-Object -ComObject Excel.Application
    $xl.Visible = $false
    $xl.DisplayAlerts = $false
    $wb = $xl.Workbooks.Add()
    $xlPath = Join-Path $tmp '_probe_excel.xlsx'
    if (Test-Path $xlPath) { Remove-Item $xlPath -Force }
    Log "EXCEL save START"
    $wb.SaveAs($xlPath)
    Log ("EXCEL save OK in " + [math]::Round(((Get-Date)-$t).TotalSeconds,1) + "s exists=" + (Test-Path $xlPath))
    $wb.Close($false)
    $xl.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($xl) | Out-Null
} catch { Log ("EXCEL FAIL: " + $_.Exception.Message) }

# ---- Word probe ----
$t = Get-Date
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $d = $word.Documents.Add()
    $wPath = Join-Path $tmp '_probe_word.docx'
    if (Test-Path $wPath) { Remove-Item $wPath -Force }
    Log "WORD save START"
    $d.SaveAs2($wPath, 16)
    Log ("WORD save OK in " + [math]::Round(((Get-Date)-$t).TotalSeconds,1) + "s exists=" + (Test-Path $wPath))
    $d.Close(0)
    $word.Quit()
} catch { Log ("WORD FAIL: " + $_.Exception.Message) }

Log "ALL DONE"
