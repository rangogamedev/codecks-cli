param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$tmpRoot = Join-Path $repoRoot ".tmp"
$runSuffix = [DateTime]::UtcNow.ToString("yyyyMMddHHmmss") + "-" + $PID
$pytestBaseTemp = Join-Path $tmpRoot ("pytest-" + $runSuffix)

if (-not (Test-Path -Path $tmpRoot)) {
    New-Item -ItemType Directory -Path $tmpRoot | Out-Null
}

$env:TEMP = $tmpRoot
$env:TMP = $tmpRoot

$pythonExe = "py"
& py -V *> $null
if ($LASTEXITCODE -ne 0) {
    $fallback = $env:CODECKS_PYTHON_PATH
    if (-not $fallback) {
        $fallback = "C:\Users\USER\AppData\Local\Python\bin\python.exe"
    }
    if (-not (Test-Path -Path $fallback)) {
        throw "Python launcher 'py' is not configured and fallback interpreter was not found. Set CODECKS_PYTHON_PATH to a valid python executable."
    }
    $pythonExe = $fallback
}

$defaultArgs = @("-m", "pytest", "tests/", "-v", "--basetemp", $pytestBaseTemp)
if ($PytestArgs -and $PytestArgs.Count -gt 0) {
    $defaultArgs += $PytestArgs
}

& $pythonExe @defaultArgs
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    exit $exitCode
}
