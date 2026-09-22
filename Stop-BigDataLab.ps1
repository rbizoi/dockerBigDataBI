[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot
docker compose --profile demo --profile seed --profile logs --profile orchestration --profile elastic stop
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host '[OK] BigData training project stopped.' -ForegroundColor Green
