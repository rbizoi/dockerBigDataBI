# Architecture COMPLETE STABLE

```text
PostgreSQL   CSV/JSON/XLSX   OpenData API   access.log/application.log
     \            |              |                    /
      +-----------+--------------+-------------------+
                              |
                            Kafka
                              |
                +-------------+-------------+
                |                           |
              Spark                       Logstash
                |                           |
         Bronze Parquet                Elasticsearch
                |                           |
          Silver Delta                    Kibana
                |
           Gold Iceberg
                |
              Trino
                |
          Power BI / SQL

Airflow orchestre les jobs Spark lorsque le profil orchestration est activé.

JupyterLab fournit un driver PySpark interactif dans un conteneur dédié. Il se
connecte au master `spark://spark-master:7077`, tandis que les calculs sont
exécutés par les deux workers. Les notebooks restent dans `spark/notebooks` sur
la machine hôte.

Les journaux d'événements de toutes les applications Spark sont écrits dans
S3/RustFS et relus par Spark History Server sur le port 18083.
```

Le passage Parquet → Delta → Iceberg représente ici des zones pédagogiques Bronze/Silver/Gold, pas une obligation universelle d'architecture Lakehouse.
