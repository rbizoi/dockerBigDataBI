from pyspark.sql import SparkSession, functions as F, types as T

spark = SparkSession.builder.appName("training-batch-to-parquet").getOrCreate()
spark.sparkContext.setLogLevel("WARN")

sales_schema = T.StructType([
    T.StructField("sale_id", T.LongType(), False),
    T.StructField("customer_id", T.LongType(), False),
    T.StructField("country", T.StringType(), False),
    T.StructField("product_id", T.LongType(), False),
    T.StructField("product_name", T.StringType(), False),
    T.StructField("category", T.StringType(), False),
    T.StructField("quantity", T.IntegerType(), False),
    T.StructField("unit_price", T.DoubleType(), False),
    T.StructField("discount", T.DoubleType(), False),
    T.StructField("amount", T.DoubleType(), False),
    T.StructField("event_ts", T.StringType(), False),
])

sales = (
    spark.read.option("header", True)
    .schema(sales_schema)
    .csv("/opt/spark/data/input/sales.csv")
    .withColumn("event_ts", F.to_timestamp("event_ts"))
    .withColumn("event_date", F.to_date("event_ts"))
    .withColumn("ingested_at", F.current_timestamp())
)

# Basic training-quality controls.
sales = sales.cache()
valid_sales = sales.filter(
    F.col("sale_id").isNotNull()
    & F.col("customer_id").isNotNull()
    & (F.col("quantity") > 0)
    & (F.col("unit_price") >= 0)
    & (F.col("amount") >= 0)
)

total_count = sales.count()
valid_count = valid_sales.count()
invalid_count = total_count - valid_count
print(f"[QUALITY] total={total_count} valid={valid_count} invalid={invalid_count}")

(
    valid_sales.write.mode("overwrite")
    .partitionBy("event_date")
    .parquet("s3a://lakehouse/bronze/sales")
)

customers = (
    spark.read.option("multiLine", True)
    .json("/opt/spark/data/input/customers.json")
    .select(
        F.col("customer_id").cast("long").alias("customer_id"),
        "first_name", "last_name", "country", "segment"
    )
)

customers.write.mode("overwrite").parquet("s3a://lakehouse/bronze/customers")

print("[OK] Bronze Parquet written to s3a://lakehouse/bronze/")
spark.stop()
