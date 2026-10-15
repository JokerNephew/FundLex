$logFile = 'D:\Desktop\FundLex\_wtmpl.log'
function Log([string]$m) { Add-Content -Path $logFile -Value $m -Encoding utf8 }
"=== TEMPLATES $(Get-Date -Format 'HH:mm:ss') ===" | Set-Content -Path $logFile -Encoding utf8

Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object { try { $_.Kill() } catch {} }
Start-Sleep -Seconds 2

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0

Log ("Templates.Count = " + $word.Templates.Count)
foreach ($t in $word.Templates) {
    try { Log ("  name=[" + $t.Name + "] path=[" + $t.FullName + "]") } catch { Log ("  err " + $_.Exception.Message) }
}
try { Log ("StartupPath = " + $word.StartupPath) } catch {}
try { Log ("Options.DefaultFilePath(Startup) = " + $word.Options.DefaultFilePath(2)) } catch {}
try { Log ("Options.DefaultFilePath(UserTemplates) = " + $word.Options.DefaultFilePath(1)) } catch {}

$word.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null

Log "--- STARTUP folders on disk ---"
$folders = @(
  (Join-Path $env:APPDATA 'Microsoft\Word\STARTUP'),
  'C:\Program Files\Microsoft Office\root\Office16\STARTUP',
  'C:\Program Files (x86)\Microsoft Office\root\Office16\STARTUP'
)
foreach ($f in $folders) {
    if (Test-Path $f) {
        Log ("FOLDER: $f")
        Get-ChildItem $f -Force -ErrorAction SilentlyContinue | ForEach-Object { Log ("   " + $_.Name + "  " + $_.Length + "B  " + $_.LastWriteTime) }
    } else { Log ("MISSING: $f") }
}

Log "--- Templates folder full listing ---"
Get-ChildItem (Join-Path $env:APPDATA 'Microsoft\Templates') -Force -ErrorAction SilentlyContinue | ForEach-Object { Log ("   " + $_.Name + "  " + $_.Length + "B  " + $_.LastWriteTime) }

Log "DONE"
