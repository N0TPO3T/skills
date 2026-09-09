Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WR {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
$procs = @(Get-Process -Name boss-zhipin -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Sort-Object Id)
if ($procs.Count -eq 0) { Write-Error "boss window not found"; exit 1 }
$p = $procs[0]
$r = New-Object WR+RECT
[WR]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
$x = $r.Left; $y = $r.Top; $w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$state = @{ x = $x; y = $y; w = $w; h = $h }
$state | ConvertTo-Json | Set-Content -Path (Join-Path $dir "state.json") -Encoding UTF8
Write-Output ("{0},{1},{2},{3}" -f $x, $y, $w, $h)
