# ReMarket

Marketplace alimentaire basée sur Open Food Facts, FastAPI, GraphQL Strawberry,
PostgreSQL, MongoDB, Traefik et React/Vite.

## Prérequis

- Docker Desktop démarré
- Docker Compose v2 (`docker compose version`)
- Git, si le dépôt doit être cloné

## Démarrage rapide

Depuis la racine du dépôt :

```powershell
Copy-Item .env.example .env
docker compose --env-file .env up --build
```

Le premier démarrage peut prendre quelques minutes. Pour lancer les services
en arrière-plan :

```powershell
docker compose --env-file .env up --build -d
```

Vérifier l'état des conteneurs :

```powershell
docker compose ps
```

Arrêter la plateforme :

```powershell
docker compose down
```

Pour supprimer également les données locales PostgreSQL et MongoDB :

```powershell
docker compose down -v
```

## URLs

| Composant | URL |
|---|---|
| Application React | http://localhost:3000 |
| API Gateway Traefik | http://localhost:8080 |
| Dashboard Traefik | http://localhost:8088 |
| Auth REST direct (diagnostic uniquement) | http://localhost:8081 |
| Catalogue GraphQL direct (diagnostic uniquement) | http://localhost:8082/graphql |

L'application frontend utilise la gateway. Les ports directs des
microservices sont réservés au diagnostic local.

## Frontend seul

Pour développer le frontend sans Docker :

```powershell
Set-Location .\Frontend_web
npm install
npm run dev
```

Puis ouvrir http://localhost:5173. Les variables frontend sont documentées
dans [Frontend_web/.env.example](<C:/Users/Admin/Downloads/Efrei/New folder/Data Use Case/Projet/Retail-e-commerce---DADE/Frontend_web/.env.example>).
Le mode `VITE_ENABLE_MOCK_FALLBACK=true` permet d'utiliser les données de
démonstration si les services backend ne sont pas encore disponibles.

## Vérifications rapides

```powershell
Invoke-RestMethod http://localhost:8081/health
Invoke-RestMethod http://localhost:8082/health
docker compose logs -f frontend
```

Dans l'interface, les comptes de démonstration `admin`, `catalog_manager`,
`analyst` et `logistics` sont disponibles depuis l'écran de connexion.

## Données et catalogue

Le catalogue est stocké dans MongoDB. PostgreSQL conserve les données
transactionnelles et les relations d'intégration. Le schéma PostgreSQL utilisé
par Docker se trouve dans
[Storage/postgres/market_postgres_schema.sql](<C:/Users/Admin/Downloads/Efrei/New folder/Data Use Case/Projet/Retail-e-commerce---DADE/Storage/postgres/market_postgres_schema.sql>).

Pour importer un fichier JSONL dans MongoDB :

```powershell
mongoimport --uri mongodb://localhost:27017/remarket `
  --collection catalog `
  --file C:\data\products-normalized.json `
  --jsonArray
```

Les contrats de navigation frontend sont décrits dans
[NAVIGATION_CONTRACTS.md](<C:/Users/Admin/Downloads/Efrei/New folder/Data Use Case/Projet/Retail-e-commerce---DADE/NAVIGATION_CONTRACTS.md>).
