from pyspark.sql import SparkSession, functions as F, types as T

spark = SparkSession.builder.appName("training-kafka-to-delta").getOrCreate()
spark.sparkContext.setLogLevel("WARN")

schema = T.StructType([
    T.StructField("sale_id", T.LongType()),
    T.StructField("customer_id", T.LongType()),
    T.StructField("country", T.StringType()),
    T.StructField("product_id", T.LongType()),
    T.StructField("product_name", T.StringType()),
    T.StructField("category", T.StringType()),
    T.StructField("quantity", T.IntegerType()),
    T.StructField("unit_price", T.DoubleType()),
    T.StructField("discount", T.DoubleType()),
    T.StructField("amount", T.DoubleType()),
    T.StructField("event_ts", T.StringType()),
    T.StructField("ingested_at", T.StringType()),
    T.StructField("source_format", T.StringType()),
])

source = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", "kafka:19092")
    .option("subscribe", "sales.raw")
    .option("startingOffsets", "earliest")
    .load()
)

parsed = (
    source.select(F.from_json(F.col("value").cast("string"), schema).alias("r"))
    .select("r.*")
    .filter(F.col("sale_id").isNotNull() & (F.col("quantity") > 0))
    .withColumn("event_ts", F.to_timestamp("event_ts"))
    .withColumn("event_date", F.to_date("event_ts"))
    .withWatermark("event_ts", "365 days")
    .dropDuplicatesWithinWatermark(["sale_id"])
)

query = (
    parsed.writeStream.format("delta")
    .outputMode("append")
    .option("checkpointLocation", "s3a://checkpoints/delta-sales")
    .option("path", "s3a://lakehouse/delta/sales")
    .partitionBy("event_date")
    .trigger(availableNow=True)
    .start()
)
query.awaitTermination()
print("[OK] Kafka sales.raw -> Delta Lake completed (availableNow).")
spark.stop()
