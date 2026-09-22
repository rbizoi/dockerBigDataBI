# Installation Windows 11 / Docker Desktop

1. Docker Desktop doit être démarré en mode Linux containers.
2. Décompresser le dossier dans un chemin court, par exemple `C:\dev\BigData`.
3. Ouvrir PowerShell dans ce dossier.
4. Exécuter :

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\Test-PowerShellSyntax.ps1
.\Install-BigDataLab.ps1 -Reset -Full
```

Après le message de succès, double-cliquez sur `OPEN_JUPYTER.cmd` pour ouvrir
JupyterLab avec le jeton généré automatiquement. Le notebook d'introduction est
`spark\notebooks\01_demarrage_spark.ipynb`.

Aucun seuil de RAM hôte ne bloque l'installation. Si Docker manque réellement de mémoire pendant l'exécution, le diagnostic indiquera `OOMKilled=true` pour le conteneur concerné.

Ne mélangez pas cette distribution avec des fichiers V5.x.
