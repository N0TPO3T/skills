param(
    [string]$Out,
    [int]$X = -1, [int]$Y = -1, [int]$W = -1, [int]$H = -1
)
# Usage: shot.ps1 <out.png> [wx wy ww wh]   (coords relative to boss window; default = whole window)
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class SH {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
$procs = @(Get-Process -Name boss-zhipin -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Sort-Object Id)
if ($procs.Count -eq 0) { Write-Error "boss window not found"; exit 1 }
$p = $procs[0]
$r = New-Object SH+RECT
[SH]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
$ox = $r.Left; $oy = $r.Top
$ow = $r.Right - $r.Left; $oh = $r.Bottom - $r.Top
if ($W -lt 0) { $W = $ow }
if ($H -lt 0) { $H = $oh }
if ($X -lt 0) { $X = 0 }
if ($Y -lt 0) { $Y = 0 }
if ($X + $W -gt $ow) { $W = $ow - $X }
if ($Y + $H -gt $oh) { $H = $oh - $Y }
$bmp = New-Object System.Drawing.Bitmap($W, $H)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($ox + $X, $oy + $Y, 0, 0, $bmp.Size)
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output ("saved {0} {1}x{2} (window origin {3},{4})" -f $Out, $W, $H, $ox, $oy)
