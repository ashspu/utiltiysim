[CmdletBinding()]
param([int]$Port = 0, [ValidateSet('riverbend-500','two-river-forest-500')][string]$Preset, [switch]$OpenBrowser, [switch]$Restart)
$ErrorActionPreference = 'Stop'
$atlasRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$atlasPython = Join-Path $atlasRoot '.venv/Scripts/python.exe'
$atlasServer = Join-Path $PSScriptRoot 'server.py'
$atlasStore = Join-Path $atlasRoot $(if ($Preset) { "out/civic-atlas-$Preset-v2" } else { 'out/civic-atlas-town500-v2' })
$atlasName = if ($Preset -eq 'two-river-forest-500') { 'Two River Forest' } elseif ($Preset) { 'Riverbend' } else { 'Fairhaven' }
if (!$Port) { $Port = if ($Preset -eq 'two-river-forest-500') { 8043 } elseif ($Preset) { 8042 } else { 8041 } }
$atlasLogs = Join-Path $atlasRoot 'out/civic-atlas'
$atlasUrl = "http://127.0.0.1:$Port"
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Choose a port from 1024 through 65535.' }
if (!(Test-Path -LiteralPath $atlasPython)) { throw "Install dependencies from $atlasRoot with: python -m uv sync --frozen --all-extras --python 3.11" }
if (!(Test-Path -LiteralPath (Join-Path $atlasRoot 'packages/town-viewer/dist/vendor/three.module.js'))) { throw 'Run npm ci in packages/town-viewer before starting.' }
if ($Restart) {
    $atlasListener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($atlasListener) {
        $atlasOwned = Get-CimInstance Win32_Process -Filter "ProcessId = $($atlasListener.OwningProcess)"
        if (!$atlasOwned.CommandLine -or $atlasOwned.CommandLine.IndexOf($atlasServer, [StringComparison]::OrdinalIgnoreCase) -lt 0 -or $atlasOwned.CommandLine.IndexOf($atlasStore, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
            throw "Port $Port does not belong to this checkout and store. It was not stopped."
        }
        Stop-Process -Id $atlasOwned.ProcessId
        Wait-Process -Id $atlasOwned.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
    }
}
$atlasExisting = $null
try { $atlasExisting = Invoke-RestMethod "$atlasUrl/atlas/api/bootstrap" -TimeoutSec 3 } catch {}
if ($atlasExisting) {
    if (($Preset -and $atlasExisting.snapshot.atlasDesign.presetId -ne $Preset) -or (!$Preset -and $atlasExisting.snapshot.atlasDesign.version -ne 'civic-atlas-town500/1')) { throw "Port $Port serves a different world. Choose another port." }
    Write-Host "$atlasName is already running: $atlasUrl/#welcome"
} else {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $Port is occupied by another application. Choose another port." }
    New-Item -ItemType Directory -Force -Path $atlasLogs | Out-Null
    $atlasProfile = if ($Preset) { "--preset $Preset" } else { '--town500' }
    $atlasArguments = '"{0}" {3} --port {1} --store "{2}"' -f $atlasServer, $Port, $atlasStore, $atlasProfile
    $atlasProcess = Start-Process -FilePath $atlasPython -ArgumentList $atlasArguments -WorkingDirectory $atlasRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $atlasLogs "server-$Port.stdout.log") -RedirectStandardError (Join-Path $atlasLogs "server-$Port.stderr.log") -PassThru
    Write-Host "Opening the saved world. First launch creates seven simulation days. Server process: $($atlasProcess.Id)"
    $atlasReady = $false
    for ($atlasAttempt = 0; $atlasAttempt -lt 180; $atlasAttempt++) {
        try {
            $atlasState = Invoke-RestMethod "$atlasUrl/atlas/api/state" -TimeoutSec 2
            if ($atlasState.environmentId -eq $atlasName) { $atlasReady = $true; break }
        } catch {}
        $atlasProcess.Refresh()
        if ($atlasProcess.HasExited) { throw "The server exited. See $atlasLogs/server-$Port.stderr.log" }
        Start-Sleep -Seconds 1
    }
    if (!$atlasReady) { throw "Startup is still pending. Check $atlasLogs/server-$Port.stderr.log before retrying." }
    Write-Host "$atlasName is ready: $atlasUrl/#welcome"
}
Write-Host "Map: $atlasUrl/#map"
Write-Host "Quality checks: $atlasUrl/#quality"
Write-Host "Saved world: $atlasStore"
if ($OpenBrowser) { $atlasView = if ($Preset) { 'map' } else { 'welcome' }; Start-Process "$atlasUrl/#$atlasView" }
