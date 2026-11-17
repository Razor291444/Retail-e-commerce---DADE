# Contrats de navigation frontend

Issue #4 est implémentée dans `Frontend_web/`, l'application React/Vite existante du dépôt. Le navigateur ne contacte jamais les ports internes : les clients REST et GraphQL construisent leurs requêtes depuis les variables `VITE_*` et ajoutent `Authorization`, `X-Request-ID` et les clés d'idempotence.

## Routes Web

| Route | Rôles | Appels |
|---|---|---|
| `#/overview` | admin, catalog_manager, analyst, logistics | agrégats (mock fallback), stocks et alertes |
| `#/orders` | admin, analyst, logistics | `GET /api/orders`, `GET /api/orders/{id}` |
| `#/catalog` | tous (écriture admin/catalog_manager) | `POST /graphql` `products`, `POST /api/auth/login` |
| `#/logistics` | admin, analyst, logistics | `GET/PUT /api/inventory/{id}`, `POST /api/inventory/reserve` |
| `#/observability` | admin, analyst | health gateway/services, pipeline Kafka |
| `#/access` | admin | matrice RBAC et utilisateurs `auth.users` |
| `#/login` | public | `POST /api/auth/login` |

## Routes Mobile

| Route | Appel / événement |
|---|---|
| `#/mobile-login` | téléphone + OTP (`inputmode=numeric`, `autocomplete=one-time-code`) |
| `#/mobile-catalog` | GraphQL `products`, recherche/catégories, `CART_ADD`, `PAGE_VIEW` |
| `#/mobile-scan` | saisie/scanner code-barres, query `productByBarcode`, événement `QR_SCAN` |
| `#/mobile-product` | détail nutritionnel, allergènes, TerroirDirect, quantité |
| `#/mobile-cart` | calcul prix B2B par paliers, avertissement au-dessus de 200 €, `CHECKOUT_START` |
| `#/mobile-checkout` | `POST /api/orders`, protection double-tap, étapes de Saga |
| `#/mobile-orders` | frise `PENDING -> PAID -> PREPARING -> DELIVERED` ou compensation |

## Réponses gérées

Les composants partagés affichent explicitement `200/201`, `401` session expirée avec tentative de refresh via `/auth/refresh`, `403` RBAC, `409` stock ou suppression, `422`/`PAYMENT_FAILED` Saga, `429` rate limit et `503` circuit breaker. Les appels `POST /api/orders` et `POST /api/payments` réutilisent une UUID persistée en session pour empêcher les doubles soumissions.

## Configuration et écart avec la cible `/v1`

Le dépôt actuel expose `/api/auth`, `/api/orders`, `/api/inventory`, `/api/payments` et `/graphql`, et Traefik écoute le port 80 dans le réseau Docker (publié via `localhost`). Les valeurs par défaut de `.env.example` reflètent ces contrats réels. Une gateway versionnée `/v1` peut être adoptée sans changer le code en positionnant `VITE_REST_BASE_PATH=/v1` et `VITE_GRAPHQL_PATH=/v1/graphql` après ajout des routeurs correspondants.
