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
    dag_id="web_logs_training_pipeline",
    description="Kafka logs -> Bronze Parquet -> Silver Delta -> Gold Iceberg -> Spark ML",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["training", "logs", "kafka", "delta", "iceberg"],
) as dag:
    kafka_logs_to_delta = SparkSubmitOperator(
        task_id="kafka_logs_to_delta",
        application="/opt/spark/jobs/06_kafka_web_logs_to_delta.py",
        conn_id="spark_default",
        conf=COMMON_CONF,
    )
    delta_logs_to_iceberg = SparkSubmitOperator(
        task_id="delta_logs_to_iceberg",
        application="/opt/spark/jobs/07_delta_web_logs_to_iceberg.py",
        conn_id="spark_default",
        conf=COMMON_CONF,
    )
    logs_ml_kmeans = SparkSubmitOperator(
        task_id="logs_ml_kmeans",
        application="/opt/spark/jobs/08_web_logs_ml_kmeans.py",
        conn_id="spark_default",
        conf=COMMON_CONF,
    )

    kafka_logs_to_delta >> delta_logs_to_iceberg >> logs_ml_kmeans
