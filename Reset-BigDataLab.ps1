[CmdletBinding()]
param([switch]$Force)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot
if (-not $Force) {
    $answer = Read-Host 'This deletes only bigdata-training containers and volumes. Type RESET'
    if ($answer -ne 'RESET') { Write-Host 'Cancelled.'; exit 2 }
}
docker compose --profile demo --profile seed --profile logs --profile orchestration --profile elastic down -v --remove-orphans
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host '[OK] BigData training project reset.' -ForegroundColor Green
