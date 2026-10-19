# Apache Druid : faits dénormalisés

Ce profil ajoute Apache Druid au laboratoire sans modifier le démarrage normal. Il charge le jeu `data/input/sales.csv` dans une datasource analytique au grain d'une ligne par vente.

## Démarrer Druid

Depuis la racine du dépôt :

```powershell
docker compose -f compose.yaml -f compose.druid.yaml --profile druid up -d druid-metadata druid-zookeeper druid-coordinator druid-broker druid-historical druid-middlemanager druid-router
```

La console Druid est disponible sur [http://localhost:8889](http://localhost:8889). Le profil Druid demande environ 6 à 8 Go de mémoire Docker disponibles. Il n'est pas lancé avec le profil principal.

## Charger l'exemple

Attendez que les services Druid soient prêts, puis lancez :

```powershell
.\druid\Load-DruidSales.ps1
```

Le chargeur soumet la spécification `ingestion/sales-fact.json` à Druid et attend la fin du traitement. Le fichier source est monté en lecture seule dans le conteneur d'indexation.

## Modèle analytique

La datasource `sales_fact_denormalized` conserve une ligne par vente et inclut directement ses attributs de filtrage BI :

- mesures : `quantity`, `unit_price`, `discount`, `amount` ;
- dimensions : `customer_id`, `country`, `product_id`, `product_name`, `category` ;
- horodatage : `event_ts`, converti en `__time` par Druid.

Le rollup est désactivé pour préserver le grain transactionnel du fichier. Il n'y a donc aucune jointure de dimension dans les requêtes BI. Ce jeu de formation a déjà les attributs produit et pays dans chaque ligne ; pour une source normalisée, enrichissez les faits avec les dimensions avant ou pendant l'ingestion. Les lookups Druid conviennent aux petits mappings devant toujours afficher leur valeur courante, mais ils ne conservent pas d'historique.

Exemple de requête dans l'éditeur SQL de Druid :

```sql
SELECT
  TIME_FLOOR("__time", 'P1M') AS mois,
  category,
  SUM(amount) AS chiffre_affaires,
  SUM(quantity) AS quantite
FROM sales_fact_denormalized
GROUP BY 1, 2
ORDER BY 1, 2
```

## Arrêter

```powershell
docker compose -f compose.yaml -f compose.druid.yaml --profile druid stop druid-router druid-middlemanager druid-historical druid-broker druid-coordinator druid-zookeeper druid-metadata
```

Les données du métastore et les segments Druid restent dans leurs volumes nommés.
