<#
.SYNOPSIS
  Static inspection of a PE file (exe/dll): list or check exports, and dump raw
  bytes at a virtual address or at an exported symbol.

.DESCRIPTION
  Everything here reads the file ON DISK. No process is started and no debugger
  is attached, which matters when the rule is "only the user launches the game" —
  this lets recon happen without the game running at all.

  Three jobs, one script:

    -Symbols <names>   Report which of these symbols the module actually exports.
    -VA <hex>          Dump bytes at a virtual address.
    -AtSymbol <name>   Dump bytes at an exported symbol (resolves it first).

.WHY THIS EXISTS
  This logic was written from scratch twice in one session, hitting the same two
  traps both times:

   * The optional header starts at e_lfanew + 24 (PE signature 4 + COFF header
     20). Using +20 makes every data directory read garbage and reports "no
     exports" for a module that plainly has thousands.
   * "Symbol not found" is only as strong as your search. A raw string scan finds
     export NAME STRINGS whether or not they are real exports, and misses nothing
     — but it also cannot tell you an export exists. Parse the export directory.

.EXAMPLES
  # Which of these does the module really export?
  .\pe-inspect.ps1 -Path Engine.dll -Symbols '?Foo@@YAXXZ','?Bar@@YAXXZ'

  # First 64 bytes of a function, to check a hook prologue before patching it
  .\pe-inspect.ps1 -Path Engine.dll -AtSymbol '?Tick@AActor@@UAEHM@Z' -Count 64

  # Bytes at an absolute VA (image base is read from the file, not assumed)
  .\pe-inspect.ps1 -Path Game.exe -VA 0x569000 -Count 96
#>
param(
    [Parameter(Mandatory=$true)][string]$Path,
    [string[]]$Symbols,
    [string]$VA,
    [string]$AtSymbol,
    [int]$Count = 64
)

$ErrorActionPreference = 'Stop'
$full = (Resolve-Path $Path).Path
$fs = [System.IO.File]::OpenRead($full)
$br = New-Object System.IO.BinaryReader($fs)

try {
    $fs.Position = 0x3C
    $peOff = $br.ReadInt32()
    $fs.Position = $peOff + 4
    $machine     = $br.ReadUInt16()
    $numSections = $br.ReadUInt16()

    # PE signature (4) + COFF header (20). Getting this wrong is the classic bug.
    $fs.Position = $peOff + 24
    $optStart = $fs.Position
    $magic    = $br.ReadUInt16()
    $isPE32Plus = ($magic -eq 0x20b)

    if ($isPE32Plus) { $fs.Position = $optStart + 24; $imageBase = $br.ReadUInt64() }
    else             { $fs.Position = $optStart + 28; $imageBase = [uint64]$br.ReadUInt32() }

    $ddOff = if ($isPE32Plus) { $optStart + 112 } else { $optStart + 96 }
    $fs.Position = $ddOff
    $expRva = $br.ReadUInt32()

    $optSize  = if ($isPE32Plus) { 240 } else { 224 }
    $secStart = $optStart + $optSize

    $sections = @()
    for ($i = 0; $i -lt $numSections; $i++) {
        $fs.Position = $secStart + ($i * 40)
        $nameBytes = $br.ReadBytes(8)
        # NOTE: this local was originally named $va, which silently aliased the
        # $VA PARAMETER (PowerShell variables are case-insensitive) and made the
        # script report a bogus "VA is below the image base" on every run where
        # -VA was never passed. The trap this file's header warns about, hit
        # inside this file. Keep section-local names prefixed.
        $secVSize = $br.ReadUInt32(); $secVA = $br.ReadUInt32()
        $secRawSize = $br.ReadUInt32(); $secRawPtr = $br.ReadUInt32()
        $sections += [pscustomobject]@{
            Name    = [System.Text.Encoding]::ASCII.GetString($nameBytes).Trim([char]0)
            VSize   = $secVSize; VA = $secVA; RawSize = $secRawSize; RawPtr = $secRawPtr
        }
    }

    function Convert-RvaToOffset([uint32]$rva) {
        foreach ($s in $script:sections) {
            $end = $s.VA + [Math]::Max($s.VSize, $s.RawSize)
            if ($rva -ge $s.VA -and $rva -lt $end) { return $s.RawPtr + ($rva - $s.VA) }
        }
        return -1
    }
    $script:sections = $sections

    function Get-ExportTable {
        if ($expRva -eq 0) { return @{} }
        $expOff = Convert-RvaToOffset $expRva
        if ($expOff -lt 0) { return @{} }
        $fs.Position = $expOff + 16
        $null      = $br.ReadUInt32()   # ordinal base
        $null      = $br.ReadUInt32()   # number of functions
        $numNames  = $br.ReadUInt32()
        $funcsRva  = $br.ReadUInt32()
        $namesRva  = $br.ReadUInt32()
        $ordsRva   = $br.ReadUInt32()
        $namesOff  = Convert-RvaToOffset $namesRva
        $funcsOff  = Convert-RvaToOffset $funcsRva
        $ordsOff   = Convert-RvaToOffset $ordsRva

        $table = @{}
        for ($i = 0; $i -lt $numNames; $i++) {
            $fs.Position = $namesOff + ($i * 4)
            $nOff = Convert-RvaToOffset $br.ReadUInt32()
            if ($nOff -lt 0) { continue }
            $fs.Position = $nOff
            $sb = New-Object System.Text.StringBuilder
            while ($true) { $c = $br.ReadByte(); if ($c -eq 0) { break }; [void]$sb.Append([char]$c) }
            $fs.Position = $ordsOff + ($i * 2)
            $ord = $br.ReadUInt16()
            $fs.Position = $funcsOff + ($ord * 4)
            $table[$sb.ToString()] = $br.ReadUInt32()
        }
        return $table
    }

    function Write-BytesAt([uint32]$rva, [uint64]$dispBase, [int]$n) {
        $off = Convert-RvaToOffset $rva
        if ($off -lt 0) { "  RVA 0x{0:X} is not inside any section" -f $rva; return }
        $fs.Position = $off
        $bytes = $br.ReadBytes($n)
        for ($i = 0; $i -lt $bytes.Length; $i += 16) {
            $chunk = $bytes[$i..([Math]::Min($i + 15, $bytes.Length - 1))]
            $hex = ($chunk | ForEach-Object { "{0:X2}" -f $_ }) -join ' '
            "{0:X8}  {1}" -f ($dispBase + $rva + $i), $hex
        }
    }

    "Module    : {0}" -f (Split-Path $full -Leaf)
    "Machine   : 0x{0:X}  ({1})" -f $machine, $(if ($machine -eq 0x14c) { "i386 / 32-bit" } elseif ($machine -eq 0x8664) { "x64" } else { "other" })
    "ImageBase : 0x{0:X}" -f $imageBase
    ""

    if ($Symbols) {
        $table = Get-ExportTable
        "Exports in table: {0}" -f $table.Count
        foreach ($want in $Symbols) {
            if ($table.ContainsKey($want)) { "  FOUND    (RVA 0x{0:X})  {1}" -f $table[$want], $want }
            else                           { "  MISSING                {0}" -f $want }
        }
        ""
    }

    if ($AtSymbol) {
        $table = Get-ExportTable
        if (-not $table.ContainsKey($AtSymbol)) { "Symbol NOT exported: $AtSymbol" }
        else {
            $rva = $table[$AtSymbol]
            "Symbol    : {0}" -f $AtSymbol
            "RVA       : 0x{0:X}   VA: 0x{1:X}" -f $rva, ($imageBase + $rva)
            Write-BytesAt $rva $imageBase $Count
        }
        ""
    }

    if ($VA) {
        $target = [Convert]::ToUInt64(($VA -replace '^0x',''), 16)
        if ($target -lt $imageBase) { "VA 0x{0:X} is below the image base" -f $target }
        else { Write-BytesAt ([uint32]($target - $imageBase)) $imageBase $Count }
    }
}
finally {
    $br.Close()
}
