import sys
from pyspark.sql import SparkSession

def _python_runtime_probe(_):
    import socket
    import sys
    yield (socket.gethostname(), f"{sys.version_info.major}.{sys.version_info.minor}", sys.executable)

def main():
    spark = SparkSession.builder.appName("bigdata-runtime-smoke").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    runtime_conf = spark.sparkContext.getConf()
    expected_conf = {
        "spark.serializer": "org.apache.spark.serializer.KryoSerializer",
        "spark.io.compression.lz4.blockSize": "128k",
        "spark.driver.memory": "1g",
        "spark.executor.memory": "1g",
        "spark.deploy.defaultCores": "4",
        "spark.sql.session.timeZone": "UTC",
        "spark.sql.ansi.enabled": "false",
        "spark.eventLog.enabled": "true",
        "spark.eventLog.dir": "s3a://lakehouse/spark-events",
        "spark.history.fs.logDirectory": "s3a://lakehouse/spark-events",
    }
    mismatches = []
    for key, expected in expected_conf.items():
        actual = runtime_conf.get(key, None)
        if actual != expected:
            mismatches.append(f"{key}: expected={expected!r} actual={actual!r}")
    if mismatches:
        raise RuntimeError("Imported Spark configuration mismatch: " + "; ".join(mismatches))
    print("SPARK_IMPORTED_CONFIG_OK")

    driver_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"PYTHON_DRIVER_VERSION={driver_version}")
    print(f"PYTHON_DRIVER_EXECUTABLE={sys.executable}")
    probes = spark.sparkContext.parallelize(range(4), 4).mapPartitions(_python_runtime_probe).collect()
    worker_versions = sorted({version for _, version, _ in probes})
    worker_executables = sorted({exe for _, _, exe in probes})
    worker_hosts = sorted({host for host, _, _ in probes})
    print("PYTHON_WORKER_VERSIONS=" + ",".join(worker_versions))
    print("PYTHON_WORKER_EXECUTABLES=" + ",".join(worker_executables))
    print("PYTHON_WORKER_HOSTS=" + ",".join(worker_hosts))
    if worker_versions != [driver_version]:
        raise RuntimeError(f"PySpark Python minor mismatch: driver={driver_version} workers={worker_versions}")
    print("PYTHON_RUNTIME_PARITY_OK")

    rows=[(1,"alpha",10.5),(2,"beta",20.0),(3,"gamma",30.25)]
    df=spark.createDataFrame(rows,["id","label","value"])
    parquet_path="s3a://lakehouse/_smoke/parquet"; delta_path="s3a://lakehouse/_smoke/delta"
    df.write.mode("overwrite").parquet(parquet_path)
    parquet_count=spark.read.parquet(parquet_path).count()
    if parquet_count != 3: raise RuntimeError(f"Parquet smoke count mismatch: {parquet_count}")
    df.write.format("delta").mode("overwrite").save(delta_path)
    delta_count=spark.read.format("delta").load(delta_path).count()
    if delta_count != 3: raise RuntimeError(f"Delta smoke count mismatch: {delta_count}")
    spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.smoke")
    spark.sql("DROP TABLE IF EXISTS iceberg.smoke.runtime_check")
    df.writeTo("iceberg.smoke.runtime_check").using("iceberg").create()
    iceberg_count=spark.table("iceberg.smoke.runtime_check").count()
    if iceberg_count != 3: raise RuntimeError(f"Iceberg smoke count mismatch: {iceberg_count}")
    print(f"SMOKE_PARQUET_COUNT={parquet_count}")
    print(f"SMOKE_DELTA_COUNT={delta_count}")
    print(f"SMOKE_ICEBERG_COUNT={iceberg_count}")
    print("SMOKE_RUNTIME_OK")
    spark.stop()

if __name__ == "__main__": main()
