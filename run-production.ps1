param(
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 8000,
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 3000,
    [switch]$SkipFetch
)

$ErrorActionPreference = "Stop"
$launcher = Join-Path $PSScriptRoot "run-app.ps1"
$launchParams = @{
    Production   = $true
    ApiPort      = $ApiPort
    FrontendPort = $FrontendPort
}
if ($SkipFetch) {
    $launchParams['SkipFetch'] = $true
}
& $launcher @launchParams
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
