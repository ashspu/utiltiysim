[CmdletBinding()]
param([int]$Port = 8042)
$ErrorActionPreference = 'Stop'
$atlasRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $atlasRoot
try {
    $env:ATLAS_URL = "http://127.0.0.1:$Port"
    & "$PSScriptRoot/start-local.ps1" -Preset riverbend-500 -Port $Port
    & .venv/Scripts/python.exe -m pytest prototypes/civic-atlas/test_preset_world.py prototypes/civic-atlas/test_reconstruction.py -q
    if ($LASTEXITCODE) { throw 'Preset source and binding checks failed.' }
    & .venv/Scripts/python.exe -m ruff check prototypes/civic-atlas
    if ($LASTEXITCODE) { throw 'Static checks failed.' }
    if (!(Test-Path 'out/civic-atlas/browser/node_modules/playwright-core/index.mjs')) {
        & npm.cmd install --prefix out/civic-atlas/browser --no-save playwright-core@1.64.0
        if ($LASTEXITCODE) { throw 'Browser tooling installation failed.' }
    }
    foreach ($atlasSuite in @('check-reconstruction.mjs','check-preset.mjs','check-map-workspace.mjs','check-workspace-records.mjs')) {
        & node "prototypes/civic-atlas/$atlasSuite"
        if ($LASTEXITCODE) { throw "$atlasSuite failed." }
    }
    Write-Host 'PASS: fixed preset, SVG bindings, real roof picking, saved readings and immersive map.'
} finally { Pop-Location }
