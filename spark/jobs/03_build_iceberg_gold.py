from pyspark.sql import SparkSession, functions as F

spark = SparkSession.builder.appName("training-build-iceberg-gold").getOrCreate()
spark.sparkContext.setLogLevel("WARN")

sales = spark.read.parquet("s3a://lakehouse/bronze/sales")

summary = (
    sales.groupBy("country", "category")
    .agg(
        F.countDistinct("sale_id").alias("sales_count"),
        F.sum("quantity").alias("units_sold"),
        F.round(F.sum("amount"), 2).alias("total_revenue"),
        F.round(F.avg("amount"), 2).alias("avg_sale_amount"),
    )
    .withColumn("refreshed_at", F.current_timestamp())
)

spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.gold")
summary.writeTo("iceberg.gold.sales_summary").using("iceberg").createOrReplace()

# A detailed table is useful for Trino/BI demonstrations.
(
    sales.select(
        "sale_id", "customer_id", "country", "product_id", "product_name",
        "category", "quantity", "unit_price", "discount", "amount",
        "event_ts", "event_date"
    )
    .writeTo("iceberg.gold.sales_detail")
    .using("iceberg")
    .partitionedBy("event_date")
    .createOrReplace()
)

print("[OK] Iceberg tables iceberg.gold.sales_summary and sales_detail created.")
spark.stop()
