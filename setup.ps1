param(
    [string]$Python = "",
    [switch]$SkipModels,
    [switch]$UiOnly,
    [ValidateSet("all", "image", "video", "ref2va")][string]$Models = "all"
)
$ErrorActionPreference = "Stop"
try {
    Set-Location -LiteralPath $PSScriptRoot
    $pythonArgs = @()
    if ($Python) {
        $pythonExe = $Python
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $pythonExe = "py"
        $pythonArgs = @("-3.12")
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $pythonExe = "python"
    } else {
        throw "Install Python 3.12 x64 from python.org first, then run setup.bat again."
    }
    $setupArgs = @((Join-Path $PSScriptRoot "scripts\setup.py"), "--models", $Models)
    if ($SkipModels) { $setupArgs += "--skip-models" }
    if ($UiOnly) { $setupArgs += "--ui-only" }
    & $pythonExe @pythonArgs @setupArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} catch {
    Write-Host $_ -ForegroundColor Red
    exit 1
}
