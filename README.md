# Docker formation BigData et BI

Laboratoire Docker Desktop pour une formation Big Data / Business Intelligence sous Windows.

## 01 Architecture

Sources (PostgreSQL, CSV, JSON, XLSX, OpenData, logs) → Kafka → Spark → Bronze Parquet → Silver Delta → Gold Iceberg → Trino → Power BI.

Une branche indépendante Kafka → Logstash → Elasticsearch → Kibana est disponible via le profil `elastic`. Airflow est disponible via le profil `orchestration`.

<img src="https://raw.githubusercontent.com/rbizoi/dockerBigDataBI/refs/heads/master/images/architecture.png" width="1024">

## 02 Principes de robustesse

- aucun contrôle RAM hôte bloquant ;
- aucune résolution Maven pendant `spark-submit` : les JARs sont intégrés à l'image Spark au build ;
- initialisation S3 via l'API S3 standard (`boto3`) avec création + `head_bucket` + objet marqueur + `head_object` ;
- PostgreSQL et Kafka ont des bootstraps idempotents auto-validants ;
- catalogue Iceberg REST persistant sur SQLite avec un seul client JDBC pour le laboratoire mono-instance ;
- healthchecks explicites sur les services critiques ;
- PowerShell 5.1 : capture locale de `stderr` des commandes natives sans transformer les warnings JVM en échecs ;
- le fichier temporaire de version Spark utilisé au build Airflow appartient à `airflow`, ce qui évite un échec final `Operation not permitted` lors du nettoyage de `/tmp` ;
- le driver Spark exécuté dans Airflow reçoit explicitement le client HTTP AWS SDK v2 `url-connection-client` requis par Iceberg S3FileIO ;
- l'interface temps réel du driver Jupyter est publiée par le service `spark-jupyter` sur `http://localhost:4040` ;
- Kibana dispose d'un heap Node.js de 1 Go dans un conteneur limité à 1,5 Go, et l'installateur détecte explicitement un épuisement du heap pendant son démarrage ;
- l'événement de validation Elastic est envoyé comme un JSON correctement terminé, puis recherché par une requête term exacte dans les index training-logs-* ;
- succès final uniquement après un vrai smoke test Parquet + Delta + Iceberg et des requêtes Trino.

## 03 Commandes

```powershell
# cœur uniquement
.\Install-BigDataLab.ps1 -Reset

# ensemble complet (projet, Airflow, Elastic, OpenData)
.\Install-BigDataLab.ps1 -Reset -Full

# reprendre sans pull/build
.\Install-BigDataLab.ps1 -SkipPull -SkipBuild -Full

# vérifier le cœur déjà démarré
.\Verify-BigDataLab.ps1

# arrêt sans supprimer les volumes
.\Stop-BigDataLab.ps1

# suppression des conteneurs/volumes de ce projet uniquement
.\Reset-BigDataLab.ps1
```

## 04 Interfaces

### 04.01 PostgreSQL

>> - PostgreSQL : `localhost:5432`

### 04.02 Kafka
>> - Kafka externe : `localhost:29092`

### 04.03 RustFS
>> - RustFS S3 : `http://localhost:9000` 
>> - RustFS console : `http://localhost:9001`

<img src="https://raw.githubusercontent.com/rbizoi/dockerBigDataBI/refs/heads/master/images/RustFS01.png" width="256">
<img src="https://raw.githubusercontent.com/rbizoi/dockerBigDataBI/refs/heads/master/images/RustFS02.png" width="256">

### 04.04 Iceberg
- Iceberg REST : `http://localhost:8181`

### 04.05 Spark 
>> - Master UI (`8080`): <i><a href="http://localhost:18080">`http://localhost:18080`</a><br></i>

<img src="https://raw.githubusercontent.com/rbizoi/dockerBigDataBI/refs/heads/master/images/SparkMaster.png" width="512">

>> - Workers (`8081`,`8082`): <br>
    >> <i><a href="http://localhost:18081">`http://localhost:18081`</a><br></i>
    >> <i><a href="http://localhost:18082">`http://localhost:18082`</a><br></i>

<img src="https://raw.githubusercontent.com/rbizoi/dockerBigDataBI/refs/heads/master/images/SparkWorker.png" width="512">

>> - Jobs : <i><a href="http://localhost:4040">`http://localhost:4040`</a><br></i>

<img src="https://raw.githubusercontent.com/rbizoi/dockerBigDataBI/refs/heads/master/images/SparkJobs.png" width="512">

>> - History Server (`18083`): <i><a href="http://localhost:18083">`http://localhost:18083`</a><br></i> 

<img src="https://raw.githubusercontent.com/rbizoi/dockerBigDataBI/refs/heads/master/images/SparkHistoryServer.png" width="512">

>> - Jupyter Lab PySpark (`8888`): <i><a href="http://localhost:8888">`http://localhost:8888`</a><br></i>

<img src="https://raw.githubusercontent.com/rbizoi/dockerBigDataBI/refs/heads/master/images/JupyterLab.png" width="512">


### 04.06 Trino
- Trino : `http://localhost:8085`

<img src="https://raw.githubusercontent.com/rbizoi/dockerBigDataBI/refs/heads/master/images/Trino.png" width="512">

### 04.07 Airflow

- Airflow : `http://localhost:8088`

<img src="https://raw.githubusercontent.com/rbizoi/dockerBigDataBI/refs/heads/master/images/AirFlow.png" width="512">

### 04.08 Elasticsearch

- Elasticsearch : `http://localhost:9200` <i><a href="http://localhost:8888">`http://localhost:9200`</a><br></i>
- Kibana : `http://localhost:5601` <i><a href="http://localhost:8888">`http://localhost:5601`</a><br></i>

<img src="https://raw.githubusercontent.com/rbizoi/dockerBigDataBI/refs/heads/master/images/elastic1.png" width="512">


## 05 Données de formation

- `sales.csv` : 2 000 lignes
- `customers.json` : 100 lignes
- `catalog.xlsx` : 7 produits
- `access.log` : 600 lignes
- `application.log` : 220 lignes

## 06 Limite de validation de l'archive

La distribution contient des contrôles runtime qui s'exécutent sur votre Docker Desktop. L'environnement d'auteur ne possède pas de daemon Docker ; il peut donc valider statiquement les fichiers, syntaxes, dépendances, données et contrats d'exécution, mais ne peut pas prétendre avoir démarré vos conteneurs Windows. Le script d'installation refuse néanmoins d'afficher le succès tant que les contrôles runtime n'ont pas passé sur la machine cible.


## 07 Python runtime contract
PySpark requires the same Python minor version on driver and workers. COMPLETE STABLE discovers the runtime versions and validates Airflow/Spark Python parity with a distributed probe instead of enforcing a number in the installer.
