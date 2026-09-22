# Intégration de la configuration Spark de dockerBigData

La distribution COMPLETE_STABLE_FIXED6_SPARKCFG conserve l'architecture et les
correctifs validés de FIXED6, puis adapte les réglages Spark trouvés dans
dockerBigData.zip.

## Paramètres repris

- sérialiseur Kryo ;
- blocs de compression LZ4 de 128 Kio ;
- mémoire driver et executor de 1 Gio ;
- quatre cœurs disponibles sur les deux workers ;
- fuseau horaire SQL UTC ;
- mode ANSI Spark SQL désactivé ;
- nettoyage des journaux historiques tous les 7 jours et rétention de 90 jours ;
- niveaux de journalisation Spark, Jetty, Parquet et Hive traduits vers Log4j2.

## Adaptations au cluster FIXED6

- Spark reste en version 4.0.4 avec Java 17 et la version Python fournie par
  l'image officielle afin de préserver la parité Airflow, master et workers ;
- le master reste spark-master et les workers restent gérés par Docker Compose ;
- les journaux d'événements et l'entrepôt SQL utilisent S3/RustFS plutôt que le
  système de fichiers local d'un conteneur ;
- un service spark-history dédié expose son interface sur localhost:18083 ;
- l'installateur vérifie qu'une application issue du smoke test apparaît
  réellement dans l'API du History Server.

## Éléments volontairement exclus

- mots de passe root ou Spark codés en dur ;
- serveur SSH et démarrage automatique par fichier bashrc ;
- noms de machines externes historiques ;
- environnement Conda Python 3.13, incompatible avec la parité Python validée ;
- historique Git, fichiers IDE et fichier de mot de passe ;
- jeux de données et notebooks, qui ne constituent pas la configuration Spark.

Le paramètre mal orthographié park.sql.ansi.enabled a été corrigé en
spark.sql.ansi.enabled. Le paramètre compute.fail_on_ansi_mode, spécifique à
d'autres plateformes, n'est pas injecté dans Apache Spark.
