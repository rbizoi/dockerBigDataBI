# Correction de l'import PySpark dans JupyterLab

## Symptôme

JupyterLab est `running / healthy`, mais le contrôle suivant échoue :

```text
ModuleNotFoundError: No module named 'pyspark'
```

## Cause confirmée

L'image Apache Spark contient les sources PySpark dans `/opt/spark/python` et
Py4J dans une archive versionnée sous `/opt/spark/python/lib`. Les commandes
`spark-submit` et `pyspark` construisent ce chemin automatiquement, mais un
processus `python3` ou un noyau Jupyter standard ne le reçoit pas.

## Correction FIXED8

- détection au build de l'archive `py4j-*-src.zip` réellement fournie ;
- création de l'alias stable `/opt/spark/python/lib/py4j-src.zip` ;
- définition persistante de `PYTHONPATH` pour l'image et `spark-jupyter` ;
- contrôle de build avec un vrai `python3 -c "import py4j, pyspark"` ;
- conservation d'une seule distribution PySpark, celle de Spark 4.0.4.

Cette solution évite d'installer une seconde copie de PySpark avec `pip`, ce qui
pourrait créer une divergence entre le driver Jupyter et les workers.
