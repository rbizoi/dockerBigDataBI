# Big Data & BI Training Lab — COMPLETE STABLE

Cette distribution est une reconstruction propre. Elle ne nécessite aucun patch V5.x.

## Installation complète recommandée

Dans PowerShell :

```powershell
cd C:\dev\BigData
Set-ExecutionPolicy -Scope Process Bypass
.\Install-BigDataLab.ps1 -Reset -Full
```

Ou double-cliquez sur `INSTALL_RESET_FULL.cmd`.

Le contrôle de quantité de RAM hôte est **désactivé**. Les limites mémoire de chaque conteneur restent présentes pour éviter qu'un service monopolise Docker Desktop.

## Installation du cœur uniquement

```powershell
.\Install-BigDataLab.ps1 -Reset
```

Le cœur valide obligatoirement : PostgreSQL, Kafka, RustFS/S3, Iceberg REST, Spark Master + 2 Workers, Spark History Server avec journaux S3, JupyterLab/PySpark, Parquet, Delta, Iceberg et Trino.

## Ouvrir JupyterLab

Après une installation réussie, double-cliquez sur `OPEN_JUPYTER.cmd`. Le
navigateur reçoit automatiquement le jeton généré dans `.env`. Le notebook
`01_demarrage_spark.ipynb` est prêt à utiliser le cluster distribué.

## Vérification ultérieure

```powershell
.\Verify-BigDataLab.ps1
```

## Critère de succès

L'installation n'est considérée réussie que si elle termine par :

```text
INSTALLATION VALIDATED SUCCESSFULLY
```

En cas d'échec, un rapport est généré automatiquement dans `reports\`.
