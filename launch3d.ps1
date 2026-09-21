$ErrorActionPreference = 'Stop'
$gameRoot = $PSScriptRoot
$pythonPath = Join-Path $gameRoot '.venv3d\Scripts\python.exe'
$runtimePath = Join-Path $gameRoot 'runtime3d.json'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'The 3D environment is missing. Follow README-3D.md to install the renderer.'
}
function Open-RunningGame3D {
    try {
        if (-not (Test-Path -LiteralPath $runtimePath)) { return $false }
        $runtime = Get-Content -Raw -LiteralPath $runtimePath | ConvertFrom-Json
        if ($runtime.url -notmatch '^http://127\.0\.0\.1:\d+$') { return $false }
        $health = Invoke-RestMethod -Uri ($runtime.url + '/api/health') -TimeoutSec 2
        if ($health.app -eq 'spatial-blocks-3d' -and $health.pid -eq $runtime.pid) {
            Start-Process $runtime.url
            return $true
        }
    } catch { }
    return $false
}
if (Open-RunningGame3D) { exit 0 }
if (-not (Test-Path -LiteralPath (Join-Path $gameRoot 'assets3d\board.usda'))) {
    & (Join-Path $gameRoot '.venv3d\Scripts\python.exe') (Join-Path $gameRoot 'scene3d.py')
    if ($LASTEXITCODE -ne 0) { throw 'The 3D scene could not be generated.' }
}
$appPath = Join-Path $gameRoot 'app3d.py'
$process = Start-Process -FilePath $pythonPath -ArgumentList @(('"' + $appPath + '"')) -WorkingDirectory $gameRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $gameRoot 'renderer3d-out.log') -RedirectStandardError (Join-Path $gameRoot 'renderer3d-err.log') -PassThru
for ($attempt=0; $attempt -lt 150; $attempt++) {
    Start-Sleep -Milliseconds 100
    if (Open-RunningGame3D) { exit 0 }
    if ($process.HasExited) { throw 'Game startup failed. See game3d.log.' }
}
throw 'Game startup took longer than expected. See game3d.log.'
