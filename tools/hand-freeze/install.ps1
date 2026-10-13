# install.ps1 -- copies Hand Freeze from dist\ to %LOCALAPPDATA%\Programs\HandFreeze and puts its icon on the desktop.
# Nothing is switched on: the app's ON/OFF button does that. Run again after a rebuild (close the app first).
#   powershell -ExecutionPolicy Bypass -File install.ps1 [-From <folder with the built files>]
param([string]$From = (Join-Path $PSScriptRoot "dist"))
$ErrorActionPreference = "Stop"
$to = Join-Path $env:LOCALAPPDATA "Programs\HandFreeze"
New-Item -ItemType Directory -Force $to | Out-Null
foreach ($f in "HandFreeze.exe", "hand_freeze_layer.dll", "hand_freeze.ico") {
    Copy-Item (Join-Path $From $f) (Join-Path $to $f) -Force
}
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Hand Freeze.lnk"))
$lnk.TargetPath = Join-Path $to "HandFreeze.exe"
$lnk.WorkingDirectory = $to
$lnk.IconLocation = (Join-Path $to "hand_freeze.ico") + ",0"
$lnk.Description = "Hold both VR controllers still in any OpenXR game"
$lnk.Save()
Write-Output "Installed to $to, icon on the desktop."
