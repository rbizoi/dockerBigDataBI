# Notebooks Spark

Les fichiers de ce dossier sont conservés sur la machine Windows et montés dans
JupyterLab sous `/opt/spark/notebooks`.

Commencez par `01_demarrage_spark.ipynb`. La variable `PYSPARK_SUBMIT_ARGS`
relie automatiquement le driver Jupyter au master `spark://spark-master:7077`.

Pour les sorties volumineuses, préférez les emplacements S3 du laboratoire
(`s3a://lakehouse/...`) plutôt que le système de fichiers local du conteneur.
