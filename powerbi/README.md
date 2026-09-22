# Power BI et Trino

Power BI Desktop reste installé sur Windows et ne fait pas partie du Compose.

## Point d'architecture

La connexion directe Power BI -> Trino n'est pas supposée « native et universelle » dans ce kit. Les options dépendent de votre environnement :

1. pilote ODBC/JDBC Trino/Starburst ou tiers validé ;
2. passerelle/produit d'entreprise fournissant un connecteur Power BI certifié ;
3. matérialisation d'un Data Mart vers une base officiellement supportée par Power BI ;
4. import de fichiers d'extraction pour un TP découplé du choix de pilote.

## Chemin garanti pour la formation : export CSV depuis Trino

Après avoir exécuté les jobs Spark/Iceberg :

Linux / WSL :

```bash
./scripts/linux/export_powerbi_csv.sh
```

Windows PowerShell :

```powershell
.\scripts\windows\Export-PowerBI.ps1
```

Deux fichiers sont créés :

- `powerbi/output/sales_summary.csv`
- `powerbi/output/sales_detail.csv`

Dans Power BI Desktop, utilisez **Obtenir les données -> Texte/CSV**. Ce chemin
est volontairement simple et reproductible pour le cours : la logique SQL reste
exécutée dans Trino, tandis que le transport vers Power BI ne dépend d'aucun
pilote tiers.

## Pour une architecture d'entreprise

Pour du DirectQuery ou du rafraîchissement automatisé, validez explicitement le
pilote/connector, la passerelle Power BI, l'authentification, le chiffrement TLS,
la gestion des identités et les performances. Une alternative fréquente consiste
à matérialiser un Data Mart dans une cible BI supportée nativement.

Ne pas présenter Trino comme un Data Warehouse physique : il est la couche SQL
distribuée/fédérée au-dessus des données.
