# ReMarket

Marketplace alimentaire basée sur Open Food Facts.

## Stack

- Python 3.13 + FastAPI pour Auth, Catalogue, Commandes, Stock et Paiement
- GraphQL Strawberry + MongoDB pour le catalogue
- PostgreSQL partagé avec un schéma par domaine transactionnel
- Traefik comme API Gateway
- React + TypeScript + Vite pour le frontend

## Démarrage

```powershell
docker compose up --build
```

Applications :

| Composant | Accès |
|---|---|
| Frontend React | http://localhost:3000 |
| Gateway Traefik | http://localhost |
| Dashboard Traefik | http://localhost:8088 |
| Auth REST direct | http://localhost:8081 |
| Catalogue GraphQL direct | http://localhost:8082/graphql |

Les services exposent aussi `/health`. Par exemple :

```powershell
Invoke-RestMethod http://localhost:8081/health
Invoke-RestMethod http://localhost:8082/health
docker compose ps
```

## Catalogue Open Food Facts

Le catalogue est exclusivement stocké dans MongoDB. PostgreSQL conserve
uniquement `integration.product_mapping`, qui relie le code-barres et le
`product_id` utilisé par les commandes et le stock.

Pour préparer un export JSONL :

```powershell
.\.venv\Scripts\python `
  Storage\data-generator\open_food_facts_to_postgres.py `
  --input "C:\data\openfoodfacts.jsonl" `
  --mapping-file "C:\data\product-mapping.json" `
  --mongo-output "C:\data\products-normalized.json" `
  --limit 10000
```

Le générateur charge automatiquement `POSTGRES_DB`, `POSTGRES_USER` et
`POSTGRES_PASSWORD` depuis le fichier `.env` à la racine. Les variables déjà
présentes dans la session PowerShell restent prioritaires.

Puis importer MongoDB :

```powershell
mongoimport --uri mongodb://localhost:27017/remarket `
  --collection products --file C:\data\products-normalized.json --jsonArray
```

Le fichier [create_schema_and_tables.sql](<C:/Users/Ruben Mougoué/Desktop/Retail-e-commerce---DADE/Storage/postgres/create_schema_and_tables.sql>) est conservé comme référence SQL Server historique. Docker utilise le script PostgreSQL dédié [init_postgres.sql](<C:/Users/Ruben Mougoué/Desktop/Retail-e-commerce---DADE/Storage/postgres/init_postgres.sql>).

MongoDB utilise deux comptes distincts : `MONGO_INITDB_ROOT_USERNAME` /
`MONGO_INITDB_ROOT_PASSWORD` pour administrer MongoDB et
`CATALOG_MONGO_USER` / `CATALOG_MONGO_PASSWORD` pour l'application catalogue.
Le script `mongo_init.js` doit être exécuté avec le premier compte.
