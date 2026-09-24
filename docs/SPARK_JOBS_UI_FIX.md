# Correction de l'accès à Spark Jobs UI

## Cause observée dans le dépôt

Le driver des notebooks s'exécute dans le service `spark-jupyter`, mais le
port de son interface Spark UI était publié dans la section `spark-master` :

```yaml
spark-master:
  ports:
    - "127.0.0.1:${SPARK_JOBS_UI_PORT:-14040}:14040"
```

Aucun processus de jobs Jupyter n'écoute dans `spark-master` sur ce port. Le
navigateur Windows atteignait donc le mauvais conteneur. Certains notebooks
contenaient en plus les hôtes internes `spark-jupyter` ou
`jupiter.olimp.fr`, qui ne sont pas des adresses valides pour le navigateur
local.

## Correction

- Spark utilise son port interne standard `4040` ;
- la publication `127.0.0.1:${SPARK_JOBS_UI_PORT:-4040}:4040` appartient à
  `spark-jupyter` ;
- `.env.example` déclare `SPARK_JOBS_UI_PORT=4040` ;
- `OPEN_SPARK_JOBS.cmd` refuse d'ouvrir une page trompeuse lorsqu'aucune
  `SparkSession` n'est active ;
- les installateurs vérifient que le port 4040 appartient bien à
  `spark-jupyter` ;
- les notebooks et la documentation utilisent l'URL Windows
  `http://127.0.0.1:4040`.

## Utilisation

Lancez d'abord une `SparkSession` dans Jupyter, puis :

```text
OPEN_SPARK_JOBS.cmd
```

Après l'arrêt de la session, l'interface temps réel disparaît normalement. Les
applications terminées restent accessibles sur le History Server, port 18083.
