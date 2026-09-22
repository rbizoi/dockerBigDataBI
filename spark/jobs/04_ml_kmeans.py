from pyspark.ml.clustering import KMeans
from pyspark.ml.feature import StandardScaler, VectorAssembler
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("training-ml-kmeans").getOrCreate()
spark.sparkContext.setLogLevel("WARN")

sales = spark.read.parquet("s3a://lakehouse/bronze/sales").select(
    "sale_id", "customer_id", "country", "category", "quantity", "unit_price", "discount", "amount"
).dropna()

assembler = VectorAssembler(
    inputCols=["quantity", "unit_price", "discount", "amount"],
    outputCol="features_raw",
)
assembled = assembler.transform(sales)

scaler = StandardScaler(inputCol="features_raw", outputCol="features", withStd=True, withMean=True)
scaled = scaler.fit(assembled).transform(assembled)

model = KMeans(k=3, seed=42, featuresCol="features", predictionCol="cluster").fit(scaled)
predictions = model.transform(scaled).select(
    "sale_id", "customer_id", "country", "category", "quantity", "unit_price", "discount", "amount", "cluster"
)

predictions.write.mode("overwrite").parquet("s3a://lakehouse/gold/ml_sales_clusters")

spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.ml")
predictions.writeTo("iceberg.ml.sales_clusters").using("iceberg").createOrReplace()

print("[ML] KMeans cluster centers:")
for center in model.clusterCenters():
    print(center)
print("[OK] ML predictions written to Parquet and Iceberg.")
spark.stop()
