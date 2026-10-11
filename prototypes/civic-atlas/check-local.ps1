[CmdletBinding()]
param([int]$Port = 8041, [switch]$Advance)
$ErrorActionPreference = 'Stop'
$atlasRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $atlasRoot
try {
    $env:ATLAS_URL = "http://127.0.0.1:$Port"
    & "$PSScriptRoot/start-local.ps1" -Port $Port
    & .venv/Scripts/python.exe -m pytest prototypes/civic-atlas/test_town500_world.py prototypes/civic-atlas/test_server.py prototypes/civic-atlas/test_reference_world.py -q
    if ($LASTEXITCODE) { throw 'Python acceptance failed.' }
    & .venv/Scripts/python.exe -m ruff check prototypes/civic-atlas
    if ($LASTEXITCODE) { throw 'Python static checks failed.' }
    if (!(Test-Path 'out/civic-atlas/browser/node_modules/playwright-core/index.mjs')) {
        & npm.cmd install --prefix out/civic-atlas/browser --no-save playwright-core@1.64.0
        if ($LASTEXITCODE) { throw 'Browser tooling installation failed.' }
    }
    # Heavy browser suites run sequentially. The first three never advance time.
    foreach ($atlasSuite in @('check-town-template-renderer.mjs','check-town500.mjs','check-welcome.mjs','check-workspace-records.mjs','check-map-workspace.mjs')) {
        & node "prototypes/civic-atlas/$atlasSuite"
        if ($LASTEXITCODE) { throw "$atlasSuite failed." }
    }
    $atlasPreviousAdvance = $env:ATLAS_ADVANCE
    try {
        $env:ATLAS_ADVANCE = if ($Advance) { '1' } else { '0' }
        & node prototypes/civic-atlas/check-browser.mjs
        if ($LASTEXITCODE) { throw 'Shell browser acceptance failed.' }
    } finally { $env:ATLAS_ADVANCE = $atlasPreviousAdvance }
    Write-Host 'PASS: local source, renderer, town, welcome, records and shell checks.'
} finally { Pop-Location }
