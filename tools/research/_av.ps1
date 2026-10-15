$logFile = 'D:\Desktop\FundLex\_av.log'
function Log([string]$m) { Add-Content -Path $logFile -Value $m -Encoding utf8 }
"=== AV $(Get-Date -Format 'HH:mm:ss') ===" | Set-Content -Path $logFile -Encoding utf8

Log "--- registered AV products (SecurityCenter2) ---"
try {
    Get-CimInstance -Namespace 'root\SecurityCenter2' -ClassName AntiVirusProduct -ErrorAction Stop | ForEach-Object {
        Log ("   name=" + $_.displayName + " | state=" + $_.productState + " | path=" + $_.pathToSignedProductExe)
    }
} catch { Log ("   err: " + $_.Exception.Message) }

Log "--- suspicious process paths ---"
$names = @('HipsDaemon','HipsTray','MSPCManagerService','QQPCExternal','wsctrlsvc','PDFREFLOW','tcls_core','pallas','betterleaks','DAX3API','DesktopMgr64','DesktopService64','DesktopAITaskCenter','MSOfficePLUSService','FoxitProxyServer_PH','FoxitPDFEditor')
foreach ($n in $names) {
    $p = Get-Process -Name $n -ErrorAction SilentlyContinue
    foreach ($x in $p) {
        $path = ''
        try { $path = $x.Path } catch {}
        Log ("   $n pid=$($x.Id) path=[$path] desc=[" + (try { $x.Description } catch { '' }) + "]")
    }
}

Log "--- Office 相关进程 ---"
Get-Process | Where-Object { $_.ProcessName -match 'WINWORD|EXCEL|POWERPNT|OfficeClickToRun|PDFREFLOW' } | ForEach-Object {
    $path = ''; try { $path = $_.Path } catch {}
    Log ("   " + $_.ProcessName + " pid=" + $_.Id + " path=[" + $path + "]")
}

Log "DONE"
