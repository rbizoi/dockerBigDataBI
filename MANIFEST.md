# BigData / Business Intelligence Docker Training Lab — COMPLETE STABLE

Consolidated distribution: no intermediate repair/hotfix artifacts are included.

## Runtime contract
- Spark Standalone runtime remains the single source of truth for the PySpark driver version.
- Airflow provider dependencies are selected from the official constraints matching the Airflow base image.
- `pyspark-client` is explicitly rejected when full `pyspark` is installed, preventing namespace collisions.
- Airflow and Spark Python minor versions are discovered and compared dynamically.
- Airflow build metadata copied into `/tmp` is owned by the `airflow` user so cleanup cannot fail on the sticky `/tmp` directory.
- NumPy is installed without an installer-side exact-version gate; import compatibility is validated at build time.
- distributed smoke validates real driver/worker Python parity before S3/Parquet/Delta/Iceberg.
- Kibana uses a 1 GiB Node.js heap inside a 1.5 GiB container limit, with explicit heap-exhaustion detection during readiness.
- Elastic validation pipes JSON directly from PowerShell to the Kafka producer, avoiding nested-shell quote removal, and verifies it with an exact Elasticsearch term query.
- dockerBigData Spark settings are safely adapted to Spark 4 and Compose, with shared S3 event logs and a validated History Server.
- JupyterLab is baked into the Spark runtime, starts as a dedicated validated service, and uses the same PySpark/Python runtime as the workers.
- Jupyter runtime/config/cache directories are explicitly writable by the `spark` user; the upstream `/nonexistent` home is never used.
- Jupyter's ordinary Python process receives Spark's bundled PySpark and Py4J sources through a stable build-time alias and an explicit `PYTHONPATH`.
- Compose explicitly runs Jupyter as `spark`; recursive home ownership and real write probes prevent false-positive readiness.

- `docs/AIRFLOW_ICEBERG_S3_FIX.md` - Airflow Spark driver / Iceberg S3 AWS HTTP client correction.
- `docs/KIBANA_MEMORY_FIX.md` - Kibana Node.js heap correction and readiness diagnostics.
- `docs/LOGSTASH_VALIDATION_FIX.md` - Kafka/Logstash validation JSON framing and exact Elasticsearch lookup.
- `docs/SPARK_CONFIGURATION_IMPORT.md` - mapping and safety decisions for the dockerBigData Spark configuration.
- `docs/JUPYTERLAB.md` - secure local access, Spark shells, notebook persistence and troubleshooting.
- `docs/JUPYTER_HOME_FIX.md` - root cause and correction for the Jupyter restart loop.
- `docs/JUPYTER_PYSPARK_PATH_FIX.md` - PySpark/Py4J import-path correction for Jupyter kernels.
- `docs/JUPYTER_OWNERSHIP_FIX.md` - recursive home ownership and notebook save validation.
