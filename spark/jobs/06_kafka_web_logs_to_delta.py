from pyspark.sql import SparkSession, functions as F, types as T

spark = SparkSession.builder.appName("training-web-logs-kafka-to-delta").getOrCreate()
spark.sparkContext.setLogLevel("WARN")

envelope_schema = T.StructType([
    T.StructField("@timestamp", T.StringType()),
    T.StructField("source_file", T.StringType()),
    T.StructField("line_number", T.IntegerType()),
    T.StructField("log_type", T.StringType()),
    T.StructField("message", T.StringType()),
])

kafka_df = (
    spark.read.format("kafka")
    .option("kafka.bootstrap.servers", "kafka:19092")
    .option("subscribe", "web.logs.raw")
    .option("startingOffsets", "earliest")
    .option("endingOffsets", "latest")
    .load()
)

raw = (
    kafka_df.select(
        F.col("partition").alias("kafka_partition"),
        F.col("offset").alias("kafka_offset"),
        F.col("timestamp").alias("kafka_timestamp"),
        F.col("key").cast("string").alias("message_key"),
        F.from_json(F.col("value").cast("string"), envelope_schema).alias("e"),
    )
    .select("kafka_partition", "kafka_offset", "kafka_timestamp", "message_key", "e.*")
    .withColumnRenamed("@timestamp", "ingest_ts_raw")
    .dropDuplicates(["source_file", "line_number", "log_type"])
)

# Preserve the immutable input before parsing. This is the Bronze layer.
(
    raw.write.mode("overwrite")
    .partitionBy("log_type")
    .parquet("s3a://lakehouse/bronze/web_logs_raw")
)

access_pattern = r'^(\S+) \S+ (\S+) \[([^]]+)\] "(\S+) ([^ ]+) HTTP/([^"]+)" (\d{3}) (\d+) "([^"]*)" "([^"]*)" (\d+)$'
app_pattern = r'^(\S+) (INFO|WARN|ERROR) service=([^ ]+) trace_id=([^ ]+) message="(.*)"$'

access = (
    raw.filter(F.col("log_type") == "apache_access")
    .withColumn("client_ip", F.regexp_extract("message", access_pattern, 1))
    .withColumn("user_id", F.regexp_extract("message", access_pattern, 2))
    .withColumn("access_time", F.regexp_extract("message", access_pattern, 3))
    .withColumn("method", F.regexp_extract("message", access_pattern, 4))
    .withColumn("path", F.regexp_extract("message", access_pattern, 5))
    .withColumn("protocol", F.concat(F.lit("HTTP/"), F.regexp_extract("message", access_pattern, 6)))
    .withColumn("status", F.regexp_extract("message", access_pattern, 7).cast("int"))
    .withColumn("bytes_sent", F.regexp_extract("message", access_pattern, 8).cast("long"))
    .withColumn("referrer", F.regexp_extract("message", access_pattern, 9))
    .withColumn("user_agent", F.regexp_extract("message", access_pattern, 10))
    .withColumn("response_time_ms", F.regexp_extract("message", access_pattern, 11).cast("int"))
    .withColumn("event_time", F.to_timestamp("access_time", "dd/MMM/yyyy:HH:mm:ss Z"))
    .withColumn("app_level", F.lit(None).cast("string"))
    .withColumn("app_service", F.lit(None).cast("string"))
    .withColumn("trace_id", F.lit(None).cast("string"))
    .withColumn("app_message", F.lit(None).cast("string"))
    .withColumn("parse_ok", F.col("event_time").isNotNull() & F.col("status").isNotNull())
)

application = (
    raw.filter(F.col("log_type") == "application")
    .withColumn("event_time", F.to_timestamp(F.regexp_extract("message", app_pattern, 1)))
    .withColumn("app_level", F.regexp_extract("message", app_pattern, 2))
    .withColumn("app_service", F.regexp_extract("message", app_pattern, 3))
    .withColumn("trace_id", F.regexp_extract("message", app_pattern, 4))
    .withColumn("app_message", F.regexp_extract("message", app_pattern, 5))
    .withColumn("client_ip", F.lit(None).cast("string"))
    .withColumn("user_id", F.lit(None).cast("string"))
    .withColumn("method", F.lit(None).cast("string"))
    .withColumn("path", F.lit(None).cast("string"))
    .withColumn("protocol", F.lit(None).cast("string"))
    .withColumn("status", F.lit(None).cast("int"))
    .withColumn("bytes_sent", F.lit(None).cast("long"))
    .withColumn("referrer", F.lit(None).cast("string"))
    .withColumn("user_agent", F.lit(None).cast("string"))
    .withColumn("response_time_ms", F.lit(None).cast("int"))
    .withColumn("parse_ok", F.col("event_time").isNotNull() & (F.length("app_level") > 0))
)

cols = [
    "kafka_partition", "kafka_offset", "kafka_timestamp", "message_key",
    "source_file", "line_number", "log_type", "message", "ingest_ts_raw",
    "event_time", "client_ip", "user_id", "method", "path", "protocol",
    "status", "bytes_sent", "referrer", "user_agent", "response_time_ms",
    "app_level", "app_service", "trace_id", "app_message", "parse_ok",
]
normalized = access.select(cols).unionByName(application.select(cols))

valid = (
    normalized.filter("parse_ok")
    .withColumn("event_date", F.to_date("event_time"))
    .withColumn("event_hour", F.date_trunc("hour", "event_time"))
    .withColumn("ingested_at", F.to_timestamp("ingest_ts_raw"))
)
invalid = normalized.filter("NOT parse_ok")

valid_count = valid.count()
invalid_count = invalid.count()
print(f"[QUALITY] web logs valid={valid_count} invalid={invalid_count}")
if valid_count == 0:
    raise RuntimeError("No valid web log records were parsed; check input and regex patterns")

(
    valid.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .partitionBy("event_date", "log_type")
    .save("s3a://lakehouse/delta/web_logs_silver")
)

if invalid_count > 0:
    invalid.write.mode("overwrite").parquet("s3a://lakehouse/quarantine/web_logs")

print("[OK] Kafka web.logs.raw -> Bronze Parquet -> Silver Delta completed.")
spark.stop()
