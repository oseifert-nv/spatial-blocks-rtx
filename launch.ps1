$ErrorActionPreference = 'Stop'
$gameRoot = $PSScriptRoot
$repoRoot = if ($env:OVSPATIALQUERY_REPO) { $env:OVSPATIALQUERY_REPO } else { Join-Path (Split-Path $gameRoot) 'ovspatialquery-prototype' }
$pythonPath = Join-Path $repoRoot '_build\venv\ovspatialqueryapp\Scripts\pythonw.exe'
$runtimePath = Join-Path $gameRoot 'runtime.json'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'The CPU library has not been built. Follow README.md to bootstrap ovspatialquery first.'
}
function Open-RunningGame {
    try {
        if (-not (Test-Path -LiteralPath $runtimePath)) { return $false }
        $runtime = Get-Content -Raw -LiteralPath $runtimePath | ConvertFrom-Json
        if ($runtime.url -notmatch '^http://127\.0\.0\.1:\d+$') { return $false }
        $health = Invoke-RestMethod -Uri ($runtime.url + '/api/health') -TimeoutSec 2
        if ($health.app -eq 'spatial-blocks' -and $health.pid -eq $runtime.pid) {
            Start-Process $runtime.url
            return $true
        }
    } catch { }
    return $false
}
if (Open-RunningGame) { exit 0 }
$appPath = Join-Path $gameRoot 'app.py'
$process = Start-Process -FilePath $pythonPath -ArgumentList @(('"' + $appPath + '"'),'--no-browser') -WorkingDirectory $gameRoot -WindowStyle Hidden -PassThru
for ($attempt=0; $attempt -lt 100; $attempt++) {
    Start-Sleep -Milliseconds 100
    # Windows virtual-environment launchers can delegate to a child interpreter,
    # so the health endpoint identifies readiness instead of the launcher PID.
    if (Open-RunningGame) { exit 0 }
    if ($process.HasExited) { throw 'Game startup failed. See game.log in the game folder.' }
}
throw 'Game startup took longer than expected. See game.log in the game folder.'
