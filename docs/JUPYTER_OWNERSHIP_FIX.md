# Correction des permissions d'enregistrement JupyterLab

## Symptôme

JupyterLab est accessible, mais l'enregistrement d'un notebook échoue avec :

```text
PermissionError: [Errno 13] Permission denied:
'/home/spark/.local/share/jupyter/notebook_secret'
```

Le sous-dossier `runtime` appartient à `spark:spark`, alors que son parent
`/home/spark/.local/share/jupyter` appartient à `root:root`.

## Cause

La création d'un chemin imbriqué avec `install -d -o spark -g spark` applique le
propriétaire demandé au répertoire final, mais les parents créés implicitement
peuvent conserver `root:root`. Jupyter peut alors démarrer grâce à `runtime`,
mais ne peut pas créer `notebook_secret` dans son répertoire de données.

## Correction FIXED9

- `chown -R spark:spark /home/spark` pendant le build ;
- permissions privées sur toute l'arborescence XDG/Jupyter ;
- `JUPYTER_DATA_DIR` explicite ;
- `user: spark` explicite dans Compose ;
- contrôle de l'utilisateur effectif dans l'installateur ;
- création et suppression de fichiers de test dans le dossier Jupyter et le
  dossier persistant des notebooks.

Jupyter n'est jamais exécuté comme root.
