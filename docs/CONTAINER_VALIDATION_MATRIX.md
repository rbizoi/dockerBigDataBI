# Matrice de validation des conteneurs

| Service | Type | Validation obligatoire |
|---|---|---|
| postgres-source | long-running | `pg_isready` puis `SELECT count(*)` |
| postgres-bootstrap | one-shot | schéma + seed + `POSTGRES_BOOTSTRAP_OK` / exit 0 |
| kafka | long-running | Admin API via `kafka-topics --list` |
| kafka-init | one-shot | création et relecture des 7 topics / exit 0 |
| objectstore-permissions | one-shot | droits volume / exit 0 |
| objectstore | long-running | `/health/ready` |
| objectstore-init | one-shot | create/head/put/head des 3 buckets via boto3 |
| iceberg-catalog-permissions | one-shot | droits volume catalogue / exit 0 |
| iceberg-rest | long-running | `/v1/config` |
| spark-master | long-running | socket 7077 + Master UI |
| spark-worker-1 | long-running | Worker UI + exécution réelle du smoke test |
| spark-worker-2 | long-running | Worker UI + exécution réelle du smoke test |
| spark-history | long-running | UI 18083 + découverte du journal d’événements S3 |
| spark-jupyter | long-running | socket 8888 + page login + imports JupyterLab/PySpark |
| trino | long-running | `/v1/info`, `SHOW CATALOGS`, PostgreSQL, Iceberg |
| mock-opendata | optionnel | endpoint `/health` |
| api-producer | optionnel | processus actif + Kafka |
| file-producer | one-shot | flush Kafka / exit 0 |
| postgres-producer | one-shot | lecture PostgreSQL + flush Kafka / exit 0 |
| web-log-producer | one-shot | exactement 600 + 220 événements |
| airflow-db | optionnel | `pg_isready` |
| airflow | optionnel | health API, DAGs, vrai `spark-submit` |
| elasticsearch | optionnel | `_cluster/health` |
| kibana | optionnel | `/api/status` |
| logstash | optionnel | événement Kafka retrouvé dans Elasticsearch |
