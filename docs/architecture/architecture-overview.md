# ReMarket — Architecture et organisation du projet

## 1. Présentation du projet

**ReMarket** est une marketplace dédiée à la vente.

Le projet repose sur une architecture en microservices. Chaque service est responsable d'un domaine fonctionnel précis et communique avec les autres composants par l'intermédiaire d'API REST et/ou de messages asynchrones + d'API GraphQL.

L'application utilise plusieurs technologies complémentaires :

| Composant | Technologie | Rôle |
|---|---|---|
| Frontend Web | React, TypeScript et Vite | Interface utilisateur web |
| Backend | Java et Spring Boot | Logique métier et API REST |
| Base relationnelle | PostgreSQL | Stockage des données structurées |
| Base documentaire | MongoDB | Stockage du catalogue de produits |
| Communication asynchrone | RabbitMQ | Échange d'événements entre les services |
| Gateway | NGINX | Point d'entrée et routage des requêtes HTTP |
| Conteneurisation | Docker et Docker Compose | Déploiement et lancement des composants |
| Tests | JUnit, Mockito, Postman et outils complémentaires | Vérification du fonctionnement de l'application |
| Application mobile future | React Native, Expo et TypeScript | Accès à la marketplace depuis un appareil mobile |

L'objectif de cette architecture est de séparer les responsabilités, de faciliter le développement en équipe et de permettre l'évolution indépendante des différentes fonctionnalités.

---

## 2. Vue d'ensemble de l'arborescence

Le dépôt Git est organisé autour des composants suivants :

```text
ReMarket/
├── README.md
├── .gitignore
├── .editorconfig
├── .env.example
├── docker-compose.yml
├── Plateforme_API/
├── Gateway/
├── Frontend_Web/
├── Test/
├── Storage/
├── infrastructure/
├── docs/
└── mobile/
```

Chaque dossier possède une responsabilité spécifique :

- **`Plateforme_API/`** : contient les microservices backend.
- **`Gateway/`** : contient la configuration du reverse proxy NGINX.
- **`Frontend_Web/`** : contient l'application web React.
- **`Test/`** : regroupe les tests transversaux et les collections de tests API.
- **`Storage/`** : contient les scripts de création, de migration et d'initialisation des bases de données.
- **`infrastructure/`** : contient les configurations des composants techniques partagés, notamment RabbitMQ.
- **`docs/`** : regroupe la documentation technique et fonctionnelle.
- **`mobile/`** : est destiné à accueillir la future application mobile.
- **`docker-compose.yml`** : décrit les conteneurs et leurs dépendances.
- **`.env.example`** : documente les variables d'environnement nécessaires.
- **`.gitignore`** : définit les fichiers qui ne doivent pas être suivis par Git.
- **`.editorconfig`** : harmonise les règles de formatage du code entre les développeurs.
- **`README.md`** : présente le projet et explique comment l'installer et le lancer.

---

## 3. Organisation des microservices — `Plateforme_API/`

Le backend est divisé en cinq microservices indépendants, développés avec Java et Spring Boot.

Chaque microservice possède son propre fichier `pom.xml`, son propre `Dockerfile` et son propre répertoire de tests.

Cette organisation permet de séparer les fonctionnalités métier et de limiter les dépendances entre les composants.

### 3.1. `auth-service/` — Authentification et gestion des utilisateurs

Ce service est responsable de l'authentification et de la gestion des comptes utilisateurs.

Ses principales fonctionnalités sont :

- Inscription et connexion des utilisateurs.
- Gestion des rôles et des autorisations.
- Génération et validation des jetons JWT.
- Protection des fonctionnalités nécessitant une authentification.

Les données relationnelles de ce service sont stockées dans PostgreSQL.

Le dossier `security/` contient les éléments liés à la sécurité, tandis que `controller/`, `service/` et `repository/` séparent les différentes couches applicatives.

### 3.2. `catalog-service/` — Catalogue des produits

Ce service gère les produits disponibles sur la marketplace.

Ses principales fonctionnalités sont :

- Création, consultation, modification et suppression des produits.
- Gestion des catégories et des descriptions.
- Gestion des caractéristiques propres à chaque type de produit.
- Recherche et filtrage des produits.
- Consultation des prix et de l'état des produits.

Les données du catalogue sont stockées dans MongoDB.

Le dossier `document/` contient les classes représentant les documents MongoDB. Le dossier `repository/` permet d'accéder aux données, tandis que `service/` contient les règles métier du catalogue.

### 3.3. `order-service/` — Gestion des commandes

Ce service gère le cycle de vie des commandes.

Ses principales fonctionnalités sont :

- Création d'une commande.
- Gestion des lignes de commande et des quantités.
- Calcul du montant total.
- Suivi du statut de la commande.
- Consultation de l'historique des commandes d'un utilisateur.
- Coordination avec les services de stock et de paiement.

Les commandes et leurs lignes sont stockées dans PostgreSQL.

Le dossier `messaging/` contient les composants nécessaires à la communication asynchrone avec RabbitMQ.

Une commande peut notamment passer par les statuts suivants :

`PENDING` → `CONFIRMED` → `PAID` → `SHIPPED`

Des statuts supplémentaires, tels que `CANCELLED`, permettent de gérer les annulations. Les transitions exactes devront être définies dans les règles métier.

### 3.4. `payment-service/` — Gestion des paiements

Ce service est responsable du traitement et du suivi des paiements.

Pour le projet, les paiements pourront être simulés afin de tester différents scénarios sans utiliser de véritable prestataire de paiement.

Ses principales fonctionnalités sont :

- Enregistrement d'une tentative de paiement.
- Simulation d'un paiement accepté ou refusé.
- Mise à jour du statut du paiement.
- Communication du résultat aux autres services.
- Gestion des erreurs et prévention du traitement multiple d'une même opération.

Les paiements sont stockés dans PostgreSQL.

Les statuts peuvent notamment être `PENDING`, `SUCCEEDED`, `FAILED` et `REFUNDED`.

### 3.5. `inventory-service/` — Gestion des stocks

Ce service est responsable de la disponibilité des produits.

Ses principales fonctionnalités sont :

- Consultation des quantités disponibles.
- Gestion des stocks par produit et par entrepôt.
- Réservation du stock lors d'une commande.
- Libération du stock après une annulation ou un échec de paiement.
- Prévention des ventes dépassant les quantités disponibles.

Les données de stock sont stockées dans PostgreSQL.

Le service doit garantir la cohérence des quantités, notamment lorsque plusieurs clients commandent simultanément le même produit.

### 3.6. Organisation interne d'un microservice

Les microservices suivent une organisation commune lorsque cela est pertinent.

```text
service/
├── pom.xml
├── Dockerfile
└── src/
    ├── main/
    │   ├── java/com/remarket/<service>/
    │   │   ├── controller/
    │   │   ├── service/
    │   │   ├── repository/
    │   │   ├── entity/ ou document/
    │   │   ├── dto/
    │   │   ├── exception/
    │   │   └── <Service>Application.java
    │   └── resources/
    │       └── application.yml
    └── test/
```

Le rôle des principaux dossiers est le suivant :

| Dossier | Responsabilité |
|---|---|
| `controller/` | Expose les endpoints HTTP et reçoit les requêtes. |
| `service/` | Contient les règles métier. |
| `repository/` | Permet l'accès à la base de données. |
| `entity/` | Contient les entités relationnelles utilisées avec JPA. |
| `document/` | Contient les documents utilisés avec MongoDB. |
| `dto/` | Définit les objets échangés avec les clients ou les autres services. |
| `security/` | Regroupe les composants de sécurité lorsqu'ils sont nécessaires. |
| `messaging/` | Regroupe les composants de communication par messages lorsque le service utilise RabbitMQ. |
| `exception/` | Centralise la gestion des erreurs. |
| `resources/` | Contient les fichiers de configuration et les autres ressources applicatives. |
| `test/` | Contient les tests unitaires et les tests propres au service. |

Tous les dossiers ne sont pas obligatoires dans chaque microservice. Leur présence dépend des besoins réels du service concerné.

---

## 4. Gateway — `Gateway/`

Le dossier `Gateway/` contient la configuration de NGINX, utilisé comme reverse proxy.

Il constitue le point d'entrée HTTP commun du frontend vers les API backend.

Les requêtes sont redirigées vers le microservice correspondant en fonction du chemin demandé.

Exemple de routage :

| Chemin | Service cible |
|---|---|
| `/api/auth/**` | `auth-service` |
| `/api/products/**` | `catalog-service` |
| `/api/orders/**` | `order-service` |
| `/api/payments/**` | `payment-service` |
| `/api/inventory/**` | `inventory-service` |

Le dossier contient :

- `nginx.conf` : configuration principale de NGINX.
- `Dockerfile` : instructions de construction du conteneur NGINX.
- `conf.d/default.conf` : configuration des routes et des serveurs virtuels.

Cette organisation centralise le routage HTTP et évite au frontend de devoir connaître directement l'adresse de chaque microservice.

NGINX ne remplace cependant pas les mécanismes d'authentification et d'autorisation des services backend.

---

## 5. Frontend Web — `Frontend_Web/`

Le frontend est développé avec React, TypeScript et Vite.

Il fournit l'interface graphique permettant aux utilisateurs d'interagir avec la marketplace.

### 5.1. Organisation des fichiers

```text
Frontend_Web/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── Dockerfile
├── public/
└── src/
    ├── assets/
    ├── components/
    ├── pages/
    ├── layouts/
    ├── services/
    ├── hooks/
    ├── types/
    ├── utils/
    ├── App.tsx
    └── main.tsx
```

| Dossier ou fichier | Responsabilité |
|---|---|
| `assets/` | Images, icônes et autres ressources statiques. |
| `components/` | Composants réutilisables de l'interface. |
| `pages/` | Pages principales de l'application. |
| `layouts/` | Structures communes aux pages. |
| `services/` | Fonctions permettant d'appeler les API backend. |
| `hooks/` | Hooks React personnalisés. |
| `types/` | Types et interfaces TypeScript. |
| `utils/` | Fonctions utilitaires partagées. |
| `App.tsx` | Composant racine de l'application. |
| `main.tsx` | Point d'entrée de l'application React. |

### 5.2. Fonctionnalités de l'interface

Le frontend pourra notamment proposer :

- Une page d'accueil.
- Un catalogue avec recherche et filtres.
- Des fiches détaillées des produits.
- Des pages d'inscription et de connexion.
- Un panier.
- Un parcours de commande.
- Une page de suivi des commandes.
- Un espace personnel.
- Des interfaces de gestion pour les administrateurs, selon le périmètre retenu.

Les appels HTTP sont centralisés dans `services/`, afin de séparer la logique de communication avec le backend des composants visuels.

---

## 6. Tests — `Test/`

Le dossier `Test/` regroupe principalement les tests qui couvrent plusieurs composants ou l'application dans son ensemble.

Les tests propres à chaque microservice restent dans son répertoire `src/test/`.

### 6.1. `integration/`

Contient les tests d'intégration destinés à vérifier le fonctionnement conjoint de plusieurs composants, par exemple un service avec sa base de données.

### 6.2. `e2e/`

Contient les tests de bout en bout qui reproduisent des parcours complets.

Exemple : un utilisateur se connecte, consulte un produit, passe une commande et vérifie le résultat du paiement.

### 6.3. `performance/`

Contient les tests destinés à évaluer les performances de l'application, notamment le temps de réponse des API sous une charge donnée.

### 6.4. `postman/`

Contient les collections Postman permettant de tester les endpoints REST.

Le fichier `remarket-api-collection.json` pourra regrouper les requêtes nécessaires pour tester les fonctionnalités de chaque service.

### 6.5. Outils de test

Les principaux outils envisagés sont :

- **JUnit** pour les tests Java.
- **Mockito** pour simuler les dépendances dans les tests unitaires.
- **Spring Boot Test** pour les tests des applications Spring.
- **Postman** pour les tests des API.
- **Playwright**, si nécessaire, pour automatiser les parcours de l'interface web.

L'objectif est de vérifier les fonctionnalités individuellement, puis de s'assurer que les différents composants fonctionnent correctement ensemble.

---

## 7. Gestion des bases de données — `Storage/`

Le dossier `Storage/` regroupe les scripts permettant de créer, d'initialiser et de faire évoluer les bases de données.

Les données relationnelles sont stockées dans PostgreSQL, tandis que le catalogue est stocké dans MongoDB.

### 7.1. PostgreSQL — `Storage/postgres/`

```text
postgres/
├── init/
│   └── 01-create-schemas.sql
├── migrations/
│   ├── auth/
│   ├── orders/
│   ├── payments/
│   └── inventory/
└── seeds/
    ├── users.sql
    ├── warehouses.sql
    └── stock.sql
```

#### `init/`

Contient les scripts d'initialisation, par exemple la création des schémas PostgreSQL.

#### `migrations/`

Contient les scripts qui font évoluer la structure de la base.

Les migrations sont organisées par domaine afin de faciliter leur lecture et leur maintenance.

Les migrations peuvent être exécutées par Flyway, utilisé dans les microservices concernés. Les scripts de migration doivent être versionnés et ordonnés pour garantir que les environnements de développement et de test disposent d'une structure cohérente.

#### `seeds/`

Contient les données initiales nécessaires au développement et aux démonstrations, telles que des utilisateurs de test, des entrepôts et des stocks.

Les scripts de données de démonstration ne doivent pas contenir de mots de passe réels ni de données personnelles sensibles.

### 7.2. MongoDB — `Storage/mongodb/`

```text
mongodb/
├── init/
│   └── 01-create-collections.js
├── indexes/
│   └── catalog-indexes.js
└── seeds/
    └── products.json
```

#### `init/`

Contient les scripts d'initialisation de MongoDB.

#### `indexes/`

Contient les scripts de création des index nécessaires aux recherches du catalogue.

#### `seeds/`

Contient des exemples de produits pouvant être importés pour les tests et les démonstrations.

La collection principale sera `catalog`. Les documents pourront contenir le nom du produit, sa description, sa catégorie, son prix et ses caractéristiques.

### 7.3. Génération de données — `Storage/data-generator/`

Ce dossier contient les scripts permettant de générer des jeux de données synthétiques.

Les fichiers envisagés sont :

- `generate_products.py` : génération des produits.
- `generate_users.py` : génération des utilisateurs.
- `generate_orders.py` : génération des commandes.
- `requirements.txt` : dépendances Python nécessaires.
- `README.md` : instructions d'utilisation.

Les données générées doivent respecter les relations métier. Par exemple, une commande doit référencer des produits existants, son montant total doit correspondre à ses lignes et les quantités en stock ne doivent pas devenir négatives.

Des scénarios particuliers pourront également être générés : paiement refusé, rupture de stock, commande annulée ou réservation expirée.

---

## 8. Infrastructure — `infrastructure/`

Ce dossier regroupe les configurations des composants techniques qui ne correspondent pas directement à un domaine métier.

### 8.1. `rabbitmq/`

Contient les fichiers de configuration de RabbitMQ.

Le fichier `definitions.json` pourra décrire les exchanges, les files d'attente et les bindings nécessaires aux communications asynchrones.

RabbitMQ permet aux services d'échanger des événements sans imposer que tous les traitements soient exécutés dans une seule requête HTTP.

Par exemple :

1. Le service de commande enregistre une nouvelle commande.
2. Un événement `OrderCreated` est publié.
3. Le service de stock traite l'événement et tente de réserver les quantités nécessaires.
4. Le service de paiement simule le traitement du paiement.
5. Le résultat du paiement est communiqué aux services concernés.
6. La commande est confirmée ou annulée selon le résultat du processus.

Le flux exact devra être défini et implémenté par l'équipe. Les messages doivent être traités de manière idempotente, car un événement peut être reçu plusieurs fois.

### 8.2. `monitoring/`

Contient la documentation et, si nécessaire, les configurations liées à la supervision de l'application.

Cette partie peut rester minimale au début du projet. Elle pourra être complétée si la supervision et la collecte des métriques font partie des objectifs retenus.

---

## 9. Documentation — `docs/`

Le dossier `docs/` regroupe la documentation technique détaillée du projet.

```text
docs/
├── architecture/
│   ├── architecture-overview.md
│   └── diagrams/
├── database/
│   ├── postgresql-schema.md
│   └── mongodb-model.md
├── api/
│   └── openapi/
├── events/
│   └── rabbitmq-events.md
└── user-guide.md
```

### 9.1. `architecture/`

Décrit l'architecture générale, les responsabilités des microservices, les dépendances entre les composants et les principaux flux de communication.

Le sous-dossier `diagrams/` contient les diagrammes d'architecture, de séquence ou de déploiement.

### 9.2. `database/`

Documente le modèle relationnel PostgreSQL et le modèle documentaire MongoDB.

### 9.3. `api/`

Regroupe les spécifications OpenAPI des API REST, lorsqu'elles sont générées ou exportées.

Ces spécifications facilitent la compréhension des endpoints et le travail parallèle entre le frontend et le backend.

### 9.4. `events/`

Documente les événements RabbitMQ, leurs producteurs, leurs consommateurs et les données échangées.

### 9.5. `user-guide.md`

Explique comment utiliser les principales fonctionnalités de la marketplace.

Cette documentation peut également servir de support pour la démonstration finale.

---

## 10. Application mobile future — `mobile/`

Le dossier `mobile/` est prévu pour accueillir une application mobile développée avec React Native, Expo et TypeScript.

Il pourra être ajouté lorsque les principales fonctionnalités de l'application web seront opérationnelles.

Son organisation reprendra certains principes du frontend web :

| Dossier | Responsabilité |
|---|---|
| `components/` | Composants d'interface réutilisables. |
| `screens/` | Écrans de l'application mobile. |
| `services/` | Appels aux API backend. |
| `hooks/` | Hooks React personnalisés. |
| `types/` | Types TypeScript partagés ou adaptés. |
| `utils/` | Fonctions utilitaires. |

L'application mobile utilisera les mêmes API backend que le frontend web.

Cela permet de conserver une seule implémentation des règles métier et d'éviter de développer un backend distinct pour le mobile.

Certaines logiques TypeScript pourront être partagées entre les deux applications, mais les composants visuels devront être adaptés à React Native.

---

## 11. Configuration à la racine du dépôt

### 11.1. `README.md`

Présente le projet, les technologies utilisées, les prérequis et les étapes d'installation.

Il constitue le point d'entrée de la documentation pour les développeurs.

### 11.2. `.gitignore`

Liste les fichiers qui ne doivent pas être suivis par Git.

Il doit notamment exclure :

- Les fichiers `.env` contenant des secrets.
- Les fichiers compilés.
- Les dépendances installées localement.
- Les fichiers temporaires des IDE.
- Les journaux et autres fichiers générés.

### 11.3. `.editorconfig`

Définit des règles communes de formatage, telles que l'encodage UTF-8, les fins de ligne et l'indentation.

Il permet de réduire les différences de formatage entre les membres de l'équipe.

### 11.4. `.env.example`

Documente les variables d'environnement nécessaires au lancement du projet.

Il contient des exemples ou des valeurs fictives, mais aucun secret réel.

Chaque développeur peut copier ce fichier vers `.env` et renseigner ses propres paramètres.

Le fichier `.env` réel doit être ignoré par Git.

### 11.5. `docker-compose.yml`

Décrit les conteneurs nécessaires au lancement de l'application.

Il pourra orchestrer :

- PostgreSQL.
- MongoDB.
- RabbitMQ.
- Les cinq microservices.
- NGINX.
- Le frontend web, si celui-ci est conteneurisé.

Docker Compose facilite la mise en place d'un environnement de développement reproductible pour l'ensemble de l'équipe.

### 11.6. `pom.xml` et `Dockerfile`

Chaque microservice possède son propre `pom.xml`, qui définit ses dépendances Maven et sa configuration de compilation.

Chaque microservice possède également un `Dockerfile`, qui décrit la construction de son image Docker.

Le `Dockerfile` de NGINX et celui du frontend web sont conservés dans leurs dossiers respectifs.

---

## 12. Architecture générale et communication

L'architecture repose sur deux modes de communication complémentaires.

### 12.1. Communication synchrone : REST/JSON

Les appels REST sont utilisés lorsque le client a besoin d'une réponse immédiate.

Par exemple :

- Le frontend demande la liste des produits au `catalog-service`.
- Le frontend demande les détails d'une commande à l'`order-service`.
- Le frontend transmet les informations de connexion à l'`auth-service`.

Les requêtes HTTP passent par NGINX, qui les redirige vers le service correspondant.

### 12.2. Communication asynchrone : RabbitMQ

RabbitMQ est utilisé pour les traitements qui peuvent être déclenchés par des événements.

Par exemple :

- Création d'une commande.
- Réservation de stock.
- Résultat d'un paiement.
- Annulation d'une commande et libération du stock.

Ce fonctionnement permet de découpler les traitements, mais nécessite de gérer les erreurs, les nouvelles tentatives, les messages dupliqués et les états intermédiaires.

### 12.3. Bases de données

Chaque domaine possède la responsabilité de ses propres données.

| Domaine | Stockage |
|---|---|
| Authentification et utilisateurs | PostgreSQL |
| Catalogue | MongoDB |
| Commandes | PostgreSQL |
| Paiements | PostgreSQL |
| Stocks et réservations | PostgreSQL |

Les services ne doivent pas modifier directement les tables appartenant à un autre service.

Les références entre les données de différents services sont gérées au niveau applicatif. Les contraintes de clé étrangère SQL restent réservées aux relations internes à une même base et à un même périmètre de données.

---

## 13. Principes de développement

Pour maintenir une architecture claire et fiable, les principes suivants sont recommandés.

1. **Séparation des responsabilités :** chaque microservice gère un domaine métier précis.
2. **Faible couplage :** les services communiquent par des API ou des événements plutôt que par un accès direct aux données des autres services.
3. **Configuration externalisée :** les identifiants, mots de passe et paramètres sensibles sont fournis par des variables d'environnement.
4. **Sécurité :** les endpoints sensibles nécessitent une authentification et des autorisations adaptées.
5. **Tests :** chaque fonctionnalité importante est accompagnée de tests appropriés.
6. **Documentation :** les API, les événements et les modèles de données sont documentés.
7. **Reproductibilité :** Docker Compose et les scripts d'initialisation permettent de reconstruire l'environnement.
8. **Cohérence métier :** les commandes, les paiements et les stocks doivent rester cohérents malgré les erreurs ou les traitements asynchrones.
9. **Évolutivité :** les nouveaux composants, notamment l'application mobile, réutilisent les API existantes lorsque cela est pertinent.

---

## 14. Ordre de développement recommandé

Le développement peut être réalisé progressivement :

1. Mettre en place le dépôt Git et les fichiers de configuration.
2. Configurer Docker Compose, PostgreSQL, MongoDB et RabbitMQ.
3. Préparer les scripts de création et de migration des bases.
4. Développer le `catalog-service`.
5. Développer l'`auth-service`.
6. Développer l'`inventory-service` et l'`order-service`.
7. Développer le `payment-service` avec une simulation de paiement.
8. Configurer NGINX pour centraliser l'accès aux API.
9. Développer le frontend web.
10. Mettre en place les événements RabbitMQ et les tests d'intégration.
11. Ajouter et tester la fonctionnalité bonus.
12. Finaliser la documentation et préparer la démonstration.
13. Développer l'application mobile lorsque le périmètre et le temps disponible le permettent.

Cette progression permet de valider les fondations techniques avant de multiplier les fonctionnalités.

---

## 15. Conclusion

L'architecture de ReMarket sépare l'interface utilisateur, les services métier, les bases de données et l'infrastructure technique.

Les cinq microservices couvrent les principales fonctionnalités de la marketplace : authentification, catalogue, commandes, paiements et gestion des stocks.

PostgreSQL assure le stockage des données relationnelles, MongoDB permet de représenter les produits aux caractéristiques variables, RabbitMQ gère les échanges asynchrones et NGINX centralise le routage HTTP.

Enfin, Docker Compose facilite le lancement de l'ensemble, tandis que les dossiers `Test/` et `docs/` permettent de valider et de documenter le fonctionnement du projet.

Cette organisation constitue une base évolutive pour une marketplace web, avec la possibilité d'ajouter une application mobile réutilisant les mêmes API.