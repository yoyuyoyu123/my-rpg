# Local environment setup used by the graphical launcher.
param()

$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$requirements = Join-Path $PSScriptRoot 'requirements.txt'

function Test-LocalPython {
    if (-not (Test-Path -LiteralPath $python)) { return $false }
    try {
        & $python --version | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

if (-not (Test-LocalPython)) {
    if (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.venv')) {
        throw 'The existing .venv is invalid. Rename or remove backend/.venv, then run Install / Repair again.'
    }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        & $py.Source -3.11 -m venv (Join-Path $PSScriptRoot '.venv')
        if ($LASTEXITCODE -ne 0) {
            & $py.Source -m venv (Join-Path $PSScriptRoot '.venv')
        }
    } else {
        $systemPython = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $systemPython) { throw 'Python is not installed. Install Python 3.11 or newer first.' }
        & $systemPython.Source -m venv (Join-Path $PSScriptRoot '.venv')
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-LocalPython)) {
        throw 'Could not create the local Python environment.'
    }
}

& $python -m pip install --disable-pip-version-check -r $requirements
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $python -c "import fastapi, pydantic, sqlalchemy, aiosqlite, uvicorn; print('setup complete')"
if ($LASTEXITCODE -ne 0) { throw 'Dependency verification failed.' }
