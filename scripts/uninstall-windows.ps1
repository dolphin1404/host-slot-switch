$ErrorActionPreference = "Stop"
$InstallRoot = Join-Path $env:LOCALAPPDATA "HostSlotSwitch"
$Cli = Join-Path $InstallRoot "venv\Scripts\host-slot-switch.exe"

if (Test-Path $Cli) {
    & $Cli hotkeys uninstall
}

Write-Host "The startup listener was removed."
Write-Host "You may now delete $InstallRoot if you also want to remove the program and config."
