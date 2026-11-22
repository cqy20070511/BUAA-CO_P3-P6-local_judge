$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$P6Python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python39\python.exe'
if (Test-Path -LiteralPath $P6Python) {
    & $P6Python -u server.py
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 -u server.py
} else {
    python -u server.py
}
