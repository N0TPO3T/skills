param([int]$X, [int]$Y, [int]$Times = 1, [switch]$Up)
# scroll.ps1 <wx wy> [times] [-Up] : wheel-scroll over window-relative point; default scrolls DOWN
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class SC {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, int dwData, UIntPtr dwExtraInfo);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    public const uint WHEEL = 0x0800;
    public const int WHEEL_DELTA = 120;
}
"@
$procs = @(Get-Process -Name boss-zhipin -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Sort-Object Id)
if ($procs.Count -eq 0) { Write-Error "boss window not found"; exit 1 }
$p = $procs[0]
$r = New-Object SC+RECT
[SC]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
[SC]::SetCursorPos($r.Left + $X, $r.Top + $Y) | Out-Null
Start-Sleep -Milliseconds 60
$delta = $Times * [SC]::WHEEL_DELTA
if (-not $Up) { $delta = -$delta }
[SC]::mouse_event([SC]::WHEEL, 0, 0, $delta, [UIntPtr]::Zero)
Write-Output ("wheel {0} ticks at ({1},{2}) dir={3}" -f $Times, $X, $Y, $(if ($Up) { "up" } else { "down" }))
