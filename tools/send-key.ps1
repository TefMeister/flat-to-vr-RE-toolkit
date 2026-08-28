# Synthetic keyboard input into a running game, via SendInput scancode events.
# WHY THIS WORKS WHERE MOUSE INJECTION OFTEN DOES NOT
#   Many DirectInput-era games poll the REAL OS keyboard stack, so plain SendInput with
#   SCANCODE events reaches them. The MOUSE is frequently a different story: a game holding the
#   mouse device in DirectInput EXCLUSIVE mode ignores injected motion entirely (measured on
#   XIII 2003: 600px injected -> 0.0 degrees of view change, while keys worked in the same
#   session). If you need view control and the mouse is dead, look for a KEY BINDING for the
#   same action before building anything cleverer - see tools/unreal-nav.ps1.
#
# Requirements: (1) the game window genuinely foreground, (2) nobody touching the physical
# keyboard/mouse during the send.
#
# Proven on: Psychonauts (2005), XIII (2003).
#
# Usage: powershell -File send_key.ps1 -Scan 0x39            # SPACE
#        powershell -File send_key.ps1 -Scan 0xCD -Extended  # RIGHT arrow
#        powershell -File send_key.ps1 -Scan 0x1C            # ENTER
# Common DIK scan codes: SPACE=0x39 ENTER=0x1C ESC=0x01 UP=0xC8 DOWN=0xD0 LEFT=0xCB RIGHT=0xCD
# (arrows are EXTENDED keys - pass -Extended or DirectInput sees the numpad variants)
param(
    [Parameter(Mandatory=$true)] [int]$Scan,
    [switch]$Extended,
    [int]$HoldMs = 120,
    [string]$ProcessName = "Psychonauts"  # override per game
)

Add-Type @'
using System;
using System.Runtime.InteropServices;
public class PsySendKey {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool AllowSetForegroundWindow(int dwProcessId);
    [StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public KEYBDINPUT ki; public ulong pad; }
    [StructLayout(LayoutKind.Sequential)] public struct KEYBDINPUT { public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
    [DllImport("user32.dll", SetLastError=true)] public static extern uint SendInput(uint n, INPUT[] inputs, int size);
    public static uint Key(ushort scan, uint extended, bool up) {
        INPUT[] inp = new INPUT[1];
        inp[0].type = 1; // INPUT_KEYBOARD
        inp[0].ki.wScan = scan;
        inp[0].ki.dwFlags = (uint)(8 | extended | (up ? 2u : 0u)); // SCANCODE | EXTENDEDKEY? | KEYUP?
        return SendInput(1, inp, Marshal.SizeOf(typeof(INPUT)));
    }
}
'@

$p = Get-Process -Name $ProcessName -ErrorAction Stop

# notes/53: the foreground-lock grant is consumed by the NEXT SetForegroundWindow call, not durable
# across multiple future sends - and the current environment has ANOTHER process (the tool-execution
# harness's own console) actively contending for foreground, so a single attempt is unreliable even
# with the grant. Retry a few times: re-grant + re-attempt + re-check, rather than failing on the
# first miss (this is real intermittent contention, not a hard denial - three earlier one-shot fixes
# this session each addressed a different wrong layer of the problem).
$ok = $false
for ($i = 0; $i -lt 5; $i++) {
    if ([PsySendKey]::GetForegroundWindow() -eq $p.MainWindowHandle) { $ok = $true; break }
    [PsySendKey]::AllowSetForegroundWindow($p.Id) | Out-Null
    [PsySendKey]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
    Start-Sleep -Milliseconds 300
}
if (-not $ok -and [PsySendKey]::GetForegroundWindow() -eq $p.MainWindowHandle) { $ok = $true }
if (-not $ok) {
    throw "could not bring $ProcessName to foreground after 5 attempts - aborting (key would land elsewhere)"
}
$ext = 0; if ($Extended) { $ext = 1 }
[PsySendKey]::Key($Scan, $ext, $false) | Out-Null
Start-Sleep -Milliseconds $HoldMs
[PsySendKey]::Key($Scan, $ext, $true) | Out-Null
"sent scan=0x{0:X2} extended={1} hold={2}ms to {3}" -f $Scan, [bool]$Extended, $HoldMs, $ProcessName
