# Validation report — COMPLETE STABLE

Static validation covers Compose, Dockerfiles, Python/Bash syntax, PowerShell structure, dependencies, data fixtures, classpath contracts, Python parity contracts, checksums and post-extraction verification.

The installer performs live runtime checks on the target Docker Desktop host, including imported Spark settings, S3 event logs, Spark History Server discovery, JupyterLab/PySpark imports, Airflow/Spark Python parity and a distributed Airflow -> Spark S3/Parquet/Delta/Iceberg smoke. The package-generation environment has no Docker daemon or Windows PowerShell, so live container execution is not claimed here.

Latest static validation: **208 passed checks, 0 errors, 1 environment warning**. The warning only indicates that the authoring environment has no Docker daemon for live container execution. FIXED13 additionally verifies that Spark Jobs UI is published by the real Jupyter driver service, that the master has no incorrect live-UI mapping, that the Windows launcher detects an active session, and that notebooks contain no obsolete Spark UI hostname.
