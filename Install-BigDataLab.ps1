[CmdletBinding()]
param(
    [switch]$Reset,
    [switch]$SkipPull,
    [switch]$SkipBuild,
    [switch]$RunTrainingProject,
    [switch]$RunProjectWithAirflow,
    [switch]$UseAirflow,
    [switch]$UseElastic,
    [switch]$UseDemo,
    [switch]$Full
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot
. (Join-Path $ProjectRoot 'scripts\windows\Common.ps1')

if ($RunProjectWithAirflow) { $UseAirflow = $true; $RunTrainingProject = $true }
if ($Full) { $UseAirflow = $true; $UseElastic = $true; $UseDemo = $true; $RunTrainingProject = $true; $RunProjectWithAirflow = $true }

$ReportsDir = Join-Path $ProjectRoot 'reports'
New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$InstallLog = Join-Path $ReportsDir ('install-' + $Stamp + '.log')

function Log-Line { param([string]$Text) Add-Content -LiteralPath $InstallLog -Value $Text -Encoding UTF8 }

try {
    Write-Section '1. Preflight Windows / Docker'
    Test-ActivePowerShellSyntax -Root $ProjectRoot

    $docker = Assert-NativeSuccess -Description 'Docker CLI' -Command { docker version --format '{{.Client.Version}}|{{.Server.Version}}' } -Quiet
    Write-Ok ('Docker client/server: ' + $docker.Text.Trim())

    $composeVersion = Assert-NativeSuccess -Description 'Docker Compose' -Command { docker compose version --short } -Quiet
    Write-Ok ('Docker Compose ' + $composeVersion.Text.Trim())

    $os = Assert-NativeSuccess -Description 'Linux containers check' -Command { docker info --format '{{.OSType}}' } -Quiet
    if ($os.Text.Trim() -ne 'linux') { throw ('Docker must use Linux containers, got: ' + $os.Text.Trim()) }
    Write-Ok 'Docker Linux containers'
    Write-Ok 'Host memory check disabled by design'

    $envFile = Join-Path $ProjectRoot '.env'
    if (-not (Test-Path -LiteralPath $envFile)) {
        Copy-Item -LiteralPath (Join-Path $ProjectRoot '.env.example') -Destination $envFile
        Write-Ok '.env created from .env.example'
    }

    $envText = Get-Content -LiteralPath $envFile -Raw
    $jupyterTokenMatch = [regex]::Match($envText, '(?m)^JUPYTER_TOKEN=(.*)$')
    $jupyterToken = if ($jupyterTokenMatch.Success) { $jupyterTokenMatch.Groups[1].Value.Trim() } else { '' }
    if ([string]::IsNullOrWhiteSpace($jupyterToken) -or $jupyterToken -eq 'CHANGE_ME') {
        $jupyterToken = [guid]::NewGuid().ToString('N')
        if ($jupyterTokenMatch.Success) {
            $envText = [regex]::Replace($envText, '(?m)^JUPYTER_TOKEN=.*$', ('JUPYTER_TOKEN=' + $jupyterToken))
        }
        else {
            $envText = $envText.TrimEnd() + [Environment]::NewLine + 'JUPYTER_TOKEN=' + $jupyterToken + [Environment]::NewLine
        }
        Set-Content -LiteralPath $envFile -Value $envText -Encoding UTF8
        Write-Ok 'JupyterLab access token generated in .env'
    }
    $jupyterPortMatch = [regex]::Match($envText, '(?m)^JUPYTER_PORT=(.*)$')
    $jupyterPort = if ($jupyterPortMatch.Success -and -not [string]::IsNullOrWhiteSpace($jupyterPortMatch.Groups[1].Value)) { $jupyterPortMatch.Groups[1].Value.Trim() } else { '8888' }

    [void](Assert-NativeSuccess -Description 'docker compose config' -Command { docker compose config --quiet } -Quiet)

    if ($Reset) {
        Write-Section '2. Reset project volumes and containers'
        $r = Invoke-NativeCapture { docker compose --profile demo --profile seed --profile logs --profile orchestration --profile elastic down -v --remove-orphans }
        if (-not [string]::IsNullOrWhiteSpace($r.Text)) { Write-Host $r.Text }
        if ($r.Code -ne 0) { throw ('Reset failed (exit=' + $r.Code + ')') }
        Write-Ok 'Project reset complete'
    }

    Write-Section '3. Images'
    if (-not $SkipPull) {
        [void](Assert-NativeSuccess -Description 'Pull core images' -Command { docker compose pull postgres-source kafka objectstore iceberg-rest trino } )
        if ($UseAirflow) { [void](Assert-NativeSuccess -Description 'Pull Airflow DB base image' -Command { docker compose --profile orchestration pull airflow-db } ) }
        if ($UseElastic) { [void](Assert-NativeSuccess -Description 'Pull Elastic Stack images' -Command { docker compose --profile elastic pull elasticsearch kibana logstash } ) }
    }
    if (-not $SkipBuild) {
        [void](Assert-NativeSuccess -Description 'Build S3 initializer and Spark runtime' -Command { docker compose build objectstore-init spark-master } )
        if ($RunTrainingProject) {
            [void](Assert-NativeSuccess -Description 'Build training producers' -Command { docker compose --profile seed --profile logs build file-producer postgres-producer web-log-producer } )
        }
        if ($UseDemo) {
            [void](Assert-NativeSuccess -Description 'Build demo services' -Command { docker compose --profile demo build mock-opendata api-producer } )
        }
        if ($UseAirflow) {
            [void](Assert-NativeSuccess -Description 'Build Airflow image' -Command { docker compose --profile orchestration build airflow } )
        }
    }

    Write-Section '4. Foundation: PostgreSQL / Kafka / RustFS'
    [void](Assert-NativeSuccess -Description 'Start foundation' -Command { docker compose up -d postgres-source kafka objectstore })
    Wait-ServiceHealthy 'postgres-source' 180
    Wait-ServiceHealthy 'kafka' 180
    Wait-ServiceHealthy 'objectstore' 180

    Write-Section '5. Idempotent bootstraps'
    [void](Assert-NativeSuccess -Description 'Start bootstrap services' -Command { docker compose up -d --force-recreate postgres-bootstrap kafka-init objectstore-init iceberg-catalog-permissions })
    Wait-ServiceCompleted 'postgres-bootstrap' 180
    Wait-ServiceCompleted 'kafka-init' 180
    Wait-ServiceCompleted 'objectstore-init' 180
    Wait-ServiceCompleted 'iceberg-catalog-permissions' 120

    Write-Section '6. Iceberg REST Catalog'
    [void](Assert-NativeSuccess -Description 'Start Iceberg REST' -Command { docker compose up -d iceberg-rest })
    Wait-ServiceHealthy 'iceberg-rest' 180
    Wait-Http -Name 'Iceberg REST' -Url 'http://127.0.0.1:8181/v1/config' -TimeoutSeconds 120

    Write-Section '7. Spark Standalone cluster'
    [void](Assert-NativeSuccess -Description 'Start Spark Master' -Command { docker compose up -d spark-master })
    Wait-ServiceHealthy 'spark-master' 180
    [void](Assert-NativeSuccess -Description 'Start Spark Workers, History Server and JupyterLab' -Command { docker compose up -d spark-worker-1 spark-worker-2 spark-history spark-jupyter })
    Wait-ServiceHealthy 'spark-worker-1' 180
    Wait-ServiceHealthy 'spark-worker-2' 180
    Wait-ServiceHealthy 'spark-history' 240
    Wait-ServiceHealthy 'spark-jupyter' 240
    Wait-Http -Name 'Spark History Server' -Url 'http://127.0.0.1:18083' -TimeoutSeconds 120
    Wait-Http -Name 'JupyterLab' -Url ('http://127.0.0.1:' + $jupyterPort + '/login') -TimeoutSeconds 120 -Service 'spark-jupyter'

    $jupyterRuntime = Invoke-NativeCapture {
        docker compose exec -T spark-jupyter python3 -c "import os, pwd, jupyterlab, pyspark; from pathlib import Path; user=pwd.getpwuid(os.geteuid()).pw_name; assert user == 'spark', user; probes=[Path('/home/spark/.local/share/jupyter/.write-test'),Path('/opt/spark/notebooks/.write-test')]; [(p.write_text('ok', encoding='utf-8'),p.unlink()) for p in probes]; print('JUPYTER_SPARK_RUNTIME_OK user=' + user + ' jupyterlab=' + jupyterlab.__version__ + ' pyspark=' + pyspark.__version__)"
    }
    if ($jupyterRuntime.Code -ne 0 -or $jupyterRuntime.Text -notmatch 'JUPYTER_SPARK_RUNTIME_OK') {
        throw ('JupyterLab Spark runtime validation failed: ' + $jupyterRuntime.Text)
    }
    Write-Ok 'JupyterLab user, write permissions and PySpark runtime validated'

    Write-Section '8. Spark runtime smoke: S3 + Parquet + Delta + Iceberg'
    [void](Invoke-SparkJob -JobName '00_runtime_smoke.py' -RequiredMarkers @('SPARK_IMPORTED_CONFIG_OK','SMOKE_PARQUET_COUNT=3','SMOKE_DELTA_COUNT=3','SMOKE_ICEBERG_COUNT=3','SMOKE_RUNTIME_OK'))

    $historyApplicationFound = $false
    for ($i = 1; $i -le 45; $i++) {
        Start-Sleep -Seconds 2
        try {
            $historyApplications = Invoke-RestMethod -Uri 'http://127.0.0.1:18083/api/v1/applications?limit=1' -Method Get -TimeoutSec 5
            if (@($historyApplications).Count -ge 1) {
                $historyApplicationFound = $true
                break
            }
        }
        catch { }
    }
    if (-not $historyApplicationFound) { throw 'Spark History Server did not discover the S3 event log produced by the runtime smoke test.' }
    Write-Ok 'Spark S3 event log visible in History Server'

    Write-Section '9. Trino SQL federation'
    [void](Assert-NativeSuccess -Description 'Start Trino' -Command { docker compose up -d trino })
    Wait-ServiceHealthy 'trino' 240
    Test-CoreFunctional

    if ($RunTrainingProject) {
        Write-Section '10. Training project: sources -> Kafka -> Lakehouse'
        [void](Assert-NativeSuccess -Description 'Run file producer' -Command { docker compose --profile seed run --rm file-producer })
        [void](Assert-NativeSuccess -Description 'Run PostgreSQL producer' -Command { docker compose --profile seed run --rm postgres-producer })

        foreach ($job in @('01_batch_to_parquet.py','02_kafka_to_delta.py','03_build_iceberg_gold.py','04_ml_kmeans.py','05_kafka_aux_to_parquet.py')) {
            [void](Invoke-SparkJob -JobName $job)
        }

        [void](Assert-NativeSuccess -Description 'Publish 820 web/application logs' -Command { docker compose --profile logs run --rm web-log-producer })
        [void](Invoke-SparkJob -JobName '06_kafka_web_logs_to_delta.py' -RequiredMarkers @('[QUALITY] web logs valid=820 invalid=0'))
        [void](Invoke-SparkJob -JobName '07_delta_web_logs_to_iceberg.py')
        [void](Invoke-SparkJob -JobName '08_web_logs_ml_kmeans.py' -RequiredMarkers @('WEB_ML_RUNTIME_OK','[OK] iceberg.ml.web_path_clusters created.'))
        Write-Ok 'Training project completed'
    }

    if ($UseDemo) {
        Write-Section '11. OpenData demo profile'
        [void](Assert-NativeSuccess -Description 'Start mock OpenData and API producer' -Command { docker compose --profile demo up -d mock-opendata api-producer })
        Wait-ServiceHealthy 'mock-opendata' 120
        $apiState = Get-ServiceState 'api-producer'
        if (-not $apiState.Exists -or $apiState.Status -ne 'running') { throw 'api-producer is not running' }
        Write-Ok 'OpenData demo profile running'
    }

    if ($UseAirflow) {
        Write-Section '12. Airflow orchestration'
        [void](Assert-NativeSuccess -Description 'Start Airflow' -Command { docker compose --profile orchestration up -d airflow-db airflow })
        Wait-ServiceHealthy 'airflow-db' 180
        Wait-ServiceHealthy 'airflow' 360
        Wait-Http -Name 'Airflow' -Url 'http://127.0.0.1:8088/api/v2/monitor/health' -TimeoutSeconds 240
        $dags = Invoke-NativeCapture { docker compose --profile orchestration exec -T airflow airflow dags list }
        if ($dags.Code -ne 0 -or $dags.Text -notmatch 'bigdata_training_pipeline' -or $dags.Text -notmatch 'web_logs_training_pipeline') {
            throw ('Airflow DAG validation failed: ' + $dags.Text)
        }
        Write-Ok 'Airflow DAGs present'

        Test-AirflowSparkPythonParity

        $afMl = Invoke-NativeCapture {
            docker compose --profile orchestration exec -T airflow python3 -c "import sys, numpy as np, pyspark; from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator; from pyspark.ml.clustering import KMeans; print('AIRFLOW_ML_RUNTIME_OK python=' + f'{sys.version_info.major}.{sys.version_info.minor}' + ' pyspark=' + pyspark.__version__ + ' numpy=' + np.__version__)"
        }
        if ($afMl.Code -ne 0 -or $afMl.Text -notmatch 'AIRFLOW_ML_RUNTIME_OK') { throw ('Airflow ML runtime validation failed: ' + $afMl.Text) }
        Write-Ok 'Airflow Python/PySpark/ML runtime validated'

        $afSmoke = Invoke-NativeCapture { docker compose --profile orchestration exec -T airflow spark-submit /opt/spark/jobs/00_runtime_smoke.py }
        if ($afSmoke.Code -ne 0 -or $afSmoke.Text -notmatch 'PYTHON_RUNTIME_PARITY_OK' -or $afSmoke.Text -notmatch 'SMOKE_RUNTIME_OK') { throw ('Airflow -> Spark smoke failed: ' + $afSmoke.Text) }
        Write-Ok 'Airflow -> Spark distributed Python/S3/Delta/Iceberg validated'
    }

    if ($UseElastic) {
        Write-Section '13. Elastic Stack and Kafka -> Logstash -> Elasticsearch'
        [void](Assert-NativeSuccess -Description 'Start Elastic Stack' -Command { docker compose --profile elastic up -d elasticsearch kibana logstash })
        Wait-ServiceHealthy 'elasticsearch' 360
        Wait-Http -Name 'Elasticsearch' -Url 'http://127.0.0.1:9200/_cluster/health' -TimeoutSeconds 240
        Wait-Http -Name 'Kibana' -Url 'http://127.0.0.1:5601/api/status' -TimeoutSeconds 360 -Service 'kibana'
        $ls = Get-ServiceState 'logstash'
        if (-not $ls.Exists -or $ls.Status -ne 'running') { throw 'Logstash is not running' }

        $validationId = [guid]::NewGuid().ToString()
        $json = '{"validation_id":"' + $validationId + '","message":"kafka-logstash-elasticsearch-validation"}'
        [void](Assert-NativeSuccess -Description 'Publish Elastic validation event' -Command {
            $json | docker compose exec -T kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server kafka:19092 --topic application.logs
        } -Quiet)

        $searchBody = @{
            query = @{
                term = @{
                    'validation_id.keyword' = $validationId
                }
            }
        } | ConvertTo-Json -Depth 5 -Compress

        $found = $false
        for ($i = 1; $i -le 45; $i++) {
            Start-Sleep -Seconds 2
            try {
                $uri = 'http://127.0.0.1:9200/training-logs-*/_search'
                $response = Invoke-RestMethod -Uri $uri -Method Post -ContentType 'application/json' -Body $searchBody -TimeoutSec 5
                if ($null -ne $response.hits -and [int64]$response.hits.total.value -ge 1) { $found = $true; break }
            }
            catch { }
        }
        if (-not $found) { throw ('Kafka -> Logstash -> Elasticsearch event not found: ' + $validationId) }
        Write-Ok 'Kafka -> Logstash -> Elasticsearch validated'
    }

    Write-Section '14. Final verification'
    Test-CoreFunctional
    Write-Host ''
    Write-Host 'INSTALLATION VALIDATED SUCCESSFULLY' -ForegroundColor Green
    Write-Host 'JupyterLab: run OPEN_JUPYTER.cmd' -ForegroundColor Cyan
    Log-Line 'INSTALLATION VALIDATED SUCCESSFULLY'
    exit 0
}
catch {
    Write-Host ''
    Write-Host ('[FAIL] ' + $_.Exception.Message) -ForegroundColor Red
    Log-Line ('[FAIL] ' + $_.Exception.ToString())
    try {
        & (Join-Path $ProjectRoot 'Collect-Diagnostics.ps1') -Reason $_.Exception.Message | Out-Null
    }
    catch { Write-Warn ('Diagnostics collection also failed: ' + $_.Exception.Message) }
    Write-Warn ('See reports directory: ' + $ReportsDir)
    exit 1
}
