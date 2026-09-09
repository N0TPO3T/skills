param([int]$X, [int]$Y, [string]$Out = "C:\Users\EDY\Code\HR\_cur.png")
# snap.ps1 <x y> [out] : move cursor to global (x,y), capture screen region around it, draw cursor icon onto image
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class SN {
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
[SN]::SetCursorPos($X, $Y) | Out-Null
Start-Sleep -Milliseconds 400
$procs = @(Get-Process -Name boss-zhipin -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Sort-Object Id)
$r = New-Object SN+RECT
[SN]::GetWindowRect($procs[0].MainWindowHandle, [ref]$r) | Out-Null
$ox = $r.Left; $oy = $r.Top
$w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($ox, $oy, 0, 0, $bmp.Size)
# draw cursor at window-relative position
$cx = $X - $ox
$cy = $Y - $oy
$icon = [System.Drawing.Icon]::FromHandle([System.Windows.Forms.Cursors]::Default.Handle)
$g.DrawIcon($icon, $cx, $cy)
$g.Dispose()
$icon.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output ("cursor at global ({0},{1}) -> window-relative ({2},{3}); saved {4}" -f $X, $Y, $cx, $cy, $Out)
