param(
    [string]$Version = "0.2.1"
)

$ErrorActionPreference = "Stop"
$InstallRoot = Join-Path $env:LOCALAPPDATA "HostSlotSwitch"
$Venv = Join-Path $InstallRoot "venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Cli = Join-Path $Venv "Scripts\host-slot-switch.exe"
$Wheel = "https://github.com/dolphin1404/host-slot-switch/releases/download/v$Version/host_slot_switch-$Version-py3-none-any.whl"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python 3.10 or newer is required. Install Python from python.org, then run this script again."
}

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
if (-not (Test-Path $Python)) {
    py -3 -m venv $Venv
}

& $Python -m pip install --upgrade $Wheel
$Config = & $Cli config path
if (-not (Test-Path $Config)) {
    & $Cli config init
}

& $Cli doctor
if ($LASTEXITCODE -ne 0) {
    throw "The device check failed. Connect and wake the mouse on this Windows host, then run the script again."
}
& $Cli hotkeys install --dry-run
& $Cli hotkeys install

Write-Host "Installed Host Slot Switch $Version."
Write-Host "Config: $Config"
Write-Host "Edit the JSON file and rerun 'host-slot-switch hotkeys install' to change shortcuts."
