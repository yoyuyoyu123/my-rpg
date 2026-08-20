# Wuji RPG backend launcher.
# Run from this directory with: .\dev.ps1

param(
    [int]$Port = 8000,
    [switch]$Stop,
    [switch]$NoReload
)

$ErrorActionPreference = 'Stop'

function Stop-OnPort([int]$TargetPort) {
    $connections = @(Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue)
    if ($connections.Count -eq 0) { return $false }

    $stopped = $false
    foreach ($connection in $connections) {
        $processId = [int]$connection.OwningProcess
        try {
            $process = Get-Process -Id $processId -ErrorAction Stop
            Write-Host "Stopping process $($process.ProcessName) (PID $processId) on port $TargetPort" -ForegroundColor Yellow
            Stop-Process -Id $processId -Force -ErrorAction Stop
            $stopped = $true
        } catch {
            Write-Host "Process $processId is already gone" -ForegroundColor DarkGray
        }
    }
    if ($stopped) { Start-Sleep -Seconds 2 }
    return $stopped
}

Write-Host ''
Write-Host 'Wuji RPG backend' -ForegroundColor Cyan
Stop-OnPort $Port | Out-Null

if ($Stop) {
    Write-Host 'Stopped.' -ForegroundColor Green
    exit 0
}

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host 'Virtual environment not found.' -ForegroundColor Red
    Write-Host 'Create it with: python -m venv .venv' -ForegroundColor Gray
    exit 1
}

try {
    $version = (& $python --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^Python\s+') {
        throw 'invalid Python launcher'
    }
} catch {
    Write-Host 'The Python executable in .venv is invalid.' -ForegroundColor Red
    Write-Host 'Recreate .venv, then install requirements.txt.' -ForegroundColor Gray
    exit 1
}

try {
    $dependencyCheck = (& $python -c "import fastapi, pydantic, pydantic_core, sqlalchemy, greenlet; print('dependencies ok')" 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $dependencyCheck -notmatch 'dependencies ok') {
        throw 'dependency import failed'
    }
} catch {
    Write-Host 'Python dependencies are incomplete or built for another Python version.' -ForegroundColor Red
    Write-Host 'Repair with: .\.venv\Scripts\python.exe -m pip install --force-reinstall -r requirements.txt' -ForegroundColor Gray
    exit 1
}

$envFile = Join-Path $PSScriptRoot '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    Write-Host 'Warning: .env does not exist. The server will start without provider keys.' -ForegroundColor Yellow
}

Write-Host "Local: http://127.0.0.1:$Port/" -ForegroundColor Green
Write-Host "Docs:  http://127.0.0.1:$Port/docs" -ForegroundColor DarkGray
Write-Host 'Press Ctrl+C to stop.' -ForegroundColor DarkGray

$uvicornArgs = @('-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', "$Port")
if (-not $NoReload) { $uvicornArgs += '--reload' }

Push-Location $PSScriptRoot
try {
    & $python @uvicornArgs
} finally {
    Pop-Location
}
