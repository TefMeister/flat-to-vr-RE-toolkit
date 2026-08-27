<#
.SYNOPSIS
  Capture a window belonging to a running process to a PNG — including most
  Direct3D windows, and without needing the window to be foreground.

.DESCRIPTION
  Uses PrintWindow with PW_RENDERFULLCONTENT (0x2), which captures many D3D
  windows that a plain screen copy renders as black, and works while the window
  is behind others. Falls back to a screen-region copy if PrintWindow fails.

.WHY THIS EXISTS
  Verifying what state a game is actually in — gameplay, a menu, a cutscene — is
  the single highest-value check when driving a game, and the cheapest way to get
  it wrong is to infer state from a derived number instead of looking.

  Real cost of not doing this: three consecutive camera experiments were run
  against a game with its pause menu open. Each captured a screenshot that was
  never opened; only a brightness metric was checked, and it happened to look
  plausible. The conclusion drawn — "this game's camera does not respond to the
  mouse" — was false and went into permanent notes before being caught.

  Capture the image. Then actually look at it.

.EXAMPLES
  .\capture-window.ps1 -Process Psychonauts -Out shot.png
  .\capture-window.ps1 -Process XIII -Out .\captures\before.png
#>
param(
    [Parameter(Mandatory=$true)][string]$Process,
    [string]$Out = "capture.png"
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinCap {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
}
"@

$proc = Get-Process $Process -ErrorAction SilentlyContinue
if (-not $proc) { throw "Process '$Process' is not running." }

$hwnd = $proc.MainWindowHandle
if ($hwnd -eq [IntPtr]::Zero) { throw "Process '$Process' has no main window." }

$rect = New-Object WinCap+RECT
[void][WinCap]::GetWindowRect($hwnd, [ref]$rect)
$w = $rect.Right - $rect.Left
$h = $rect.Bottom - $rect.Top
if ($w -le 0 -or $h -le 0) { throw "Window rect is empty ($w x $h) - is the window minimised?" }

$bmp = New-Object System.Drawing.Bitmap $w, $h
$gfx = [System.Drawing.Graphics]::FromImage($bmp)
try {
    $hdc = $gfx.GetHdc()
    # PW_RENDERFULLCONTENT = 0x2 - the flag that makes this work for D3D windows.
    $ok = [WinCap]::PrintWindow($hwnd, $hdc, 2)
    $gfx.ReleaseHdc($hdc)
    if (-not $ok) {
        # Fallback: copy the screen region. Needs the window actually visible.
        $gfx.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bmp.Size)
    }
    $dir = Split-Path $Out -Parent
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
    "saved {0} ({1}x{2}, PrintWindow={3})" -f $Out, $w, $h, $ok
}
finally {
    $gfx.Dispose(); $bmp.Dispose()
}
