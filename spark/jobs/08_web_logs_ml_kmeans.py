import math
import traceback

from pyspark.ml.clustering import KMeans
from pyspark.ml.feature import StandardScaler, VectorAssembler
from pyspark.sql import SparkSession, functions as F


APP_NAME = "training-web-logs-ml-kmeans"
FEATURE_COLS = [
    "requests",
    "error_rate_pct",
    "avg_response_ms",
    "p95_response_ms",
    "bytes_sent",
]


def main():
    spark = SparkSession.builder.appName(APP_NAME).getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    stage = "startup"

    try:
        stage = "read_path_daily"
        print(f"ML_STAGE={stage}")
        metrics = (
            spark.table("iceberg.logs.path_daily")
            .select(
                "event_date",
                "path",
                "method",
                *FEATURE_COLS,
                "errors",
            )
        )

        # MLlib expects numeric finite feature values.  Cast explicitly so
        # Iceberg aggregate types (long/int/double) cannot cause schema
        # ambiguity in VectorAssembler.
        stage = "cast_and_validate_features"
        print(f"ML_STAGE={stage}")
        for col_name in FEATURE_COLS:
            metrics = metrics.withColumn(col_name, F.col(col_name).cast("double"))

        finite_condition = F.lit(True)
        for col_name in FEATURE_COLS:
            finite_condition = (
                finite_condition
                & F.col(col_name).isNotNull()
                & (~F.isnan(F.col(col_name)))
                & (F.abs(F.col(col_name)) < F.lit(float("inf")))
            )

        metrics = metrics.filter(finite_condition).cache()

        row_count = metrics.count()
        distinct_feature_count = metrics.select(*FEATURE_COLS).dropDuplicates().count()

        print(f"WEB_ML_INPUT_ROWS={row_count}")
        print(f"WEB_ML_DISTINCT_FEATURE_ROWS={distinct_feature_count}")

        if row_count == 0:
            raise RuntimeError(
                "No finite rows available in iceberg.logs.path_daily for KMeans"
            )

        stage = "assemble_features"
        print(f"ML_STAGE={stage}")
        assembler = VectorAssembler(
            inputCols=FEATURE_COLS,
            outputCol="features_raw",
            handleInvalid="skip",
        )
        assembled = assembler.transform(metrics).cache()
        assembled_count = assembled.count()
        print(f"WEB_ML_ASSEMBLED_ROWS={assembled_count}")

        if assembled_count == 0:
            raise RuntimeError("VectorAssembler produced zero usable rows")

        # KMeans needs at least two useful clusters.  For a degenerate
        # training sample with a single distinct vector, keep the pipeline
        # operational and assign cluster 0 deterministically.
        if distinct_feature_count < 2:
            stage = "single_cluster_fallback"
            print(f"ML_STAGE={stage}")
            result = (
                assembled.select(
                    "event_date",
                    "path",
                    "method",
                    "requests",
                    "errors",
                    "error_rate_pct",
                    "avg_response_ms",
                    "p95_response_ms",
                    "bytes_sent",
                )
                .withColumn("behavior_cluster", F.lit(0).cast("int"))
                .withColumn("model_refreshed_at", F.current_timestamp())
            )
            print("WEB_ML_K=1")
            print("[ML] Degenerate feature set: assigned behavior_cluster=0")
        else:
            stage = "standardize_features"
            print(f"ML_STAGE={stage}")
            scaler_model = StandardScaler(
                inputCol="features_raw",
                outputCol="features",
                withStd=True,
                withMean=True,
            ).fit(assembled)
            scaled = scaler_model.transform(assembled).cache()

            scaled_count = scaled.count()
            print(f"WEB_ML_SCALED_ROWS={scaled_count}")
            if scaled_count == 0:
                raise RuntimeError("StandardScaler produced zero rows")

            k = min(3, distinct_feature_count, scaled_count)
            print(f"WEB_ML_K={k}")

            stage = "fit_kmeans"
            print(f"ML_STAGE={stage}")
            model = KMeans(
                k=k,
                seed=42,
                featuresCol="features",
                predictionCol="behavior_cluster",
                maxIter=20,
            ).fit(scaled)

            stage = "predict"
            print(f"ML_STAGE={stage}")
            result = (
                model.transform(scaled)
                .select(
                    "event_date",
                    "path",
                    "method",
                    "requests",
                    "errors",
                    "error_rate_pct",
                    "avg_response_ms",
                    "p95_response_ms",
                    "bytes_sent",
                    "behavior_cluster",
                )
                .withColumn("model_refreshed_at", F.current_timestamp())
            )

            print("[ML] Web path KMeans centers:")
            for i, center in enumerate(model.clusterCenters()):
                print(f"cluster={i} center={center}")

        stage = "write_iceberg"
        print(f"ML_STAGE={stage}")
        spark.sql("CREATE NAMESPACE IF NOT EXISTS iceberg.ml")
        (
            result.writeTo("iceberg.ml.web_path_clusters")
            .using("iceberg")
            .createOrReplace()
        )

        output_count = spark.table("iceberg.ml.web_path_clusters").count()
        print(f"WEB_ML_OUTPUT_ROWS={output_count}")
        if output_count != row_count:
            raise RuntimeError(
                f"Output row count mismatch: input={row_count} output={output_count}"
            )

        print("WEB_ML_RUNTIME_OK")
        print("[OK] iceberg.ml.web_path_clusters created.")

    except Exception as exc:
        print(f"WEB_ML_FAILED_STAGE={stage}")
        print(f"WEB_ML_EXCEPTION_TYPE={type(exc).__name__}")
        print(f"WEB_ML_EXCEPTION={exc}")
        traceback.print_exc()
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
