param(
    [switch]$UiOnly,
    [switch]$VerifyHashes,
    [switch]$FastDisk,
    [switch]$NoBrowser,
    [ValidateSet("all", "image", "video", "ref2va")][string]$Models = "all",
    [ValidateRange(1024,65535)][int]$StudioPort = 8230,
    [ValidateRange(1024,65535)][int]$EnginePort = 8188
)
$ErrorActionPreference = "Stop"
try {
    Set-Location -LiteralPath $PSScriptRoot
    $pythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $pythonExe)) { throw "Run setup.bat first." }
    $launchArgs = @((Join-Path $PSScriptRoot "scripts\launch.py"), "--models", $Models, "--studio-port", $StudioPort, "--engine-port", $EnginePort)
    if ($UiOnly) { $launchArgs += "--ui-only" }
    if ($VerifyHashes) { $launchArgs += "--verify-hashes" }
    if ($FastDisk) { $launchArgs += "--fast-disk" }
    if ($NoBrowser) { $launchArgs += "--no-browser" }
    & $pythonExe @launchArgs
    exit $LASTEXITCODE
} catch {
    Write-Host $_ -ForegroundColor Red
    exit 1
}
