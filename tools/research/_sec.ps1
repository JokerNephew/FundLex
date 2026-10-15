$logFile = 'D:\Desktop\FundLex\_sec.log'
function Log([string]$m) { Add-Content -Path $logFile -Value $m -Encoding utf8 }
"=== SECURITY $(Get-Date -Format 'HH:mm:ss') ===" | Set-Content -Path $logFile -Encoding utf8

# Defender controlled folder access
try {
    $mp = Get-MpPreference -ErrorAction Stop
    Log ("Defender RealTimeProtection enabled = " + (-not (Get-MpComputerStatus).RealTimeProtectionEnabled -eq $false))
    Log ("ControlledFolderAccess = " + $mp.EnableControlledFolderAccess)
    Log ("CFA ProtectedFolders = " + ($mp.ControlledFolderAccessProtectedFolders -join '; '))
    Log ("CFA AllowedApps = " + ($mp.ControlledFolderAccessAllowedApplications -join '; '))
    Log ("ExclusionPath = " + ($mp.ExclusionPath -join '; '))
} catch { Log ("Defender query err: " + $_.Exception.Message) }

try {
    $st = Get-MpComputerStatus -ErrorAction Stop
    Log ("AMRunningMode = " + $st.AMRunningMode)
    Log ("RealTimeProtectionEnabled = " + $st.RealTimeProtectionEnabled)
    Log ("AntivirusEnabled = " + $st.AntivirusEnabled)
    Log ("BehaviorMonitorEnabled = " + $st.BehaviorMonitorEnabled)
} catch { Log ("MpComputerStatus err: " + $_.Exception.Message) }

# known security / shell-hook software processes
Log "--- security-ish processes ---"
$pat = 'huorong|hips|360|qqpcmgr|tencent|kingsoft|avp|kav|nod32|mcafee|symantec|sophos|eset|avast|avg|bitdefender|trend|pcmanager|deepscan|usysdiag|wsctrl|zhuandong|360tray|360safe|safe|guard|thunder|xunlei|evernote|zotero|foxit|wind|wft'
Get-Process | Where-Object { $_.ProcessName -match $pat } | Select-Object -Unique ProcessName | ForEach-Object { Log ("   " + $_.ProcessName) }

Log "--- all processes (top by name) ---"
(Get-Process | Select-Object -ExpandProperty ProcessName | Sort-Object -Unique) -join ', ' | ForEach-Object { Log ("   " + $_) }

Log "DONE"
