<#
.SYNOPSIS
  Closed-loop navigation primitives for a game driven by synthetic keys: turn to a
  heading, walk a measured distance, report pose.

.DESCRIPTION
  Written for Unreal-Engine-era titles whose telemetry exposes player position and
  rotation, but nothing here is Unreal-specific except the default rotator scale.
  Give it a log whose newest matching line carries a pose, a regex to pull the
  numbers out, and the keys bound to movement, and it will drive.

  Turning is CLOSED-LOOP - turn, re-measure, correct. Open-loop timing is good to a
  few degrees, which compounds badly over a route; two or three corrections land a
  heading inside tolerance reliably (measured: within 0.8 degrees on XIII).

.WHY YOU PROBABLY NEED THIS AT ALL
  If the game holds the mouse in DirectInput EXCLUSIVE mode, injected mouse motion
  does nothing (measured on XIII 2003: 600px -> 0.0 degrees) while injected KEYS work
  fine. View control then has to come from a key bound to the engine's own turn
  action. Unreal-family engines define input as named ALIASES in an ini, and a game
  may define a turn alias and never bind it to any key - which reads as "the engine
  cannot do this" when only the binding is missing. Check the alias table first.

.TWO TRAPS THAT COST REAL TIME
  * DO NOT WRAP AN ALREADY-UNWRAPPED ROTATOR. Some builds report yaw as a raw
    accumulating integer that runs straight through its wrap boundary. Applying a
    shortest-arc wrap to that turns a real -199 degree turn into an apparent +161,
    which looks exactly like the turn key spontaneously reversing direction. Pass
    -WrapUnits only when you have CONFIRMED the value wraps.
  * The ini the game writes may not be the ini to edit. At least one title deletes
    its user ini on exit and regenerates it from a template at launch, so edits to
    the former always vanish. Verify a binding survives a restart.

.CALIBRATION
  Rates are per-game. Measure once (hold a key for a known time, read the pose
  delta) and pass them in. Defaults are XIII (2003), kept as a worked example:
  ~157 units/s movement, 166 deg/s turn.

.EXAMPLES
  $log = "$env:TEMP\xiii_capture\xiii_automation.log"
  .\unreal-nav.ps1 -LogPath $log -Process XIII -Pose
  .\unreal-nav.ps1 -LogPath $log -Process XIII -TurnBy 90
  .\unreal-nav.ps1 -LogPath $log -Process XIII -WalkMs 1200
#>
param(
    [Parameter(Mandatory=$true)][string]$LogPath,
    [string]$Process   = "XIII",
    [string]$PoseRegex = 'pos=([-\d.]+),([-\d.]+),([-\d.]+) rot=([-\d]+),([-\d]+),([-\d]+)',
    [double]$RotUnits  = 65536,   # rotator units per revolution (Unreal = 65536)
    [double]$TurnRate  = 166.0,   # degrees/sec while a turn key is held
    [double]$Tolerance = 3.0,     # stop correcting inside this many degrees
    [switch]$WrapUnits,           # ONLY if the yaw genuinely wraps - see notes above
    [hashtable]$Keys,             # name -> DIK scancode; see $DefaultKeys below
    [double]$TurnTo    = [double]::NaN,
    [double]$TurnBy    = [double]::NaN,
    [int]   $WalkMs    = 0,
    [string]$WalkKey   = "Forward",
    [switch]$Pose
)
$ErrorActionPreference = 'Stop'

# XIII (2003) after binding its four unbound turn aliases to spare keys.
$DefaultKeys = @{
    Forward = 0x11; Back = 0x1F; Left = 0x1E; Right = 0x20
    TurnNeg = 0x16; TurnPos = 0x24
    LookUp  = 0x0E; LookDown = 0x0D; Jump = 0x39
}
if (-not $Keys) { $Keys = $DefaultKeys }

$SendKey = Join-Path $PSScriptRoot "send-key.ps1"
if (-not (Test-Path $SendKey)) { throw "send-key.ps1 not found beside this script" }

function Get-Pose {
    $line = Select-String -Path $LogPath -Pattern $PoseRegex | Select-Object -Last 1
    if (-not $line) { return $null }
    if ($line.Line -match $PoseRegex) {
        $pitchRaw = [double]$Matches[4]
        if ($pitchRaw -gt ($RotUnits/2)) { $pitchRaw -= $RotUnits }   # pitch is small+signed
        $yawRaw = [double]$Matches[5]
        if ($WrapUnits) { $yawRaw = $yawRaw % $RotUnits }
        [pscustomobject]@{
            X = [double]$Matches[1]; Y = [double]$Matches[2]; Z = [double]$Matches[3]
            YawDeg = $yawRaw * 360.0 / $RotUnits
            PitchDeg = $pitchRaw * 360.0 / $RotUnits
        }
    }
}

function Press($name, $ms) {
    if (-not $Keys.ContainsKey($name)) { throw "no key mapped for '$name'" }
    & $SendKey -ProcessName $Process -Scan $Keys[$name] -HoldMs $ms | Out-Null
    Start-Sleep -Milliseconds 900
}

function Turn-By([double]$deg) {
    $p = Get-Pose
    if (-not $p) { throw "no pose line in $LogPath - is the game in gameplay?" }
    $target = $p.YawDeg + $deg
    for ($i = 1; $i -le 4; $i++) {
        $err = $target - (Get-Pose).YawDeg
        if ([math]::Abs($err) -lt $Tolerance) { break }
        # Cap one hold so a single command cannot wildly overshoot if the rate
        # differs on this surface or level.
        $ms = [int][math]::Round([math]::Min([math]::Abs($err), 170.0) / $TurnRate * 1000.0)
        if ($ms -lt 40) { $ms = 40 }
        Press $(if ($err -lt 0) { "TurnNeg" } else { "TurnPos" }) $ms
    }
    $f = Get-Pose
    "turn -> heading {0,8:N1}   (target {1,8:N1}, error {2,5:N1})" -f $f.YawDeg, $target, ($f.YawDeg - $target)
}

if ($Pose) {
    $p = Get-Pose
    if ($p) { "pos {0,9:N1} {1,9:N1} {2,8:N1}   yaw {3,9:N1}   pitch {4,6:N1}" -f $p.X,$p.Y,$p.Z,$p.YawDeg,$p.PitchDeg }
    else    { "(no pose found in $LogPath)" }
}
if (-not [double]::IsNaN($TurnBy)) { Turn-By $TurnBy }
if (-not [double]::IsNaN($TurnTo)) { Turn-By ($TurnTo - (Get-Pose).YawDeg) }
if ($WalkMs -gt 0) {
    $b = Get-Pose
    Press $WalkKey $WalkMs
    $a = Get-Pose
    $d = [math]::Sqrt(($a.X-$b.X)*($a.X-$b.X) + ($a.Y-$b.Y)*($a.Y-$b.Y))
    "walk {0} {1}ms -> {2:N1} units   pos {3,9:N1} {4,9:N1} {5,8:N1}" -f $WalkKey, $WalkMs, $d, $a.X, $a.Y, $a.Z
}
