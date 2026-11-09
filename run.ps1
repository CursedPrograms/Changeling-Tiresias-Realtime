# Changeling Tiresias Realtime runs in Changeling Tiresias's environment: it needs Changeling Tiresias and Changeling
# Simia Realtime next to this folder (as in Changeling Studio). Missing ones are fetched here.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Studio = Split-Path $PSScriptRoot -Parent
foreach ($a in @("Tiresias", "Simia-Realtime")) {
    $dir = Join-Path $Studio "Changeling-$a"
    if (-not (Test-Path $dir)) {
        Write-Host "Getting Changeling $a ..."
        git clone "https://github.com/CursedPrograms/Changeling-$a" $dir
    }
}

# The environment: Changeling Tiresias's, or a sibling's (Tiresias, Chronos and Natio need the same things).
$Py = $null
foreach ($a in @("Tiresias", "Tiresias", "Chronos", "Natio")) {
    $p = Join-Path $Studio "Changeling-$a\psdenv\Scripts\python.exe"
    $torch = Join-Path $Studio "Changeling-$a\psdenv\Lib\site-packages	orch"
    if (-not $Py -and (Test-Path $torch)) { $Py = $p }
}
if (-not $Py) {
    Write-Host "Setting up Changeling Tiresias first, once: its environment and its models."
    & (Join-Path $Studio "Changeling-Tiresias\run.ps1") --download-models
    $Py = Join-Path $Studio "Changeling-Tiresias\psdenv\Scripts\python.exe"
}
if (-not (Test-Path (Join-Path $Studio "Changeling-Simia-Realtime\venv\Scripts\python.exe"))) {
    Write-Host "Changeling Simia Realtime isn't set up yet: start its run.ps1 once, then come back."
}

& $Py live.py @args
