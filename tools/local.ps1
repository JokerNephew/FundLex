param(
    [ValidateSet('api','worker','test')][string]$Mode = 'api',
    [int]$Port = 8000,
    [string]$Model,
    [string]$RequestOptionsJson
)
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $workspaceRoot
$pythonPath = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create the virtual environment with uv sync --extra test first.' }
if ($Mode -eq 'worker') {
    foreach ($name in @('LLM_PROVIDER','LLM_BASE_URL','LLM_MODEL','LLM_API_KEY')) {
        if (-not [Environment]::GetEnvironmentVariable($name,'Process')) {
            [Environment]::SetEnvironmentVariable($name,[Environment]::GetEnvironmentVariable($name,'User'),'Process')
        }
    }
    if ($PSBoundParameters.ContainsKey('Model')) { $env:LLM_MODEL = $Model }
    if ($PSBoundParameters.ContainsKey('RequestOptionsJson')) { $env:FUNDLEX_MODEL_REQUEST_OPTIONS_JSON = $RequestOptionsJson }
    foreach ($name in @('LLM_PROVIDER','LLM_BASE_URL','LLM_MODEL','LLM_API_KEY')) {
        if (-not [Environment]::GetEnvironmentVariable($name,'Process')) { throw "Required model variable is absent: $name" }
    }
    & $pythonPath -X utf8 -m fundlex.jobs
} elseif ($Mode -eq 'test') {
    & $pythonPath -X utf8 -m pytest -q -p no:cacheprovider
} else {
    & $pythonPath -X utf8 -m uvicorn fundlex.api:app --host 127.0.0.1 --port $Port
}
exit $LASTEXITCODE
