# Enumerate a PE's exports, optionally filtered by regex.
# Parses the export directory rather than scanning for strings: a string scan
# finds names that are merely referenced and cannot prove a symbol is exported.
param(
    [Parameter(Mandatory=$true)][string]$Path,
    [string]$Match = ".",
    [int]$Limit = 200
)
$b = [System.IO.File]::ReadAllBytes((Resolve-Path $Path).Path)
$pe = [BitConverter]::ToInt32($b, 0x3C)
$nSec = [BitConverter]::ToUInt16($b, $pe + 6)
$opt = $pe + 24                       # PE sig (4) + COFF header (20). NOT +20.
$magic = [BitConverter]::ToUInt16($b, $opt)
$optSize = if ($magic -eq 0x20b) { 240 } else { 224 }
$ddOff = if ($magic -eq 0x20b) { $opt + 112 } else { $opt + 96 }
$expRva = [BitConverter]::ToUInt32($b, $ddOff)
if ($expRva -eq 0) { "no export directory"; exit }

$secStart = $opt + $optSize
$secs = @()
for ($i = 0; $i -lt $nSec; $i++) {
    $s = $secStart + ($i * 40)
    $secs += [pscustomobject]@{
        VA  = [BitConverter]::ToUInt32($b, $s + 12)
        Sz  = [BitConverter]::ToUInt32($b, $s + 16)
        Raw = [BitConverter]::ToUInt32($b, $s + 20)
    }
}
function R2O([uint32]$rva) {
    foreach ($s in $secs) { if ($rva -ge $s.VA -and $rva -lt ($s.VA + $s.Sz)) { return $s.Raw + ($rva - $s.VA) } }
    return 0
}

$e = R2O $expRva
$nNames  = [BitConverter]::ToUInt32($b, $e + 24)
$namesRva = [BitConverter]::ToUInt32($b, $e + 32)
$namesOff = R2O $namesRva

$hits = 0
for ($i = 0; $i -lt $nNames; $i++) {
    $nr = [BitConverter]::ToUInt32($b, $namesOff + ($i * 4))
    $no = R2O $nr
    if ($no -eq 0) { continue }
    $end = $no
    while ($b[$end] -ne 0) { $end++ }
    $name = [System.Text.Encoding]::ASCII.GetString($b, $no, $end - $no)
    if ($name -match $Match) {
        $name
        $hits++
        if ($hits -ge $Limit) { "... (stopped at $Limit)"; break }
    }
}
if ($hits -eq 0) { "no exports matching /$Match/" } else { "`n$hits match(es) of $nNames exports" }
