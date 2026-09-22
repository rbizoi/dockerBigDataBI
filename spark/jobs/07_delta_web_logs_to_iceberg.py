from pyspark.sql import SparkSession, functions as F

spark = SparkSession.builder.appName("training-web-logs-delta-to-iceberg").getOrCreate()
spark.sparkContext.setLogLevel("WARN")

logs = spark.read.format("delta").load("s3a://lakehouse/delta/web_logs_silver")
if logs.limit(1).count() == 0:
    raise RuntimeError("Silver Delta web log table is empty")

spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.logs")

# Detailed normalized table for SQL and BI exploration.
(
    logs.select(
        "event_time", "event_date", "event_hour", "log_type", "source_file",
        "client_ip", "user_id", "method", "path", "protocol", "status",
        "bytes_sent", "user_agent", "response_time_ms", "app_level",
        "app_service", "trace_id", "app_message", "message"
    )
    .writeTo("iceberg.logs.events")
    .using("iceberg")
    .partitionedBy("event_date")
    .createOrReplace()
)

access = logs.filter(F.col("log_type") == "apache_access")
traffic_hourly = (
    access.groupBy("event_hour")
    .agg(
        F.count("*").alias("requests"),
        F.countDistinct("client_ip").alias("unique_clients"),
        F.sum(F.when(F.col("status") >= 400, 1).otherwise(0)).alias("errors_4xx_5xx"),
        F.sum(F.when(F.col("status") >= 500, 1).otherwise(0)).alias("errors_5xx"),
        F.round(F.avg("response_time_ms"), 2).alias("avg_response_ms"),
        F.expr("percentile_approx(response_time_ms, 0.95)").alias("p95_response_ms"),
        F.sum("bytes_sent").alias("bytes_sent"),
    )
    .withColumn("error_rate_pct", F.round(F.col("errors_4xx_5xx") * F.lit(100.0) / F.col("requests"), 2))
    .withColumn("refreshed_at", F.current_timestamp())
)
traffic_hourly.writeTo("iceberg.logs.traffic_hourly").using("iceberg").createOrReplace()

path_daily = (
    access.groupBy("event_date", "path", "method")
    .agg(
        F.count("*").alias("requests"),
        F.sum(F.when(F.col("status") >= 400, 1).otherwise(0)).alias("errors"),
        F.round(F.avg("response_time_ms"), 2).alias("avg_response_ms"),
        F.expr("percentile_approx(response_time_ms, 0.95)").alias("p95_response_ms"),
        F.sum("bytes_sent").alias("bytes_sent"),
    )
    .withColumn("error_rate_pct", F.round(F.col("errors") * F.lit(100.0) / F.col("requests"), 2))
)
path_daily.writeTo("iceberg.logs.path_daily").using("iceberg").partitionedBy("event_date").createOrReplace()

app = logs.filter(F.col("log_type") == "application")
app_daily = (
    app.groupBy("event_date", "app_service", "app_level")
    .agg(F.count("*").alias("events"))
)
app_daily.writeTo("iceberg.logs.application_daily").using("iceberg").partitionedBy("event_date").createOrReplace()

print("[OK] Silver Delta -> Iceberg Gold tables: events, traffic_hourly, path_daily, application_daily.")
spark.stop()
