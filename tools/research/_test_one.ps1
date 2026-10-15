$ErrorActionPreference = 'Stop'
$pdf = Get-ChildItem -Path 'D:\Desktop\FundLex\funds' -Filter *.pdf | Sort-Object Name | Select-Object -First 1
$docxPath = 'D:\Desktop\FundLex\funds_word\_test.docx'
$log = @()

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$log += "STEP1: word created"
try { $word.Options.ConfirmConversions = $false; $log += "STEP2: ConfirmConversions set" } catch { $log += "STEP2 ERR: " + $_.Exception.Message }
try { $word.AutomationSecurity = 3; $log += "STEP3: AutomationSecurity set" } catch { $log += "STEP3 ERR: " + $_.Exception.Message }

try {
    $log += "STEP4: opening " + $pdf.Name
    $doc = $word.Documents.Open($pdf.FullName, $false, $true, $false)
    $log += "STEP5: opened, pages=" + $doc.ComputeStatistics(2)
    $doc.SaveAs2($docxPath, 16)
    $log += "STEP6: saved"
    $doc.Close(0)
    $log += "STEP7: closed"
} catch {
    $log += ("OPEN_ERR: " + $_.Exception.Message)
}
$log -join "`n" | Out-File 'D:\Desktop\FundLex\_probe.txt' -Encoding utf8
$word.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
