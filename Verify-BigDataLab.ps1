[CmdletBinding()]
param(
    [switch]$UseAirflow,
    [switch]$UseElastic
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot
. (Join-Path $ProjectRoot 'scripts\windows\Common.ps1')

$jupyterPort = '8888'
$envFile = Join-Path $ProjectRoot '.env'
if (Test-Path -LiteralPath $envFile) {
    $portMatch = [regex]::Match((Get-Content -LiteralPath $envFile -Raw), '(?m)^JUPYTER_PORT=(.*)$')
    if ($portMatch.Success -and -not [string]::IsNullOrWhiteSpace($portMatch.Groups[1].Value)) { $jupyterPort = $portMatch.Groups[1].Value.Trim() }
}

try {
    Write-Section 'Functional verification'
    foreach ($svc in @('postgres-source','kafka','objectstore','iceberg-rest','spark-master','spark-worker-1','spark-worker-2','spark-history','spark-jupyter','trino')) {
        $s = Get-ServiceState $svc
        if (-not $s.Exists -or $s.Status -ne 'running' -or -not $s.HasHealthcheck -or $s.Health -ne 'healthy') {
            throw ($svc + ' invalid state: status=' + $s.Status + ' health=' + $s.Health)
        }
        Write-Ok ($svc + ' status=' + $s.Status + ' health=' + $s.Health)
    }
    Wait-Http -Name 'Spark History Server' -Url 'http://127.0.0.1:18083' -TimeoutSeconds 60
    Wait-Http -Name 'JupyterLab' -Url ('http://127.0.0.1:' + $jupyterPort + '/login') -TimeoutSeconds 60 -Service 'spark-jupyter'
    $jupyterRuntime = Invoke-NativeCapture { docker compose exec -T spark-jupyter python3 -c "import os, pwd, jupyterlab, pyspark; from pathlib import Path; user=pwd.getpwuid(os.geteuid()).pw_name; assert user == 'spark', user; probes=[Path('/home/spark/.local/share/jupyter/.write-test'),Path('/opt/spark/notebooks/.write-test')]; [(p.write_text('ok', encoding='utf-8'),p.unlink()) for p in probes]; print('JUPYTER_SPARK_RUNTIME_OK user=' + user)" }
    if ($jupyterRuntime.Code -ne 0 -or $jupyterRuntime.Text -notmatch 'JUPYTER_SPARK_RUNTIME_OK') { throw 'JupyterLab Spark runtime validation failed' }
    Write-Ok 'JupyterLab validated'
    Test-CoreFunctional -IncludeSparkSmoke

    if ($UseAirflow) {
        Wait-Http -Name 'Airflow' -Url 'http://127.0.0.1:8088/api/v2/monitor/health' -TimeoutSeconds 60
        $dags = Invoke-NativeCapture { docker compose --profile orchestration exec -T airflow airflow dags list }
        if ($dags.Code -ne 0 -or $dags.Text -notmatch 'bigdata_training_pipeline' -or $dags.Text -notmatch 'web_logs_training_pipeline') { throw 'Airflow DAG validation failed' }
        Write-Ok 'Airflow validated'
    }
    if ($UseElastic) {
        Wait-Http -Name 'Elasticsearch' -Url 'http://127.0.0.1:9200/_cluster/health' -TimeoutSeconds 60
        Wait-Http -Name 'Kibana' -Url 'http://127.0.0.1:5601/api/status' -TimeoutSeconds 60
        $ls = Get-ServiceState 'logstash'
        if (-not $ls.Exists -or $ls.Status -ne 'running') { throw 'Logstash is not running' }
        Write-Ok 'Elastic Stack validated'
    }
    Write-Host ''
    Write-Host 'VERIFICATION PASSED' -ForegroundColor Green
    exit 0
}
catch {
    Write-Host ('[FAIL] ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
