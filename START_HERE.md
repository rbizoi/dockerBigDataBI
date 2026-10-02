# Démarrage Windows et Linux

La procédure actuelle est dans [README.md](README.md). Aucun fichier Shell, PowerShell ou CMD n’est requis.

```text
docker compose --profile full build
docker compose --profile full up -d
docker compose --profile checks run --rm integration-check --full
docker compose --profile checks run --rm airflow-check
```

Portail : http://localhost:8090. Les deux commandes de contrôle doivent réussir.
