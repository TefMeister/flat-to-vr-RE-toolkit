# Relative mouse motion via SendInput, for driving mouse-look in a game.
#
# !! READ THIS BEFORE REACHING FOR IT !!
# This tool FAILS against any game holding the mouse in DirectInput EXCLUSIVE mode,
# and a lot of DirectInput-era games do. Measured on XIII (2003): 600 px of injected
# motion produced 0.0 degrees of view change, in a session where injected KEYS worked
# perfectly. Psychonauts (2005) hit the identical wall. The device simply is not
# reading the Windows input queue.
#
# So: try it, but spend ONE measurement deciding, and if the view does not move, stop.
# Do not escalate to bigger deltas, more steps, or cursor warping - none of that
# changes an exclusive-mode grab. Look instead for a KEY bound to the same action
# (tools/unreal-nav.ps1 explains the Unreal-family alias route, where the binding is
# often merely absent rather than the capability missing).
#
# It is kept because a fast NEGATIVE is worth having: one run tells you which input
# route this game supports, which decides the whole automation approach.
#
# Sent as many small steps rather than one big jump: games commonly clamp or
# smooth per-frame mouse delta, so a single large delta can under-rotate or be
# discarded entirely, which reads as "mouse injection does not work" when the
# real cause is the step size.
param(
    [Parameter(Mandatory=$true)][int]$Dx,
    [int]$Dy = 0,
    [int]$Steps = 20,
    [int]$StepDelayMs = 12,
    [string]$ProcessName = "XIII"   # override per game
)
$ErrorActionPreference = 'Stop'

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class MouseInj {
    [StructLayout(LayoutKind.Sequential)]
    public struct MOUSEINPUT { public int dx, dy; public uint mouseData, dwFlags, time; public IntPtr extra; }
    [StructLayout(LayoutKind.Sequential)]
    public struct INPUT { public uint type; public MOUSEINPUT mi; public int pad1, pad2; }
    [DllImport("user32.dll", SetLastError=true)]
    public static extern uint SendInput(uint n, INPUT[] p, int cb);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
    public const uint MOUSEEVENTF_MOVE = 0x0001;
    public static void Move(int dx, int dy) {
        INPUT[] inp = new INPUT[1];
        inp[0].type = 0;
        inp[0].mi.dx = dx; inp[0].mi.dy = dy;
        inp[0].mi.dwFlags = MOUSEEVENTF_MOVE;
        SendInput(1, inp, Marshal.SizeOf(typeof(INPUT)));
    }
}
"@

# Focus the game, or the motion lands in whatever window is focused instead.
$p = Get-Process -Name $ProcessName -ErrorAction Stop
$h = $p.MainWindowHandle
if ($h -eq [IntPtr]::Zero) { throw "$ProcessName has no main window" }
for ($i = 0; $i -lt 5; $i++) {
    if ([MouseInj]::GetForegroundWindow() -eq $h) { break }
    [MouseInj]::ShowWindow($h, 9) | Out-Null
    [MouseInj]::SetForegroundWindow($h) | Out-Null
    Start-Sleep -Milliseconds 120
}
if ([MouseInj]::GetForegroundWindow() -ne $h) { throw "could not focus $ProcessName - aborting" }
Start-Sleep -Milliseconds 150

$sx = [int][math]::Round($Dx / $Steps)
$sy = [int][math]::Round($Dy / $Steps)
for ($i = 0; $i -lt $Steps; $i++) {
    [MouseInj]::Move($sx, $sy)
    Start-Sleep -Milliseconds $StepDelayMs
}
"mouse dx=$Dx dy=$Dy in $Steps steps of ($sx,$sy) -> $ProcessName"
