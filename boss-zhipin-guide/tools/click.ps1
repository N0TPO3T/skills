param(
    [int]$X, [int]$Y,
    [switch]$Right, [switch]$Double, [switch]$NoFront
)
# click.ps1 <wx wy> : left click at window-relative coords (optionally right/double)
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class CK {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    public const uint LEFTDOWN = 0x02, LEFTUP = 0x04, RIGHTDOWN = 0x08, RIGHTUP = 0x10;
    public const int SW_RESTORE = 9;
}
"@
$procs = @(Get-Process -Name boss-zhipin -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Sort-Object Id)
if ($procs.Count -eq 0) { Write-Error "boss window not found"; exit 1 }
$p = $procs[0]
$hwnd = $p.MainWindowHandle
$r = New-Object CK+RECT
[CK]::GetWindowRect($hwnd, [ref]$r) | Out-Null
if (-not $NoFront) {
    if ([CK]::IsIconic($hwnd)) { [CK]::ShowWindow($hwnd, [CK]::SW_RESTORE) | Out-Null }
    [CK]::SetForegroundWindow($hwnd) | Out-Null
    Start-Sleep -Milliseconds 150
}
$gx = $r.Left + $X
$gy = $r.Top + $Y
[CK]::SetCursorPos($gx, $gy) | Out-Null
Start-Sleep -Milliseconds 80
if ($Double) {
    [CK]::mouse_event([CK]::LEFTDOWN, 0, 0, 0, [UIntPtr]::Zero)
    [CK]::mouse_event([CK]::LEFTUP, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 60
}
if ($Right) {
    [CK]::mouse_event([CK]::RIGHTDOWN, 0, 0, 0, [UIntPtr]::Zero)
    [CK]::mouse_event([CK]::RIGHTUP, 0, 0, 0, [UIntPtr]::Zero)
} else {
    [CK]::mouse_event([CK]::LEFTDOWN, 0, 0, 0, [UIntPtr]::Zero)
    [CK]::mouse_event([CK]::LEFTUP, 0, 0, 0, [UIntPtr]::Zero)
}
Write-Output ("clicked at global ({0},{1})" -f $gx, $gy)
