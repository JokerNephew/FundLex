param([int]$Limit = 0)

$ErrorActionPreference = 'Continue'
$srcDir = 'D:\Desktop\FundLex\funds'
$outDir = 'D:\Desktop\FundLex\funds_word'
$logFile = 'D:\Desktop\FundLex\_convert_log.txt'
$dlgLog = 'D:\Desktop\FundLex\_dialogs.log'

function Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $msg
    [System.IO.File]::AppendAllText($logFile, $line + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
}

# ---- dialog watchdog ----
Add-Type @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Diagnostics;
public class DK {
    [DllImport("user32.dll")] static extern bool EnumWindows(EP cb, IntPtr p);
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr h, EP cb, IntPtr p);
    delegate bool EP(IntPtr h, IntPtr p);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr SendMessageW(IntPtr h, uint msg, IntPtr w, IntPtr l);
    static object gate = new object();
    public static List<string> Seen = new List<string>();
    public static void LogLine(string s){ lock(gate){ Seen.Add(s); } }
    static bool IsWord(uint pid){ try { return Process.GetProcessById((int)pid).ProcessName.ToUpper()=="WINWORD"; } catch { return false; } }
    public static void Tick() {
        EnumWindows((h,p)=>{
            var cn=new StringBuilder(64); GetClassNameW(h,cn,64);
            if(cn.ToString()!="#32770") return true;
            if(!IsWindowVisible(h)) return true;
            uint pid; GetWindowThreadProcessId(h,out pid);
            if(!IsWord(pid)) return true;
            var tt=new StringBuilder(512); GetWindowTextW(h,tt,512);
            var texts=new List<string>(); IntPtr btn=IntPtr.Zero;
            EnumChildWindows(h,(c,p2)=>{
                var cn2=new StringBuilder(64); GetClassNameW(c,cn2,64);
                var tt2=new StringBuilder(1024); GetWindowTextW(c,tt2,1024);
                if(tt2.Length>0) texts.Add(cn2.ToString()+":"+tt2.ToString());
                if(btn==IntPtr.Zero && cn2.ToString()=="Button") btn=c;
                return true;
            }, IntPtr.Zero);
            LogLine("DIALOG ["+tt.ToString()+"] {"+string.Join(" | ",texts.ToArray())+"}");
            if(btn!=IntPtr.Zero) SendMessageW(btn,0x00F5,IntPtr.Zero,IntPtr.Zero);
            return true;
        }, IntPtr.Zero);
    }
    static void Run(int it,int ms){ for(int i=0;i<it;i++){ try{Tick();}catch{} System.Threading.Thread.Sleep(ms); } }
    public static void Start(int it,int ms){ var t=new System.Threading.Thread(()=>Run(it,ms)); t.IsBackground=true; t.Start(); }
}
"@

if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }

$pdfs = Get-ChildItem -Path $srcDir -Filter *.pdf | Sort-Object Name
if ($Limit -gt 0) { $pdfs = $pdfs | Select-Object -First $Limit }
$total = @($pdfs).Count

Log ("=== BATCH START total=$total limit=$Limit ===")

[DK]::Start(4000, 300)   # ~20 min watch

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try { $word.Options.ConfirmConversions = $false } catch {}
try { $word.Options.SaveInterval = 0 } catch {}
try { $word.AutomationSecurity = 3 } catch {}

$ok = 0; $skip = 0; $fail = 0
$i = 0
foreach ($pdf in $pdfs) {
    $i++
    $target = Join-Path $outDir ($pdf.BaseName + '.docx')
    if (Test-Path $target) { $skip++; continue }
    $t = Get-Date
    $doc = $null
    try {
        $doc = $word.Documents.Open($pdf.FullName, $false, $false, $false)
        $doc.SaveAs2($target, 16)
        $sec = [math]::Round(((Get-Date) - $t).TotalSeconds, 1)
        $sizeKB = [math]::Round((Get-Item $target).Length / 1KB, 0)
        $doc.Close(0)
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc) | Out-Null
        $ok++
        Log ("[$i/$total] OK ${sec}s ${sizeKB}KB  $($pdf.BaseName)")
    } catch {
        $fail++
        Log ("[$i/$total] FAIL $($pdf.Name) :: $($_.Exception.Message)")
        try { if ($doc) { $doc.Close(0) } } catch {}
        try { $word.Documents.Close(0) } catch {}
    }
}

try { $word.Quit() } catch {}
try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null } catch {}

if ([DK]::Seen.Count -gt 0) {
    "=== DIALOGS $(Get-Date -Format 'HH:mm:ss') ===" | Set-Content -Path $dlgLog -Encoding utf8
    [DK]::Seen | Add-Content -Path $dlgLog -Encoding utf8
}

Log ("=== BATCH DONE ok=$ok skip=$skip fail=$fail ===")
