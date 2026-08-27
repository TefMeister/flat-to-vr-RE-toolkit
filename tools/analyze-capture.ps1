<#
.SYNOPSIS
  Measure a screen capture. Two modes: how much of the frame is near-black
  (-Black), and the horizontal disparity between the two eyes of a side-by-side
  stereo capture (-Stereo).

.DESCRIPTION
  -Black   Reports the percentage of near-black pixels plus a coarse
           left-to-right column profile, so edge-black can be told from
           centre-black. Useful for measuring unrendered regions.

  -Stereo  Splits a side-by-side capture in half and finds the horizontal shift
           that best aligns one eye onto the other. Larger disparity = the
           content sits nearer the viewer. Useful for measuring the virtual
           depth of a HUD or overlay without a headset.

.IMPORTANT
  A number from this script is EVIDENCE, NOT A STATE CHECK. Do not use a
  brightness figure to decide whether a game is in gameplay or in a menu — that
  exact shortcut produced three invalidated experiments and one false conclusion
  in permanent notes. Open the image.

.WHY IT LOOKS LIKE THIS
  Two PowerShell traps, both paid for in real time:

   * GetPixel per pixel is unusably slow (minutes for one frame). LockBits plus a
     single Marshal.Copy is the only workable approach.
   * PowerShell variables are CASE-INSENSITIVE. A loop counter $r silently
     clobbers an array named $R, and the failure surfaces as a bizarre "cannot
     index into System.Int32" thousands of lines deep. Names here are
     deliberately distinct - keep them that way.

.EXAMPLES
  .\analyze-capture.ps1 -Path frame.png -Black
  .\analyze-capture.ps1 -Path frame.png -Stereo
#>
param(
    [Parameter(Mandatory=$true)][string]$Path,
    [switch]$Black,
    [switch]$Stereo,
    [int]$Threshold = 24,
    [int]$Top = 30,
    [int]$Bottom = 0,
    [int]$MaxShift = 40
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

if (-not $Black -and -not $Stereo) { $Black = $true }

$bmp    = [System.Drawing.Bitmap]::FromFile((Resolve-Path $Path).Path)
$imgW   = $bmp.Width
$imgH   = $bmp.Height
$rc     = New-Object System.Drawing.Rectangle 0, 0, $imgW, $imgH
$data   = $bmp.LockBits($rc, [System.Drawing.Imaging.ImageLockMode]::ReadOnly,
                        [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$stride = $data.Stride
$bytes  = New-Object 'byte[]' ($stride * $imgH)
[System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $bytes, 0, $bytes.Length)
$bmp.UnlockBits($data)
$bmp.Dispose()

if ($Bottom -le 0) { $Bottom = $imgH - 4 }
if ($Bottom -ge $imgH) { $Bottom = $imgH - 1 }

$xStart = 4
$halfW  = [int](($imgW - 8) / 2)

if ($Black) {
    # Left eye only, so a side-by-side capture is not double-counted.
    $darkCount = 0; $totalCount = 0
    $colCount  = 8
    $colDark   = New-Object 'int[]' $colCount
    $colTotal  = New-Object 'int[]' $colCount
    for ($yy = $Top; $yy -lt $Bottom; $yy += 2) {
        $rowBase = $yy * $stride
        for ($ii = 0; $ii -lt $halfW; $ii += 2) {
            $o = $rowBase + ($xStart + $ii) * 4
            $lum = 0.299*$bytes[$o+2] + 0.587*$bytes[$o+1] + 0.114*$bytes[$o]
            $ci = [int]($ii * $colCount / $halfW)
            if ($ci -ge $colCount) { $ci = $colCount - 1 }
            $colTotal[$ci]++; $totalCount++
            if ($lum -lt $Threshold) { $darkCount++; $colDark[$ci]++ }
        }
    }
    $pct = if ($totalCount -gt 0) { [math]::Round(100.0 * $darkCount / $totalCount, 2) } else { 0 }
    $profile = for ($ci = 0; $ci -lt $colCount; $ci++) {
        if ($colTotal[$ci] -gt 0) { "{0,5:N1}" -f (100.0 * $colDark[$ci] / $colTotal[$ci]) } else { "  n/a" }
    }
    "{0,-20} black={1,6}%   columns L..R: {2}" -f (Split-Path $Path -Leaf), $pct, ($profile -join ' ')
}

if ($Stereo) {
    $xRight = $xStart + $halfW
    $rowList = @()
    for ($yy = $Top; $yy -lt $Bottom; $yy += 3) { $rowList += $yy }
    $nRows = $rowList.Count

    $bandLeft  = New-Object 'double[]' ($nRows * $halfW)
    $bandRight = New-Object 'double[]' ($nRows * $halfW)
    for ($ri = 0; $ri -lt $nRows; $ri++) {
        $rowBase = $rowList[$ri] * $stride
        $outBase = $ri * $halfW
        for ($ii = 0; $ii -lt $halfW; $ii++) {
            $o1 = $rowBase + ($xStart + $ii) * 4
            $bandLeft[$outBase + $ii]  = 0.299*$bytes[$o1+2] + 0.587*$bytes[$o1+1] + 0.114*$bytes[$o1]
            $o2 = $rowBase + ($xRight + $ii) * 4
            $bandRight[$outBase + $ii] = 0.299*$bytes[$o2+2] + 0.587*$bytes[$o2+1] + 0.114*$bytes[$o2]
        }
    }

    $bestShift = 0; $bestScore = [double]::MaxValue
    for ($sh = -$MaxShift; $sh -le $MaxShift; $sh++) {
        $tot = 0.0; $cnt = 0
        for ($ri = 0; $ri -lt $nRows; $ri++) {
            $outBase = $ri * $halfW
            $lo = [Math]::Max(0, -$sh)
            $hi = [Math]::Min($halfW, $halfW - $sh)
            for ($ii = $lo; $ii -lt $hi; $ii++) {
                $d = $bandLeft[$outBase + $ii] - $bandRight[$outBase + $ii + $sh]
                $tot += $d * $d; $cnt++
            }
        }
        if ($cnt -eq 0) { continue }
        $score = $tot / $cnt
        if ($score -lt $bestScore) { $bestScore = $score; $bestShift = $sh }
    }
    "{0,-20} halfW={1}px rows={2}  BEST SHIFT = {3,3} px  (mse {4})" -f `
        (Split-Path $Path -Leaf), $halfW, $nRows, $bestShift, [math]::Round($bestScore,1)
}
