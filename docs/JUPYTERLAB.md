# JupyterLab avec le cluster Spark

## Démarrage recommandé

Exécutez d'abord `INSTALL_CORE.cmd` ou `INSTALL_RESET_FULL.cmd`. L'installateur :

1. génère un jeton aléatoire dans `.env` si nécessaire ;
2. construit JupyterLab dans la même image que Spark 4.0.4 ;
3. démarre `spark-jupyter` après le master et les deux workers ;
4. valide les imports JupyterLab et PySpark.

L'image crée `/home/spark` et les répertoires XDG/Jupyter avec le propriétaire
`spark:spark`. Jupyter n'utilise donc jamais le dossier amont `/nonexistent`.
Elle expose également `/opt/spark/python` et l'archive Py4J dans `PYTHONPATH`,
afin qu'un noyau Python standard puisse importer `pyspark` sans passer par
`spark-submit`.

Le service Compose impose `user: spark`. L'installateur vérifie l'identité Unix
effective, puis crée et supprime de vrais fichiers dans le répertoire de données
Jupyter et dans `spark/notebooks`. Un serveur HTTP sain mais incapable
d'enregistrer un notebook n'est donc plus accepté.

Double-cliquez ensuite sur `OPEN_JUPYTER.cmd`. Le navigateur est ouvert avec le
jeton sans que vous ayez à le recopier.

## Accès manuel

L'interface écoute uniquement sur la boucle locale Windows :

```text
http://127.0.0.1:8888/lab
```

Le jeton se trouve dans la ligne `JUPYTER_TOKEN=` du fichier `.env`. Pour voir
l'URL produite par Jupyter :

```powershell
docker compose logs spark-jupyter
```

## Premier notebook

Ouvrez `01_demarrage_spark.ipynb`, puis exécutez les cellules. La variable
`PYSPARK_SUBMIT_ARGS` configure automatiquement :

- le master `spark://spark-master:7077` ;
- le nom réseau du driver `spark-jupyter` ;
- Python 3 identique côté driver et workers.

Les notebooks sont stockés dans `spark/notebooks` sur Windows. Ils survivent à
la recréation du conteneur. Les données d'exemple sont disponibles en lecture
dans `/opt/spark/data`; les résultats Lakehouse doivent être écrits dans S3.

## Shells Spark

PySpark :

```powershell
docker compose exec spark-master pyspark --master spark://spark-master:7077
```

Scala :

```powershell
docker compose exec spark-master /opt/spark/bin/spark-shell --master spark://spark-master:7077
```

Shell Linux du master :

```powershell
docker compose exec spark-master bash
```

## Diagnostic

```powershell
docker compose ps spark-jupyter
docker compose logs --tail 200 spark-jupyter
docker compose exec spark-jupyter python3 -c "import jupyterlab, pyspark; print(jupyterlab.__version__, pyspark.__version__)"
```

Si le port 8888 est déjà utilisé, changez `JUPYTER_PORT` dans `.env`, puis
relancez `docker compose up -d --force-recreate spark-jupyter`.

Si une ancienne image affiche `PermissionError: /nonexistent`, reconstruisez
obligatoirement l'image puis recréez le service :

```powershell
docker compose build --no-cache spark-master
docker compose up -d --force-recreate spark-master spark-worker-1 spark-worker-2 spark-history spark-jupyter
```
