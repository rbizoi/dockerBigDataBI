# Correction du test Kafka vers Logstash vers Elasticsearch

## Symptôme

Kibana et Elasticsearch répondaient en HTTP 200, mais l'événement de validation publié dans Kafka n'était jamais retrouvé dans Elasticsearch.

## Cause confirmée

Le JSON traversait une commande imbriquée PowerShell vers Bash. Sous Windows PowerShell, les guillemets doubles du document étaient retirés pendant la construction des arguments natifs.

Logstash recevait donc un objet de la forme suivante, sans guillemets autour des noms et valeurs :

    {validation_id:8139f7d9-99d8-46f9-add9-8b57e9c988fc,message:kafka-logstash-elasticsearch-validation}

au lieu d'un véritable objet JSON. Son codec ajoutait le tag _jsonparsefailure et ne créait pas le champ validation_id.

## Correction

- suppression complète de la commande Bash imbriquée et de ses échappements ;
- transmission directe de la chaîne JSON depuis PowerShell vers l'entrée standard du producteur Kafka exécuté dans le conteneur ;
- recherche limitée aux index training-logs-* ;
- remplacement de la query-string Lucene par une requête JSON term exacte sur validation_id.keyword.
