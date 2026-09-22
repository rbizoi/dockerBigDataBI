"""Land non-sales Kafka source topics into a raw Bronze Parquet zone.

This job deliberately stores the Kafka payload as JSON text.  It is a teaching
example of the immutable/raw landing pattern: schema-specific parsing can be
performed later without losing the original event.
"""
from pyspark.sql import SparkSession, functions as F

spark = SparkSession.builder.appName("training-kafka-aux-to-parquet").getOrCreate()
spark.sparkContext.setLogLevel("WARN")

raw = (
    spark.read.format("kafka")
    .option("kafka.bootstrap.servers", "kafka:19092")
    .option("subscribe", "customers.raw,catalog.raw,opendata.raw")
    .option("startingOffsets", "earliest")
    .option("endingOffsets", "latest")
    .load()
    .select(
        F.col("topic").alias("kafka_topic"),
        F.col("partition").alias("kafka_partition"),
        F.col("offset").alias("kafka_offset"),
        F.col("timestamp").alias("kafka_timestamp"),
        F.col("key").cast("string").alias("message_key"),
        F.col("value").cast("string").alias("payload_json"),
    )
    .withColumn("ingested_date", F.to_date("kafka_timestamp"))
)

count = raw.count()
print(f"[KAFKA] auxiliary records read={count}")

if count > 0:
    (
        raw.write.mode("overwrite")
        .partitionBy("kafka_topic", "ingested_date")
        .parquet("s3a://lakehouse/bronze/kafka_aux")
    )
    print("[OK] customers/catalog/OpenData Kafka events landed in Bronze Parquet.")
else:
    print("[WARN] No auxiliary Kafka events found; nothing written.")

spark.stop()
