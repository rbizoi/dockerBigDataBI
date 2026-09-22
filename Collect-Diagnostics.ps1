[CmdletBinding()]
param([string]$Reason = '')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot
$reports = Join-Path $ProjectRoot 'reports'
New-Item -ItemType Directory -Force -Path $reports | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$out = Join-Path $reports ('diagnostics-' + $stamp + '.txt')

('Reason: ' + $Reason) | Out-File -LiteralPath $out -Encoding UTF8
'' | Out-File -LiteralPath $out -Append -Encoding UTF8
'=== docker version ===' | Out-File -LiteralPath $out -Append -Encoding UTF8
docker version 2>&1 | Out-File -LiteralPath $out -Append -Encoding UTF8
'' | Out-File -LiteralPath $out -Append -Encoding UTF8
'=== compose ps ===' | Out-File -LiteralPath $out -Append -Encoding UTF8
docker compose --profile demo --profile seed --profile logs --profile orchestration --profile elastic ps -a 2>&1 | Out-File -LiteralPath $out -Append -Encoding UTF8
'' | Out-File -LiteralPath $out -Append -Encoding UTF8
'=== inspect states ===' | Out-File -LiteralPath $out -Append -Encoding UTF8
foreach ($svc in @('postgres-source','kafka','objectstore','iceberg-rest','spark-master','spark-worker-1','spark-worker-2','spark-history','spark-jupyter','trino','airflow-db','airflow','elasticsearch','kibana','logstash')) {
    $id = docker compose --profile orchestration --profile elastic ps -a -q $svc 2>$null
    if ($id) {
        ('--- ' + $svc + ' ---') | Out-File -LiteralPath $out -Append -Encoding UTF8
        docker inspect --format '{{json .State}}' $id 2>&1 | Out-File -LiteralPath $out -Append -Encoding UTF8
    }
}
'' | Out-File -LiteralPath $out -Append -Encoding UTF8
'=== compose logs ===' | Out-File -LiteralPath $out -Append -Encoding UTF8
docker compose --profile demo --profile seed --profile logs --profile orchestration --profile elastic logs --no-color --tail 250 2>&1 | Out-File -LiteralPath $out -Append -Encoding UTF8

'' | Out-File -LiteralPath $out -Append -Encoding UTF8
'=== recent Spark driver logs ===' | Out-File -LiteralPath $out -Append -Encoding UTF8
Get-ChildItem -LiteralPath $reports -Filter 'spark-job-*.log' -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 5 |
    ForEach-Object {
        ('--- ' + $_.Name + ' ---') | Out-File -LiteralPath $out -Append -Encoding UTF8
        Get-Content -LiteralPath $_.FullName -Tail 300 -ErrorAction SilentlyContinue |
            Out-File -LiteralPath $out -Append -Encoding UTF8
    }

Write-Host ('[WARN] Diagnostics: ' + $out) -ForegroundColor Yellow
$out
