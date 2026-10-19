[CmdletBinding()]
param(
    [string]$DruidUrl = "http://localhost:8889",
    [string]$SpecPath = (Join-Path $PSScriptRoot "ingestion/sales-fact.json"),
    [int]$TimeoutMinutes = 20
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $SpecPath)) {
    throw "Druid ingestion spec not found: $SpecPath"
}

$task = Invoke-RestMethod -Method Post `
    -Uri "$DruidUrl/druid/indexer/v1/task" `
    -ContentType "application/json" `
    -InFile $SpecPath

$taskId = if ($task -is [string]) { $task.Trim('"') } else { $task.task }
if ([string]::IsNullOrWhiteSpace($taskId)) {
    throw "Druid did not return an ingestion task ID."
}

Write-Host "Druid ingestion task: $taskId"
$deadline = (Get-Date).AddMinutes($TimeoutMinutes)

do {
    Start-Sleep -Seconds 5
    $result = Invoke-RestMethod -Method Get -Uri "$DruidUrl/druid/indexer/v1/task/$taskId/status"
    $state = $result.status.status
    Write-Host "Task status: $state"

    if ($state -eq "SUCCESS") {
        Write-Host "Datasource sales_fact_denormalized is ready."
        exit 0
    }
    if ($state -eq "FAILED") {
        $report = Invoke-RestMethod -Method Get -Uri "$DruidUrl/druid/indexer/v1/task/$taskId/reports"
        Write-Host ($report | ConvertTo-Json -Depth 20)
        throw "Druid ingestion task failed: $taskId"
    }
} while ((Get-Date) -lt $deadline)

throw "Timed out waiting for Druid task $taskId after $TimeoutMinutes minutes."
