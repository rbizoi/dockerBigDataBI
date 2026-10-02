# Architecture

Sources CSV/JSON/XLSX/PostgreSQL/OpenData/logs → Kafka → Spark → Parquet/Delta/Iceberg sur RustFS → Trino → Superset.

Branche Kafka → Logstash → Elasticsearch → Kibana. Branche Kafka ou S3 CSV → Druid (ZooKeeper, métadonnées PostgreSQL, segments S3 RustFS) → Superset. Airflow orchestre les jobs Spark. pgAdmin administre PostgreSQL ; Kafka UI expose les topics ; Jupyter, Spark Master/Workers/History exposent les outils de formation. Le portail regroupe tous les accès.

Voir INTEGRATION_MATRIX.md pour les preuves de test et les couples sans intégration native.
