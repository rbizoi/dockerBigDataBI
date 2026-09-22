Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Section {
    param([string]$Text)
    Write-Host ''
    Write-Host ('=' * 78) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ('=' * 78) -ForegroundColor DarkCyan
}

function Write-Ok { param([string]$Text) Write-Host ('[OK] ' + $Text) -ForegroundColor Green }
function Write-Warn { param([string]$Text) Write-Host ('[WARN] ' + $Text) -ForegroundColor Yellow }
function Write-Step { param([string]$Text) Write-Host ('[' + (Get-Date -Format 'HH:mm:ss') + '] ' + $Text) -ForegroundColor Cyan }

function Invoke-NativeCapture {
    param([scriptblock]$Command)
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $lines = @(& $Command 2>&1)
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }

    $text = (($lines | ForEach-Object { [string]$_ }) -join [Environment]::NewLine)
    [pscustomobject]@{ Code = $code; Text = $text; Lines = $lines }
}

function Assert-NativeSuccess {
    param(
        [string]$Description,
        [scriptblock]$Command,
        [switch]$Quiet
    )
    Write-Step $Description
    $result = Invoke-NativeCapture $Command
    if (-not $Quiet -and -not [string]::IsNullOrWhiteSpace($result.Text)) {
        Write-Host $result.Text
    }
    if ($result.Code -ne 0) {
        throw ($Description + ' failed (exit=' + $result.Code + ').' + [Environment]::NewLine + $result.Text)
    }
    return $result
}

function Get-ComposeContainerId {
    param([string]$Service)
    $result = Invoke-NativeCapture { docker compose ps -a -q $Service }
    if ($result.Code -ne 0) { return $null }
    foreach ($line in @($result.Text -split "`r?`n")) {
        $candidate = $line.Trim()
        if ($candidate -match '^[0-9a-f]{12,64}$') { return $candidate }
    }
    return $null
}

function Get-OptionalPropertyValue {
    param(
        [Parameter(Mandatory=$false)]$Object,
        [Parameter(Mandatory=$true)][string]$Name,
        $Default = $null
    )

    if ($null -eq $Object) { return $Default }

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $Default }

    return $property.Value
}

function Get-ServiceState {
    param([string]$Service)

    $id = Get-ComposeContainerId $Service
    if ([string]::IsNullOrWhiteSpace($id)) {
        return [pscustomobject]@{
            Service=$Service
            Exists=$false
            Status='missing'
            Health='none'
            HasHealthcheck=$false
            ExitCode=-1
            OOMKilled=$false
            Error=''
        }
    }

    $result = Invoke-NativeCapture { docker inspect --format '{{json .State}}' $id }
    if ($result.Code -ne 0 -or [string]::IsNullOrWhiteSpace($result.Text)) {
        return [pscustomobject]@{
            Service=$Service
            Exists=$true
            Status='inspect-error'
            Health='none'
            HasHealthcheck=$false
            ExitCode=-1
            OOMKilled=$false
            Error=$result.Text
        }
    }

    try {
        $state = $result.Text | ConvertFrom-Json
    }
    catch {
        return [pscustomobject]@{
            Service=$Service
            Exists=$true
            Status='inspect-json-error'
            Health='none'
            HasHealthcheck=$false
            ExitCode=-1
            OOMKilled=$false
            Error=$_.Exception.Message
        }
    }

    $health = 'none'
    $hasHealthcheck = $false
    $healthObject = Get-OptionalPropertyValue -Object $state -Name 'Health' -Default $null
    if ($null -ne $healthObject) {
        $hasHealthcheck = $true
        $healthStatus = Get-OptionalPropertyValue -Object $healthObject -Name 'Status' -Default 'unknown'
        if (-not [string]::IsNullOrWhiteSpace([string]$healthStatus)) {
            $health = [string]$healthStatus
        }
    }

    $status = [string](Get-OptionalPropertyValue -Object $state -Name 'Status' -Default 'unknown')
    $exitCodeRaw = Get-OptionalPropertyValue -Object $state -Name 'ExitCode' -Default -1
    $oomKilledRaw = Get-OptionalPropertyValue -Object $state -Name 'OOMKilled' -Default $false
    $errorText = [string](Get-OptionalPropertyValue -Object $state -Name 'Error' -Default '')

    return [pscustomobject]@{
        Service=$Service
        Exists=$true
        Status=$status
        Health=$health
        HasHealthcheck=$hasHealthcheck
        ExitCode=[int]$exitCodeRaw
        OOMKilled=[bool]$oomKilledRaw
        Error=$errorText
    }
}

function Wait-ServiceHealthy {
    param(
        [string]$Service,
        [int]$TimeoutSeconds = 240
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $s = Get-ServiceState $Service
        if ($s.Exists -and $s.Status -eq 'running' -and $s.Health -eq 'healthy') {
            Write-Ok ($Service + ' running / healthy')
            return
        }
        if ($s.Exists -and $s.Status -eq 'running' -and -not $s.HasHealthcheck) {
            throw ($Service + ' is running but has no Docker healthcheck; Wait-ServiceHealthy requires an explicit healthcheck.')
        }
        if ($s.Exists -and $s.Status -eq 'exited') {
            throw ($Service + ' exited before becoming healthy (exit=' + $s.ExitCode + ', oom=' + $s.OOMKilled + ').')
        }
        Start-Sleep -Seconds 2
    }
    $last = Get-ServiceState $Service
    throw ($Service + ' did not become healthy in ' + $TimeoutSeconds + 's (status=' + $last.Status + ', health=' + $last.Health + ').')
}

function Wait-ServiceCompleted {
    param(
        [string]$Service,
        [int]$TimeoutSeconds = 180
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $s = Get-ServiceState $Service
        if ($s.Exists -and $s.Status -eq 'exited') {
            if ($s.ExitCode -eq 0) {
                Write-Ok ($Service + ' completed successfully')
                return
            }
            throw ($Service + ' failed (exit=' + $s.ExitCode + ', oom=' + $s.OOMKilled + ', error=' + $s.Error + ').')
        }
        Start-Sleep -Seconds 2
    }
    $last = Get-ServiceState $Service
    throw ($Service + ' did not complete in ' + $TimeoutSeconds + 's (status=' + $last.Status + ').')
}

function Wait-Http {
    param(
        [string]$Name,
        [string]$Url,
        [int]$TimeoutSeconds = 180,
        [string]$Service = ''
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $nextServiceCheck = Get-Date
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                Write-Ok ($Name + ' HTTP ' + $response.StatusCode)
                return
            }
        }
        catch { }

        if (-not [string]::IsNullOrWhiteSpace($Service) -and (Get-Date) -ge $nextServiceCheck) {
            $state = Get-ServiceState $Service
            if (-not $state.Exists) {
                throw ($Name + ' container is missing while waiting for ' + $Url)
            }
            if ($state.Status -eq 'exited' -or $state.Status -eq 'dead') {
                throw ($Name + ' container stopped (status=' + $state.Status + ', exit=' + $state.ExitCode + ', oom=' + $state.OOMKilled + ').')
            }

            $recentLogs = Invoke-NativeCapture { docker compose logs --no-color --tail 120 $Service }
            if ($recentLogs.Text -match 'JavaScript heap out of memory|Ineffective mark-compacts near heap limit') {
                throw ($Name + ' stopped responding because its Node.js heap is exhausted. Recent container logs:' + [Environment]::NewLine + $recentLogs.Text)
            }
            $nextServiceCheck = (Get-Date).AddSeconds(10)
        }
        Start-Sleep -Seconds 2
    }
    if (-not [string]::IsNullOrWhiteSpace($Service)) {
        $last = Get-ServiceState $Service
        throw ($Name + ' HTTP endpoint not ready: ' + $Url + ' (container status=' + $last.Status + ', health=' + $last.Health + ', exit=' + $last.ExitCode + ', oom=' + $last.OOMKilled + ').')
    }
    throw ($Name + ' HTTP endpoint not ready: ' + $Url)
}

function Test-ActivePowerShellSyntax {
    param([string]$Root)
    $errorsFound = New-Object System.Collections.Generic.List[string]
    Get-ChildItem -LiteralPath $Root -Recurse -File -Filter '*.ps1' | ForEach-Object {
        $tokens = $null
        $parseErrors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$parseErrors)
        foreach ($parseError in @($parseErrors)) {
            $errorsFound.Add(('{0}:{1}:{2} {3}' -f $_.FullName, $parseError.Extent.StartLineNumber, $parseError.Extent.StartColumnNumber, $parseError.Message))
        }
    }
    if ($errorsFound.Count -gt 0) {
        throw ('PowerShell syntax errors:' + [Environment]::NewLine + ($errorsFound -join [Environment]::NewLine))
    }
    Write-Ok ('PowerShell syntax valid (' + ((Get-ChildItem -LiteralPath $Root -Recurse -File -Filter '*.ps1').Count) + ' scripts)')
}

function Invoke-SparkJob {
    param(
        [string]$JobName,
        [string[]]$RequiredMarkers = @()
    )

    Write-Step ('spark-submit ' + $JobName)
    $jobPath = '/opt/spark/jobs/' + $JobName

    $reportsDir = Join-Path $script:ProjectRoot 'reports'
    New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null

    $safeName = [System.IO.Path]::GetFileNameWithoutExtension($JobName) -replace '[^A-Za-z0-9_.-]', '_'
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $jobLog = Join-Path $reportsDir ('spark-job-' + $stamp + '-' + $safeName + '.log')

    $result = Invoke-NativeCapture {
        docker compose exec -T spark-master /opt/spark/bin/spark-submit $jobPath
    }

    @(
        'JOB=' + $JobName
        'EXIT_CODE=' + $result.Code
        ''
        $result.Text
    ) | Out-File -LiteralPath $jobLog -Encoding UTF8

    if (-not [string]::IsNullOrWhiteSpace($result.Text)) {
        Write-Host $result.Text
    }

    if ($result.Code -ne 0) {
        throw (
            'Spark job failed: ' + $JobName +
            ' (exit=' + $result.Code + '). Full driver log: ' + $jobLog
        )
    }

    foreach ($marker in $RequiredMarkers) {
        if ($result.Text -notmatch [regex]::Escape($marker)) {
            throw (
                'Spark job ' + $JobName +
                ' missing marker: ' + $marker +
                '. Full driver log: ' + $jobLog
            )
        }
    }

    Write-Ok ('Spark job validated: ' + $JobName)
    return $result
}

function Invoke-TrinoSql {
    param([string]$Sql)
    $result = Invoke-NativeCapture { docker compose exec -T trino trino --server http://localhost:8080 --user training --output-format TSV --execute $Sql }
    return $result
}

function Assert-OneShotSucceeded {
    param(
        [Parameter(Mandatory=$true)][string]$Service,
        [Parameter(Mandatory=$true)][string]$Description
    )

    $state = Get-ServiceState $Service
    if (-not $state.Exists) {
        throw ($Description + ' container is missing: ' + $Service)
    }
    if ($state.Status -ne 'exited' -or $state.ExitCode -ne 0) {
        throw ($Description + ' failed: service=' + $Service +
            ' status=' + $state.Status +
            ' exit=' + $state.ExitCode +
            ' oom=' + $state.OOMKilled +
            ' error=' + $state.Error)
    }
    Write-Ok ($Description + ' validated by one-shot exit=0')
}


function Get-ContainerPythonMinor {
    param([Parameter(Mandatory=$true)][string]$Service,[switch]$OrchestrationProfile)
    if ($OrchestrationProfile) {
        $result = Invoke-NativeCapture { docker compose --profile orchestration exec -T $Service python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" }
    } else {
        $result = Invoke-NativeCapture { docker compose exec -T $Service python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" }
    }
    if ($result.Code -ne 0) { throw ('Unable to read Python version from ' + $Service + ': ' + $result.Text) }
    $version=$result.Text.Trim()
    if ($version -notmatch '^\d+\.\d+$') { throw ('Unexpected Python version from ' + $Service + ': ' + $version) }
    return $version
}

function Test-AirflowSparkPythonParity {
    $airflowPython=Get-ContainerPythonMinor -Service 'airflow' -OrchestrationProfile
    $masterPython=Get-ContainerPythonMinor -Service 'spark-master'
    $worker1Python=Get-ContainerPythonMinor -Service 'spark-worker-1'
    $worker2Python=Get-ContainerPythonMinor -Service 'spark-worker-2'
    $versions=@($airflowPython,$masterPython,$worker1Python,$worker2Python)
    $distinct=@($versions | Select-Object -Unique)
    if ($distinct.Count -ne 1) { throw ('Airflow/Spark Python mismatch: airflow=' + $airflowPython + ', master=' + $masterPython + ', worker1=' + $worker1Python + ', worker2=' + $worker2Python) }
    Write-Ok ('Airflow/Spark Python parity: ' + $airflowPython)
}


function Test-CoreFunctional {
    param([switch]$IncludeSparkSmoke)

    Write-Section 'Functional validation: PostgreSQL / Kafka / S3 / Iceberg / Trino'

    # PostgreSQL:
    # Do not parse psql stdout on Windows.  postgres-bootstrap already runs
    # the SQL schema/seed and exits non-zero unless customers >= 5.
    $pgState = Get-ServiceState 'postgres-source'
    if (-not $pgState.Exists -or $pgState.Status -ne 'running' -or
        -not $pgState.HasHealthcheck -or $pgState.Health -ne 'healthy') {
        throw ('PostgreSQL service invalid: status=' + $pgState.Status +
            ' health=' + $pgState.Health)
    }
    Assert-OneShotSucceeded -Service 'postgres-bootstrap' -Description 'PostgreSQL schema/seed/customer-count'
    Write-Ok 'PostgreSQL service healthy and bootstrap contract satisfied'

    # Kafka:
    # kafka-init creates the seven required topics and re-lists them internally.
    # Its exit code is the functional contract; avoid parsing kafka-topics output
    # again in Windows PowerShell.
    $kafkaState = Get-ServiceState 'kafka'
    if (-not $kafkaState.Exists -or $kafkaState.Status -ne 'running' -or
        -not $kafkaState.HasHealthcheck -or $kafkaState.Health -ne 'healthy') {
        throw ('Kafka service invalid: status=' + $kafkaState.Status +
            ' health=' + $kafkaState.Health)
    }
    Assert-OneShotSucceeded -Service 'kafka-init' -Description 'Kafka 7-topic bootstrap'
    Write-Ok 'Kafka service healthy and seven-topic bootstrap contract satisfied'

    # S3: verify through the same boto3 client used for bootstrap.  The
    # verifier exits non-zero if a bucket or marker object is missing.
    $s3 = Invoke-NativeCapture { docker compose run --rm --no-deps objectstore-init --verify-only }
    if ($s3.Code -ne 0) {
        throw ('S3 bucket validation failed (exit=' + $s3.Code + '): ' + $s3.Text)
    }
    Write-Ok 'S3 buckets warehouse/lakehouse/checkpoints verified with marker objects'

    Wait-Http -Name 'Iceberg REST' -Url 'http://127.0.0.1:8181/v1/config' -TimeoutSeconds 60

    if ($IncludeSparkSmoke) {
        [void](Invoke-SparkJob -JobName '00_runtime_smoke.py' -RequiredMarkers @(
            'SMOKE_PARQUET_COUNT=3',
            'SMOKE_DELTA_COUNT=3',
            'SMOKE_ICEBERG_COUNT=3',
            'SMOKE_RUNTIME_OK'
        ))
    }

    # Direct catalog queries prove both Trino catalogs are loaded.  Use stable
    # textual markers rather than parsing numeric CLI output.
    $trinoPg = Invoke-TrinoSql "SELECT IF(count(*) >= 5, 'POSTGRES_FEDERATION_OK', 'POSTGRES_FEDERATION_BAD') FROM postgresql.public.customers"
    if ($trinoPg.Code -ne 0 -or $trinoPg.Text -notmatch 'POSTGRES_FEDERATION_OK') {
        throw ('Trino PostgreSQL federation failed: ' + $trinoPg.Text)
    }
    Write-Ok 'Trino -> PostgreSQL validated (customers >= 5)'

    $trinoIce = Invoke-TrinoSql "SELECT IF(count(*) = 3, 'ICEBERG_QUERY_OK', 'ICEBERG_QUERY_BAD') FROM iceberg.smoke.runtime_check"
    if ($trinoIce.Code -ne 0 -or $trinoIce.Text -notmatch 'ICEBERG_QUERY_OK') {
        throw ('Trino Iceberg query failed: ' + $trinoIce.Text)
    }
    Write-Ok 'Trino -> Iceberg validated (runtime_check=3)'
}
