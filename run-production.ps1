param(
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 8000,
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 3000
)

$ErrorActionPreference = "Stop"
$launcher = Join-Path $PSScriptRoot "run-app.ps1"
& $launcher -Production -ApiPort $ApiPort -FrontendPort $FrontendPort
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
