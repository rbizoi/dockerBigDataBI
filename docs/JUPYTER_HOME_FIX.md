# Correction du redémarrage JupyterLab

## Symptôme

Le service `spark-jupyter` reste en état `Restarting (1)` puis l'installateur
signale qu'il n'est pas devenu sain.

## Cause confirmée

Dans l'image Spark amont, l'utilisateur non privilégié `spark` peut avoir
`/nonexistent` comme dossier personnel. Jupyter Core tente alors de créer :

```text
/nonexistent/.local/share/jupyter/runtime
```

La création échoue avec `PermissionError: [Errno 13] Permission denied`, puis
Jupyter quitte avec le code 1. La stratégie `restart: unless-stopped` provoque
ensuite une boucle de redémarrage.

Ce défaut n'est lié ni à la mémoire disponible, ni au master Spark, ni aux
workers.

## Correction FIXED7

- création de `/home/spark` dans l'image ;
- propriétaire `spark:spark` et permissions privées pour les répertoires de travail ;
- définition explicite de `HOME`, des variables XDG et des chemins Jupyter ;
- vérification du propriétaire pendant le build ;
- maintien de l'exécution non privilégiée avec `USER spark`.

L'image Spark doit être reconstruite pour appliquer cette correction.
