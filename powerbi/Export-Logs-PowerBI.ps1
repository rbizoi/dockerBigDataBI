[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $ProjectRoot
New-Item -ItemType Directory -Force -Path 'powerbi\output' | Out-Null

$queries = @{
  'web_traffic_hourly.csv' = 'SELECT event_hour, requests, unique_clients, errors_4xx_5xx, errors_5xx, avg_response_ms, p95_response_ms, bytes_sent, error_rate_pct, refreshed_at FROM iceberg.logs.traffic_hourly ORDER BY event_hour';
  'web_path_daily.csv' = 'SELECT event_date, path, method, requests, errors, error_rate_pct, avg_response_ms, p95_response_ms, bytes_sent FROM iceberg.logs.path_daily ORDER BY event_date, requests DESC';
  'application_daily.csv' = 'SELECT event_date, app_service, app_level, events FROM iceberg.logs.application_daily ORDER BY event_date, app_service, app_level';
  'web_path_clusters.csv' = 'SELECT event_date, path, method, requests, errors, error_rate_pct, avg_response_ms, p95_response_ms, bytes_sent, behavior_cluster, model_refreshed_at FROM iceberg.ml.web_path_clusters ORDER BY behavior_cluster, requests DESC'
}

foreach ($entry in $queries.GetEnumerator()) {
    $stderrPath = Join-Path $env:TEMP ('trino-export-' + [guid]::NewGuid().ToString() + '.err')
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $content = @(& docker compose exec -T trino trino --server http://localhost:8080 --user training --output-format CSV_HEADER --execute $entry.Value 2>$stderrPath)
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }
    if ($code -ne 0) {
        $stderrText = ''
        if (Test-Path -LiteralPath $stderrPath) { $stderrText = Get-Content -LiteralPath $stderrPath -Raw }
        throw ('Trino export failed: ' + $entry.Key + [Environment]::NewLine + $stderrText)
    }
    $content | Set-Content -Encoding UTF8 (Join-Path 'powerbi\output' $entry.Key)
    if (Test-Path -LiteralPath $stderrPath) { Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue }
    Write-Host ('[OK] ' + $entry.Key) -ForegroundColor Green
}
