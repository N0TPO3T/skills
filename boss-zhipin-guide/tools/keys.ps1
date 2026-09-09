param([Parameter(Mandatory=$true)][string]$Action)
# keys.ps1 type:<text> | esc | enter | tab | pgdn | pgup | end | ctrlw
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class KY {
    [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    public const uint KEYUP = 0x02;
    public const byte VK_ESCAPE = 0x1B, VK_RETURN = 0x0D, VK_TAB = 0x09, VK_CONTROL = 0x11;
    public const byte VK_NEXT = 0x22, VK_PRIOR = 0x21, VK_END = 0x23, VK_V = 0x56;
}
"@
$procs = @(Get-Process -Name boss-zhipin -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Sort-Object Id)
if ($procs.Count -eq 0) { Write-Error "boss window not found"; exit 1 }
[KY]::SetForegroundWindow($procs[0].MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 120
function SendKey([byte]$vk) {
    [KY]::keybd_event($vk, 0, 0, [UIntPtr]::Zero)
    [KY]::keybd_event($vk, 0, [KY]::KEYUP, [UIntPtr]::Zero)
}
function SendCtrlV() {
    [KY]::keybd_event([KY]::VK_CONTROL, 0, 0, [UIntPtr]::Zero)
    SendKey([KY]::VK_V)
    [KY]::keybd_event([KY]::VK_CONTROL, 0, [KY]::KEYUP, [UIntPtr]::Zero)
}
if ($Action.StartsWith("type:")) {
    $text = $Action.Substring(5)
    Set-Clipboard -Value $text
    Start-Sleep -Milliseconds 200
    SendCtrlV
} elseif ($Action -eq "esc") {
    SendKey([KY]::VK_ESCAPE)
} elseif ($Action -eq "enter") {
    SendKey([KY]::VK_RETURN)
} elseif ($Action -eq "tab") {
    SendKey([KY]::VK_TAB)
} elseif ($Action -eq "pgdn") {
    SendKey([KY]::VK_NEXT)
} elseif ($Action -eq "pgup") {
    SendKey([KY]::VK_PRIOR)
} elseif ($Action -eq "end") {
    SendKey([KY]::VK_END)
} elseif ($Action -eq "ctrlw") {
    [KY]::keybd_event([KY]::VK_CONTROL, 0, 0, [UIntPtr]::Zero)
    SendKey(0x57)
    [KY]::keybd_event([KY]::VK_CONTROL, 0, [KY]::KEYUP, [UIntPtr]::Zero)
} else {
    Write-Error "unknown action"
    exit 1
}
Write-Output ("key action: {0}" -f $Action)
