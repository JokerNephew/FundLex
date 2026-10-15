$ErrorActionPreference = 'Stop'
$srcDir = 'D:\Desktop\FundLex\funds'
$outDir = 'D:\Desktop\FundLex\funds_word'
$log = @()

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try { $word.Options.ConfirmConversions = $false } catch {}
try { $word.AutomationSecurity = 3 } catch {}

$pdfs = Get-ChildItem -Path $srcDir -Filter *.pdf | Sort-Object Name | Select-Object -First 3
foreach ($pdf in $pdfs) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $docxPath = Join-Path $outDir ([System.IO.Path]::GetFileNameWithoutExtension($pdf.Name) + '.docx')
    try {
        $doc = $word.Documents.Open($pdf.FullName, $false, $true, $false)
        $pages = $doc.ComputeStatistics(2)
        $doc.SaveAs2($docxPath, 16)
        $doc.Close(0)
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc) | Out-Null
        $sw.Stop()
        $log += ("OK  {0}  pages={1}  {2}s" -f $pdf.Name, $pages, [math]::Round($sw.Elapsed.TotalSeconds,1))
    } catch {
        $sw.Stop()
        $log += ("FAIL {0}  {1}s  {2}" -f $pdf.Name, [math]::Round($sw.Elapsed.TotalSeconds,1), $_.Exception.Message)
    }
}
$word.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
$log -join "`n" | Out-File 'D:\Desktop\FundLex\_probe.txt' -Encoding utf8
