$logFile = 'D:\Desktop\FundLex\_wdiag.log'
function Log([string]$m) { Add-Content -Path $logFile -Value $m -Encoding utf8 }
"=== WORD DIAG $(Get-Date -Format 'HH:mm:ss') ===" | Set-Content -Path $logFile -Encoding utf8

Log "--- AutoRecover / Save paths ---"
$opt = 'HKCU:\Software\Microsoft\Office\16.0\Word\Options'
foreach ($n in @('AUTOSAVE-PATH','DefaultFormat','ConfirmFileConversion')) {
    $v = (Get-ItemProperty $opt -Name $n -ErrorAction SilentlyContinue).$n
    Log ("  $n = [$v]")
}
$asp = (Get-ItemProperty $opt -Name 'AUTOSAVE-PATH' -ErrorAction SilentlyContinue).'AUTOSAVE-PATH'
if ($asp) { Log ("  AUTOSAVE dir exists = " + (Test-Path $asp)) }
Log ("  D:\Office exists = " + (Test-Path 'D:\Office'))
if (Test-Path 'D:\Office') {
    Get-ChildItem 'D:\Office' -Force -ErrorAction SilentlyContinue | ForEach-Object { Log ("     " + $_.Name) }
}

Log "--- Normal.dotm ---"
$tmpl = Join-Path $env:APPDATA 'Microsoft\Templates'
if (Test-Path $tmpl) {
    Get-ChildItem $tmpl -Force -ErrorAction SilentlyContinue | ForEach-Object {
        Log ("  " + $_.Name + "  " + $_.Length + "B  " + $_.LastWriteTime)
    }
} else { Log "  templates dir missing" }

Log "--- Word Data key ---"
$data = 'HKCU:\Software\Microsoft\Office\16.0\Word\Data'
if (Test-Path $data) {
    $p = Get-ItemProperty $data
    $names = ($p.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' } | Measure-Object).Count
    Log ("  Data values = " + $names)
} else { Log "  Data key missing" }

Log "--- Resiliency ---"
if (Test-Path 'HKCU:\Software\Microsoft\Office\16.0\Word\Resiliency') {
    Get-ChildItem 'HKCU:\Software\Microsoft\Office\16.0\Word\Resiliency' -Recurse -ErrorAction SilentlyContinue | ForEach-Object { Log ("  " + $_.Name) }
} else { Log "  none" }

Log "--- recent Application event log (Word/Office) ---"
try {
    Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=(Get-Date).AddHours(-2)} -ErrorAction Stop |
      Where-Object { $_.ProviderName -match 'Word|Office|Application Error|Application Hang' } |
      Select-Object -First 25 | ForEach-Object {
        Log ("  [" + $_.TimeCreated.ToString('HH:mm:ss') + "] " + $_.ProviderName + " id=" + $_.Id + " :: " + ($_.Message -replace "`r`n"," " ).Substring(0, [Math]::Min(300, $_.Message.Length)))
      }
} catch { Log ("  event log err: " + $_.Exception.Message) }

Log "DONE"
