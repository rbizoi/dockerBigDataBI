from datetime import datetime

from airflow import DAG
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

COMMON_CONF = {
    "spark.driver.host": "airflow",
    "spark.driver.bindAddress": "0.0.0.0",
    "spark.executor.cores": "1",
    "spark.executor.memory": "768m",
    "spark.driver.memory": "768m",
}

with DAG(
    dag_id="bigdata_training_pipeline",
    description="Batch/Kafka -> Bronze Parquet -> Delta -> Iceberg -> Spark ML",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["training", "spark", "lakehouse"],
) as dag:
    batch_to_parquet = SparkSubmitOperator(
        task_id="batch_to_parquet",
        application="/opt/spark/jobs/01_batch_to_parquet.py",
        conn_id="spark_default",
        conf=COMMON_CONF,
    )
    kafka_to_delta = SparkSubmitOperator(
        task_id="kafka_to_delta_available_now",
        application="/opt/spark/jobs/02_kafka_to_delta.py",
        conn_id="spark_default",
        conf=COMMON_CONF,
    )
    kafka_aux_to_parquet = SparkSubmitOperator(
        task_id="kafka_aux_to_parquet",
        application="/opt/spark/jobs/05_kafka_aux_to_parquet.py",
        conn_id="spark_default",
        conf=COMMON_CONF,
    )
    build_iceberg_gold = SparkSubmitOperator(
        task_id="build_iceberg_gold",
        application="/opt/spark/jobs/03_build_iceberg_gold.py",
        conn_id="spark_default",
        conf=COMMON_CONF,
    )
    ml_kmeans = SparkSubmitOperator(
        task_id="ml_kmeans",
        application="/opt/spark/jobs/04_ml_kmeans.py",
        conn_id="spark_default",
        conf=COMMON_CONF,
    )

    batch_to_parquet >> [kafka_to_delta, kafka_aux_to_parquet]
    [kafka_to_delta, kafka_aux_to_parquet] >> build_iceberg_gold >> ml_kmeans
