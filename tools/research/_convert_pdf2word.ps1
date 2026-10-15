$ErrorActionPreference = 'Stop'

$srcDir = 'D:\Desktop\FundLex\funds'
$outDir = 'D:\Desktop\FundLex\funds_word'
$logFile = 'D:\Desktop\FundLex\_convert_log.txt'

if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }

function Write-Log($msg) { Add-Content -Path $logFile -Value $msg -Encoding utf8 }

$pdfs = Get-ChildItem -Path $srcDir -Filter *.pdf | Sort-Object Name
$total = $pdfs.Count
$done = 0
$failed = @()

Write-Log ("START total=" + $total + " time=" + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try { $word.Options.ConfirmConversions = $false } catch {}
try { $word.AutomationSecurity = 3 } catch {}

foreach ($pdf in $pdfs) {
    $done++
    $docName = [System.IO.Path]::GetFileNameWithoutExtension($pdf.Name)
    $docxPath = Join-Path $outDir ($docName + '.docx')
    if (Test-Path $docxPath) { continue }
    try {
        $doc = $word.Documents.Open($pdf.FullName, $false, $true, $false)
        $doc.SaveAs2($docxPath, 16)
        $doc.Close(0)
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc) | Out-Null
        if ($done % 20 -eq 0) { Write-Log ("[{0}/{1}] OK {2}" -f $done, $total, (Get-Date).ToString('HH:mm:ss')) }
    } catch {
        $failed += $pdf.Name
        Write-Log ("[{0}/{1}] FAIL: {2} :: {3}" -f $done, $total, $pdf.Name, $_.Exception.Message)
        try { $word.ActiveDocument.Close(0) } catch {}
    }
}

$word.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null

Write-Log ("DONE Total=" + $total + " Failed=" + $failed.Count + " time=" + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))
if ($failed.Count -gt 0) {
    Write-Log "--- FAILED LIST ---"
    foreach ($f in $failed) { Write-Log $f }
}
