param(
    [Parameter(Mandatory=$true)][string]$Case,
    [Parameter(Mandatory=$true)][string]$Log
)
$ErrorActionPreference = 'Stop'
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (Test-Path -LiteralPath $bundledPython) {
    & $bundledPython -X utf8 (Join-Path $PSScriptRoot 'compare_trace.py') --case $Case --actual $Log
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (!$pythonCommand) { throw '找不到 Python 3。请安装 Python 3，或使用 Codex 附带的 Python 执行 compare_trace.py。' }
    & $pythonCommand.Source -X utf8 (Join-Path $PSScriptRoot 'compare_trace.py') --case $Case --actual $Log
}
exit $LASTEXITCODE
