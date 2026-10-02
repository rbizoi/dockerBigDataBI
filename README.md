# Docker formation Big Data et BI — Windows et Linux

Laboratoire pédagogique utilisable avec **les mêmes commandes Docker** sous Windows (Docker Desktop en mode conteneurs Linux / WSL2) et Linux (Docker Engine + Compose v2, ou Docker Desktop). Aucun script Shell, PowerShell ou CMD à exécuter ; Python et les dépendances tournent dans les conteneurs.

Télécharger et extraire le ZIP du dépôt ou utiliser un checkout existant, puis ouvrir un terminal dans le dossier contenant `compose.yaml`. Docker doit être installé et démarré. Prévoir environ 24–32 Go de RAM disponibles pour la pile complète, plusieurs dizaines de Go de disque et une connexion Internet au premier build. Ce sont des estimations, sans contrôle RAM bloquant. Le cœur reste utilisable séparément.

## Démarrage complet

Les valeurs pédagogiques de secours de Compose sont utilisables directement. Le dépôt ne distribue aucun `.env` avec des secrets personnels. Pour personnaliser les paramètres, créer facultativement `.env` avec un éditeur à partir de `.env.example` avant le premier démarrage. Aucun `cp`, script hôte ou Python hôte n’est nécessaire.

```text
docker version
docker compose version
docker info --format "{{.OSType}}"
docker compose --profile full config --quiet
docker compose --profile full build
docker compose --profile full up -d
```

`OSType` doit être `linux`, y compris sous Windows. Compose attend les dépendances saines et les initialisations terminées. La fin de `up -d` ne constitue pas une validation des échanges de données. Le premier démarrage de la pile complète peut prendre plusieurs minutes.

**Portail : http://localhost:8090**. Il regroupe les interfaces, les identifiants réellement configurés et les rapports. Les boutons ouvrent les interfaces des conteneurs déjà démarrés ; ils ne démarrent pas de conteneurs.

## Contrôles fonctionnels avec les données existantes

```text
docker compose --profile checks run --rm integration-check --full
docker compose --profile checks run --rm airflow-check
```

Exécuter ces deux commandes successivement. Selon le matériel, prévoir jusqu’à 30–60 minutes pour la première validation complète. La seconde nécessite les tables produites par la première. Chaque commande retourne `0` seulement si ses contrôles passent, et un code non nul en cas d’échec. **La validation complète exige le succès des deux commandes.** Les rapports `reports/integration.json` et `reports/airflow-check.json`, affichés dans le portail, sont horodatés ; les logs Spark détaillés restent dans `reports/`.

Le contrôle publie les CSV, JSON, XLSX, tables PostgreSQL, logs et OpenData déjà présents dans le dépôt ; exécute les pipelines Spark ; compare les comptes et montants CSV/Parquet/Iceberg/Trino ; vérifie les identifiants Kafka/Delta ; ingère `sales.csv` dans Druid depuis S3 ; vérifie un flux Kafka dans Druid et les segments dans RustFS ; exécute des requêtes depuis Superset sur PostgreSQL, Trino et Druid ; vérifie les données de vente dans Elasticsearch après Logstash. Il teste également les interfaces HTTP.

Le contrôle Airflow charge les deux DAGs et exécute une vérification distribuée des données avec **l’image et le pilote Python Airflow**, contre les workers Spark. Il ne simule pas une exécution complète du scheduler Airflow : celle-ci reste à lancer depuis l’interface pour les exercices.

Les contrôles écrivent dans les zones pédagogiques `bronze`, `delta`, `gold`, `logs`, `ml` et les datasources Druid `training_sales` / `training_sales_stream`. Ils republient les événements Kafka ; ne pas utiliser ce laboratoire avec des données de production. Les traitements dédupliquent les identifiants/positions de logs ; les comptes Kafka bruts et Elasticsearch peuvent augmenter à chaque relance. Le supervisor Druid Kafka reste actif pour les exercices.

Voir [la matrice d’intégration](docs/INTEGRATION_MATRIX.md) pour les liens pris en charge. Une interface utilisateur n’est pas un connecteur universel : les couples sans protocole natif sont explicitement marqués sans intégration directe, et les chaînes entre produits sont testées à travers les connecteurs installés.

## Cœur ou profils séparés

```text
docker compose build
docker compose up -d
docker compose --profile checks run --rm integration-check
```

| Profil | Produits ajoutés | Commande |
|---|---|---|
| `analytics` | Druid, ZooKeeper, métadonnées, Superset | `docker compose --profile analytics up -d --build` |
| `elastic` | Elasticsearch, Logstash, Kibana | `docker compose --profile elastic up -d` |
| `orchestration` | Airflow et sa base | `docker compose --profile orchestration up -d --build` |
| `demo` | API OpenData locale et producteur continu Kafka | `docker compose --profile demo up -d --build` |
| `full` | Les quatre ensembles ci-dessus | `docker compose --profile full up -d --build` |

Les profils `seed` et `logs` restent disponibles pour lancer les producteurs individuellement ; le contrôle d’intégration les exécute lui-même dans son conteneur.

## Interfaces et identifiants par défaut

Les valeurs pédagogiques par défaut utilisent `formation` pour la base, l’utilisateur et le mot de passe SQL PostgreSQL. Un fichier `.env` facultatif prime sur ces valeurs ; il est exclu de Git.

| Produit / interface | Adresse locale | Utilisateur | Mot de passe ou token |
|---|---|---|---|
| Portail | http://localhost:8090 | Aucun | Aucun |
| PostgreSQL / pgAdmin | http://localhost:5050 | `admin@formation.fr` | `formation` |
| Connexion SQL dans pgAdmin | `postgres-source:5432`, base `formation` | `formation` | `formation` |
| Kafka UI | http://localhost:8086 | Aucun | Aucun |
| RustFS | http://localhost:9001 | `labadmin` | `TRAINING_ONLY_S3_PASSWORD` |
| Spark Master | http://localhost:18080 | Aucun | Aucun |
| Spark Workers | http://localhost:18081 et http://localhost:18082 | Aucun | Aucun |
| Spark History | http://localhost:18083 | Aucun | Aucun |
| Job Spark Jupyter | http://localhost:4040 | Aucun | Seulement pendant une session Spark active |
| JupyterLab | http://localhost:8888 | Aucun | `CHANGE_ME` par défaut ; valeur `JUPYTER_TOKEN` dans le portail |
| Trino | http://localhost:8085 | `formation` (libre) | Aucun |
| Airflow | http://localhost:8088 | Aucun en mode pédagogique `all_admins` | Aucun |
| Kibana | http://localhost:5601 | Aucun | Aucun |
| Druid | http://localhost:8889 | Aucun | Aucun |
| Superset | http://localhost:8089 | `admin` | `formation` |

Les ports sont modifiables dans `.env` ; le portail suit les mêmes variables. Pour pgAdmin, le serveur est préenregistré mais le mot de passe SQL est demandé à la connexion. Changer une variable après la création d’un compte ou d’un volume PostgreSQL ne change pas son mot de passe : le modifier dans le produit, ou repartir de volumes neufs si les données sont jetables. Jupyter lit son token au démarrage du conteneur. Les notebooks existants sont copiés une fois dans un volume nommé ; les modifications dans Jupyter y sont conservées. Les nouveautés sont copiées si leur chemin n’existe pas déjà.

Iceberg REST est une API (`http://localhost:8181/v1/config`) sans console native dans l’image utilisée ; ses tables se consultent dans Superset, Trino ou Jupyter. Elasticsearch a Kibana ; Logstash se supervise avec les logs Docker et les données dans Kibana. ZooKeeper et les bases de métadonnées sont des dépendances internes. Parquet et Delta sont des formats, consultables avec Jupyter/Spark. Power BI Desktop reste une application externe Windows : Superset fournit ici l’interface BI disponible sur les deux systèmes.

Tous les ports publiés sont limités à `127.0.0.1`. Les comptes sont pédagogiques et plusieurs services sont sans authentification. Éviter d’exposer ce Compose sur Internet. Le portail affiche volontairement les accès du laboratoire local.

## Validation statique facultative

```text
docker compose --profile checks build static-check
docker compose --profile checks run --rm static-check
```

Cette commande vérifie les fichiers et les contrats des données. Elle ne remplace pas les deux contrôles runtime.

## Commandes de contrôle et d’exploitation

```text
docker compose --profile full ps -a
docker compose --profile full logs --tail 100
docker compose logs postgres-bootstrap kafka-init objectstore-init notebooks-init pgadmin-config
docker compose --profile full logs superset-init druid-coordinator druid-middlemanager
docker compose --profile full exec airflow airflow dags list
docker compose exec trino trino --user formation --execute "SHOW CATALOGS"
docker compose --profile full stop
docker compose --profile full start
docker compose --profile full down
```

`down` conserve les volumes. Pour **supprimer les données Docker de ce projet** et repartir à zéro :

```text
docker compose --profile full --profile checks --profile seed --profile logs down --volumes --remove-orphans
```

Cette dernière commande supprime aussi les notebooks modifiés dans le volume. Les données sources du dépôt et les rapports sur l’hôte restent présents. Ne pas utiliser `docker system prune` pour réinitialiser ce laboratoire.

## Portée des vérifications de cette modification

Configuration validée avec Docker Compose, syntaxes Python et contrats de fichiers vérifiés. L’environnement d’édition ne possède pas de daemon Docker : les images n’y ont pas été construites, les conteneurs n’y ont pas démarré et les intégrations runtime ne sont **pas encore certifiées**. Les commandes de contrôle ci-dessus doivent réussir sur votre machine pour confirmer la pile complète. Les anciens documents de correction décrivent l’historique ; ce README est la procédure actuelle.
