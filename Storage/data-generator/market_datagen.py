#!/usr/bin/env python3
"""market_datagen.py : générateur modulaire de données pour Market.

Génère, sans fichier Open Food Facts :
  - la collection MongoDB `catalog` (produits alimentaires synthétiques, TOUS avec
    la MÊME image_url : --image-url) ;
  - les tables PostgreSQL : entrepôts, stock, clients, commandes, lignes,
    paiements, réservations, et (option) utilisateurs de démo.

Architecture (chaque bloc est remplaçable) :
  générateurs  generate_catalog / build_stock / build_customers / iter_order_chunks
  cibles       MongoSink, PostgresSink, FilesSink (JSONL + CSV), DryRunSink
  pipeline     run() : relie les générateurs aux cibles
  contrôle     verify() : cohérence des données dans PostgreSQL

Reproductibilité : même --seed + mêmes volumes = mêmes données. Chaque étape a sa
propre graine dérivée, donc changer --orders ne change pas le catalogue.
Les codes-barres générés sont des EAN-13 valides du préfixe 200-299 (usage interne
GS1) : ils ne peuvent pas entrer en collision avec de vrais produits.

Profils de volume (--profile) : small, demo (défaut), large. Tout paramètre
explicite (--products, --orders...) l'emporte. Un fichier JSON (--config) peut
fournir les mêmes paramètres ; la ligne de commande l'emporte sur le fichier.

Exemples :
    python market_datagen.py --dry-run
    python market_datagen.py --targets files --export-dir out --profile small
    python market_datagen.py --targets mongo,postgres --reset --with-auth-users
    python market_datagen.py --targets postgres --catalog-source mongo --reset   # catalogue Open Food Facts déjà chargé

Prérequis : mongo_init.js et market_postgres_schema.sql déjà exécutés.
Dépendances : pymongo (cible mongo ou source mongo), psycopg[binary] (cible postgres),
              argon2-cffi (seulement avec --with-auth-users).
Variables d'environnement : DATABASE_URL, POSTGRES_*, MONGO_URI, MONGO_DB,
CATALOG_MONGO_*, MARKET_IMAGE_URL, SEED_DEMO_PASSWORD. Les variables sont
chargées depuis le fichier `.env` situé à la racine du dépôt, sans écraser les
variables déjà définies dans l'environnement.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import itertools
import json
import math
import os
import random
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

# Image unique pour tous les produits. Service externe : remplacez-la par une image
# hébergée par vos soins (--image-url ou MARKET_IMAGE_URL) pour ne plus en dépendre.
DEFAULT_IMAGE_URL = "https://placehold.co/400x400/png?text=Market"


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE entries without overwriting environment variables."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def postgres_url_from_environment() -> str | None:
    """Build PostgreSQL's URL from POSTGRES_* variables when DATABASE_URL is absent."""
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    database = os.getenv("POSTGRES_DB")
    if not all((user, password, database)):
        return None
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}@"
        f"{host}:{port}/{quote_plus(database)}"
    )


def mongo_uri_from_environment() -> str:
    """Build MongoDB's service-user URI when MONGO_URI is absent."""
    if os.getenv("MONGO_URI"):
        return os.environ["MONGO_URI"]
    user = os.getenv("CATALOG_MONGO_USER")
    password = os.getenv("CATALOG_MONGO_PASSWORD")
    database = os.getenv("MONGO_DB", "market")
    if user and password:
        return (
            f"mongodb://{quote_plus(user)}:{quote_plus(password)}"
            f"@localhost:27017/{database}?authSource={database}"
        )
    return "mongodb://localhost:27017"

PROFILES = {
    "small": {"products": 500, "customers": 300, "orders": 3_000, "days": 30},
    "demo": {"products": 5_000, "customers": 5_000, "orders": 50_000, "days": 90},
    "large": {"products": 50_000, "customers": 20_000, "orders": 500_000, "days": 90},
}

PARIS = ZoneInfo("Europe/Paris")
AMOUNT_LIMIT_CENTS = 20_000  # le service Paiement refuse au-dessus de 200 €

# Ordre = ordre de chargement compatible avec les clés étrangères.
TABLE_COLUMNS = {
    "inventory.warehouse": ["id", "name", "city", "capacity_units"],
    "orders.customers": ["id", "name", "email", "auth_user_id", "created_at"],
    "orders.orders": ["id", "customer_id", "status", "total_cents", "currency", "created_at", "updated_at"],
    "orders.order_items": ["id", "order_id", "order_created_at", "product_id", "product_name", "quantity", "unit_price_cents"],
    "payments.payments": ["id", "order_id", "amount_cents", "currency", "status", "failure_reason", "idempotency_key", "created_at", "updated_at"],
    "inventory.stock": ["product_id", "warehouse_id", "quantity", "reserved_quantity", "reorder_threshold"],
    "inventory.reservations": ["id", "order_id", "product_id", "warehouse_id", "quantity", "status", "created_at", "updated_at", "expires_at"],
}

# ===========================================================================
# 1. GÉNÉRATEUR DE CATALOGUE (MongoDB)
# ===========================================================================
GROUP_BANDS = {  # fourchettes de prix en centimes par groupe PNNS
    "beverages": (80, 450), "fruits-and-vegetables": (90, 700), "milk-and-dairy-products": (70, 600),
    "cereals-and-potatoes": (80, 500), "composite-foods": (250, 900), "fat-and-sauces": (120, 800),
    "fish-meat-eggs": (300, 1500), "sugary-snacks": (100, 600), "salty-snacks": (120, 500),
}

# (groupe, sous-catégorie, produits de base, variantes de format,
#  macros pour 100 g : (lipides, dont saturés, glucides, dont sucres, fibres, protéines, sel),
#  groupes NOVA possibles, ingrédients, allergènes)
TAXONOMY = [
    ("beverages", "waters", ["Eau minérale naturelle", "Eau gazeuse", "Eau de source"], ["1,5 L", "6 x 1,5 L", "50 cl", "1 L"],
     (0, 0, 0, 0, 0, 0, 0.01), (1,), "Eau minérale naturelle", []),
    ("beverages", "fruit-juices", ["Jus d'orange", "Jus de pomme", "Jus multifruits", "Nectar d'abricot", "Jus de raisin"], ["pur jus 1 L", "à base de concentré 1 L", "bio 1 L", "pressé 75 cl"],
     (0.1, 0, 10.5, 10, 0.3, 0.5, 0.01), (1, 3), "Jus de fruits, vitamine C", []),
    ("beverages", "sodas", ["Limonade", "Cola", "Boisson gazeuse à l'orange", "Thé glacé pêche"], ["1,5 L", "6 x 33 cl", "sans sucres 1,5 L", "2 L"],
     (0, 0, 10, 10, 0, 0, 0.01), (4,), "Eau gazéifiée, sucre, arômes naturels, acidifiant", []),
    ("fruits-and-vegetables", "fresh-fruits", ["Pommes Gala", "Bananes", "Fraises", "Raisins blancs", "Poires Conférence"], ["1 kg", "500 g", "barquette 250 g", "bio 1 kg"],
     (0.3, 0.1, 12, 10, 2.4, 0.8, 0.01), (1,), "Fruit frais", []),
    ("fruits-and-vegetables", "vegetables", ["Carottes", "Courgettes", "Tomates grappe", "Haricots verts", "Salade mélange"], ["1 kg", "500 g", "sachet 250 g", "bio 500 g"],
     (0.3, 0.1, 5, 3, 2.5, 1.5, 0.05), (1,), "Légume frais", []),
    ("fruits-and-vegetables", "canned-vegetables", ["Petits pois carottes", "Maïs doux", "Haricots rouges"], ["boîte 400 g", "bocal 345 g", "lot de 3"],
     (0.5, 0.1, 10, 2, 4, 4, 0.6), (3,), "Légumes, eau, sel", []),
    ("milk-and-dairy-products", "yogurts", ["Yaourt nature", "Yaourt aux fruits", "Yaourt à la grecque", "Skyr nature"], ["pot 125 g", "x 4", "x 8", "bio x 4"],
     (2, 1.3, 5, 4.5, 0, 4, 0.1), (3,), "Lait, ferments lactiques", ["en:milk"]),
    ("milk-and-dairy-products", "cheeses", ["Camembert", "Emmental râpé", "Comté", "Chèvre frais", "Mozzarella"], ["250 g", "200 g", "portion 150 g", "AOP 200 g"],
     (25, 16, 0.5, 0.5, 0, 22, 1.6), (3,), "Lait, sel, présure, ferments", ["en:milk"]),
    ("milk-and-dairy-products", "milks", ["Lait demi-écrémé", "Lait entier", "Lait d'avoine"], ["1 L", "6 x 1 L", "bio 1 L"],
     (1.6, 1, 4.8, 4.8, 0, 3.3, 0.1), (1, 3), "Lait", ["en:milk"]),
    ("cereals-and-potatoes", "breads", ["Baguette tradition", "Pain de mie complet", "Pain aux céréales"], ["400 g", "500 g", "tranché 600 g"],
     (3, 0.5, 48, 3, 5, 9, 1.2), (3,), "Farine de blé, eau, sel, levain", ["en:gluten"]),
    ("cereals-and-potatoes", "pasta-rice", ["Spaghetti", "Penne", "Riz basmati", "Riz long grain", "Semoule fine"], ["500 g", "1 kg", "bio 500 g"],
     (1.5, 0.3, 72, 3, 3, 12, 0.02), (1, 3), "Semoule de blé dur", ["en:gluten"]),
    ("cereals-and-potatoes", "breakfast-cereals", ["Flocons d'avoine", "Muesli croustillant", "Céréales chocolatées"], ["500 g", "750 g", "bio 500 g"],
     (8, 2, 65, 18, 7, 9, 0.4), (3, 4), "Céréales complètes, sucre, cacao", ["en:gluten"]),
    ("composite-foods", "ready-meals", ["Lasagnes bolognaise", "Hachis parmentier", "Quiche lorraine", "Gratin dauphinois", "Couscous royal"], ["400 g", "300 g", "2 portions 600 g"],
     (9, 4, 17, 2.5, 1.8, 8, 1.1), (4,), "Viande, légumes, sauce, fromage", ["en:gluten", "en:milk"]),
    ("composite-foods", "soups", ["Soupe de légumes", "Velouté de potiron", "Soupe à l'oignon"], ["brique 1 L", "bol 300 ml"],
     (1.5, 0.5, 5, 2.5, 1.5, 1.2, 0.7), (3, 4), "Légumes, eau, crème", ["en:milk"]),
    ("composite-foods", "pizzas", ["Pizza margherita", "Pizza 4 fromages", "Pizza jambon champignons"], ["surgelée 350 g", "fraîche 400 g"],
     (10, 4.5, 29, 3, 2, 11, 1.3), (4,), "Farine de blé, tomate, fromage", ["en:gluten", "en:milk"]),
    ("fat-and-sauces", "oils", ["Huile d'olive vierge extra", "Huile de tournesol", "Huile de colza"], ["50 cl", "1 L", "75 cl"],
     (100, 14, 0, 0, 0, 0, 0), (2,), "Huile végétale", []),
    ("fat-and-sauces", "sauces", ["Mayonnaise", "Ketchup", "Sauce tomate basilic", "Moutarde de Dijon", "Vinaigrette"], ["300 g", "430 g", "bocal 400 g"],
     (20, 2, 10, 6, 1, 1, 1.8), (4,), "Huile, vinaigre, tomate, épices", ["en:eggs", "en:mustard"]),
    ("fat-and-sauces", "butters", ["Beurre doux", "Beurre demi-sel"], ["250 g", "500 g"],
     (82, 52, 0.5, 0.5, 0, 0.6, 0.05), (2,), "Crème pasteurisée", ["en:milk"]),
    ("fish-meat-eggs", "meats", ["Blanc de poulet", "Steak haché 5% MG", "Jambon blanc", "Saucisses de Strasbourg", "Rôti de porc"], ["x 4 tranches", "barquette 500 g", "x 2", "400 g"],
     (5, 2, 0.5, 0.5, 0, 22, 1.4), (1, 3, 4), "Viande, sel", []),
    ("fish-meat-eggs", "fish", ["Filet de saumon", "Thon en conserve", "Cabillaud surgelé", "Sardines à l'huile"], ["x 2 pavés", "boîte 160 g", "400 g"],
     (10, 2, 0, 0, 0, 21, 0.8), (1, 3), "Poisson, sel", ["en:fish"]),
    ("fish-meat-eggs", "eggs", ["Oeufs frais", "Oeufs bio", "Oeufs plein air"], ["boîte de 6", "boîte de 12", "x 10"],
     (10, 3, 1, 1, 0, 13, 0.35), (1,), "Oeufs", ["en:eggs"]),
    ("sugary-snacks", "chocolate", ["Tablette de chocolat noir", "Tablette de chocolat au lait", "Pâte à tartiner noisettes", "Barre chocolatée"], ["100 g", "200 g", "400 g", "x 6"],
     (32, 19, 55, 52, 3, 6, 0.1), (4,), "Sucre, cacao, beurre de cacao, lait", ["en:milk", "en:nuts"]),
    ("sugary-snacks", "biscuits", ["Biscuits sablés", "Cookies pépites de chocolat", "Gaufrettes", "Madeleines"], ["200 g", "300 g", "x 10"],
     (20, 10, 63, 28, 2, 6, 0.5), (4,), "Farine de blé, sucre, beurre, oeufs", ["en:gluten", "en:milk", "en:eggs"]),
    ("sugary-snacks", "confectionery", ["Bonbons gélifiés", "Caramels tendres", "Guimauves"], ["sachet 200 g", "300 g"],
     (0.5, 0.1, 78, 60, 0, 4, 0.05), (4,), "Sirop de glucose, sucre, gélatine, arômes", []),
    ("salty-snacks", "chips", ["Chips nature", "Chips à l'ancienne", "Chips paprika"], ["150 g", "200 g", "x 3"],
     (32, 3, 50, 0.5, 4, 6, 1.4), (4,), "Pommes de terre, huile, sel", []),
    ("salty-snacks", "crackers", ["Biscuits apéritif fromage", "Crackers", "Cacahuètes grillées salées"], ["100 g", "250 g"],
     (22, 8, 55, 3, 3, 10, 2), (4,), "Farine de blé, huile, fromage, sel", ["en:gluten", "en:peanuts"]),
]
QUALIFIERS = ["", "", "", "gourmand", "léger", "bio", "premium", "origine France", "recette traditionnelle", "format familial"]
BRANDS = [  # marques fictives
    "Maison Dupré", "Les Vergers du Sud", "Fermes de Bretagne", "Nature & Saveurs", "Moulin de Provence",
    "Délices du Terroir", "La Belle Récolte", "Saveurs d'Antan", "Fruits d'Occitanie", "Domaine des Prés",
    "Le Panier Frais", "Atelier Gourmand", "Terre & Mer", "Les Régals", "Pâturages d'Auvergne",
    "Côté Jardin", "Maison Lefèvre", "Bon Matin", "La Ferme Dorée", "Petit Marché",
    "Éclat d'Alsace", "Grand Terroir", "Source Pure", "Market Sélection",
]

_ENERGY_KJ = [335 * i for i in range(1, 11)]
_SUGARS = [4.5 * i for i in range(1, 11)]
_SAT_FAT = [float(i) for i in range(1, 11)]
_SODIUM_MG = [90 * i for i in range(1, 11)]
_FIBER = [0.9, 1.9, 2.8, 3.7, 4.7]
_PROTEIN = [1.6, 3.2, 4.8, 6.4, 8.0]


def _points(value: float, thresholds: list[float]) -> int:
    return sum(1 for t in thresholds if value > t)


def nutriscore_grade(sub: str, n: dict[str, float]) -> str:
    """Approximation du Nutri-Score (aliments solides) : à ne pas prendre comme référence."""
    if sub in ("waters", "fresh-fruits", "vegetables"):
        return "a"
    if sub == "fruit-juices":
        return "d"
    if sub == "sodas":
        return "b" if n["sugars_100g"] < 1 else "e"
    negative = (
        _points(n["energy-kcal_100g"] * 4.184, _ENERGY_KJ) + _points(n["sugars_100g"], _SUGARS)
        + _points(n["saturated-fat_100g"], _SAT_FAT) + _points(n["salt_100g"] * 400, _SODIUM_MG)
    )
    positive = _points(n["fiber_100g"], _FIBER) + (0 if negative >= 11 else _points(n["proteins_100g"], _PROTEIN))
    score = negative - positive
    return "a" if score <= -1 else "b" if score <= 2 else "c" if score <= 10 else "d" if score <= 18 else "e"


def _ean13(rng: random.Random, used: set[str]) -> str:
    while True:
        digits = [int(c) for c in f"{rng.randint(200, 299)}{rng.randrange(10**9):09d}"]
        check = (10 - sum(d * (3 if i % 2 else 1) for i, d in enumerate(digits)) % 10) % 10
        code = "".join(map(str, digits)) + str(check)
        if code not in used:
            used.add(code)
            return code


def _nutriments(macros: tuple, rng: random.Random) -> dict[str, float]:
    fat, sat, carbs, sugars, fiber, protein, salt = macros

    def jitter(value: float, digits: int = 1) -> float:
        return round(value * rng.uniform(0.75, 1.25), digits) if value else 0.0

    fat, carbs, fiber, protein = jitter(fat), jitter(carbs), jitter(fiber), jitter(protein)
    sat, sugars, salt = min(jitter(sat), fat), min(jitter(sugars), carbs), jitter(salt, 2)
    kcal = round(9 * fat + 4 * carbs + 4 * protein + 2 * fiber)
    return {
        "energy-kcal_100g": kcal, "fat_100g": fat, "saturated-fat_100g": sat,
        "carbohydrates_100g": carbs, "sugars_100g": sugars, "fiber_100g": fiber,
        "proteins_100g": protein, "salt_100g": salt,
    }


def generate_catalog(args: argparse.Namespace, now: datetime) -> list[dict[str, Any]]:
    """Documents conformes au validator de mongo_init.js ; image_url identique partout."""
    rng = random.Random(f"{args.seed}:catalog")
    used: set[str] = set()
    docs = []
    for i in range(args.products):
        group, sub, bases, variants, macros, nova, ingredients, allergens = rng.choice(TAXONOMY)
        base, variant, qualifier = rng.choice(bases), rng.choice(variants), rng.choice(QUALIFIERS)
        nutriments = _nutriments(macros, rng)
        organic = qualifier == "bio" or "bio" in variant.split()
        low, high = GROUP_BANDS[group]
        created = now - timedelta(days=rng.randint(0, 730), seconds=rng.randint(0, 86_399))
        attributes = {
            "nutriscore_grade": nutriscore_grade(sub, nutriments),
            "nova_group": rng.choice(nova),
            "quantity": variant,
            "ingredients_text": ingredients,
            "allergens_tags": allergens,
            "labels_tags": ["en:organic", "fr:ab-agriculture-biologique"] if organic else [],
            "countries_tags": ["en:france"],
            "categories": [f"en:{group}", f"en:{sub}"],
            "nutriments": nutriments,
        }
        docs.append({
            "product_id": args.start_product_id + i,
            "barcode": _ean13(rng, used),
            "seller_id": None,
            "name": " ".join(p for p in (base, qualifier, variant) if p)[:200],
            "brand": rng.choice(BRANDS),
            "category": group,
            "subcategory": sub,
            "price_cents": int(rng.triangular(low, high, low + (high - low) * 0.25)) // 10 * 10 + 9,
            "currency": "EUR",
            "status": "inactive" if rng.random() < args.inactive_rate else "active",
            "image_url": args.image_url,  # UNE seule URL pour tous les produits
            "attributes": {k: v for k, v in attributes.items() if v not in (None, "", [], {})},
            "created_at": created,
            "updated_at": now,
        })
    return docs


def load_catalog_from_mongo(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Source alternative : réutilise un catalogue déjà présent (ex. issu d'Open Food Facts)."""
    from pymongo import MongoClient

    collection = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=5000)[args.mongo_db]["catalog"]
    cursor = collection.find({}, {"_id": 0, "product_id": 1, "name": 1, "price_cents": 1, "status": 1}).sort("product_id", 1)
    if args.products:
        cursor = cursor.limit(args.products)
    return list(cursor)


# ===========================================================================
# 2. GÉNÉRATEURS POSTGRESQL
# ===========================================================================
HOUR_WEIGHTS = [1, 1, 1, 1, 1, 2, 4, 8, 12, 14, 15, 16, 20, 22, 16, 14, 15, 17, 22, 26, 24, 16, 8, 3]
WEEKDAY_WEIGHTS = [1.0, 0.95, 0.95, 1.0, 1.1, 1.35, 1.25]
# (nom, ville, taux de remplissage visé) : Bordeaux > 90 % pour démontrer l'alerte saturation
WAREHOUSES = [
    ("Entrepôt Île-de-France", "Évry", 0.62),
    ("Entrepôt Rhône-Alpes", "Lyon", 0.78),
    ("Entrepôt Hauts-de-France", "Lille", 0.55),
    ("Entrepôt Nouvelle-Aquitaine", "Bordeaux", 0.93),
    ("Entrepôt Provence", "Marseille", 0.71),
]
WAREHOUSE_SHARE = [0.35, 0.20, 0.15, 0.15, 0.15]
FIRST_NAMES = [
    "Léa", "Lucas", "Emma", "Hugo", "Chloé", "Louis", "Jade", "Gabriel", "Manon", "Arthur",
    "Camille", "Jules", "Sarah", "Adam", "Inès", "Raphaël", "Louise", "Nathan", "Zoé", "Tom",
    "Alice", "Ethan", "Clara", "Noah", "Lola", "Paul", "Anaïs", "Maxime", "Eva", "Théo",
    "Julie", "Antoine", "Margaux", "Baptiste", "Océane", "Mathis", "Pauline", "Enzo", "Romane", "Yanis",
]
LAST_NAMES = [
    "Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit", "Durand", "Leroy", "Moreau",
    "Simon", "Laurent", "Lefebvre", "Michel", "Garcia", "David", "Bertrand", "Roux", "Vincent", "Fournier",
    "Morel", "Girard", "André", "Lefèvre", "Mercier", "Dupont", "Lambert", "Bonnet", "François", "Martinez",
    "Legrand", "Garnier", "Faure", "Rousseau", "Blanc", "Guérin", "Muller", "Henry", "Roussel", "Nicolas",
]
DEMO_USERS = [
    ("admin@market.example", "admin"), ("catalog@market.example", "catalog_manager"),
    ("analyst@market.example", "analyst"), ("logistics@market.example", "logistics"),
    ("svc-orders@market.example", "service_account"),
]
DEMO_CUSTOMER_EMAILS = [f"client{i}@market.example" for i in (1, 2, 3)]


def _ascii(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9-]", "", text)


def build_stock(products: list[dict[str, Any]], rng: random.Random):
    """(entrepôts, lignes de stock modifiables). Capacités calculées pour viser les taux de remplissage."""
    n_wh = len(WAREHOUSES)
    stock: list[list[int]] = []
    stored = [0] * n_wh
    for product in products:
        count = rng.choices([1, 2, 3], [0.6, 0.3, 0.1])[0]
        chosen: set[int] = set()
        while len(chosen) < count:
            chosen.add(rng.choices(range(1, n_wh + 1), WAREHOUSE_SHARE)[0])
        for wh in sorted(chosen):
            threshold = 20 if rng.random() < 0.2 else 10
            quantity = max(1, int(rng.lognormvariate(4.0, 0.9)))
            if rng.random() < 0.04:  # bientôt en rupture (ou déjà en rupture)
                quantity = rng.randint(0, threshold)
            stock.append([product["product_id"], wh, quantity, 0, threshold])
            stored[wh - 1] += quantity
    warehouses = [(i + 1, name, city, max(1, math.ceil(stored[i] / target))) for i, (name, city, target) in enumerate(WAREHOUSES)]
    return warehouses, stock


def build_customers(n: int, rng: random.Random, now: datetime) -> list[tuple]:
    rows = []
    for i in range(1, n + 1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        created = now - timedelta(days=rng.randint(91, 700), seconds=rng.randint(0, 86_399))
        rows.append((i, f"{first} {last}", f"{_ascii(first)}.{_ascii(last)}.{i}@example.com", None, created))
    return rows


def build_timestamps(n: int, days: int, now: datetime, rng: random.Random) -> list[datetime]:
    """n horodatages UTC triés, jamais dans le futur, avec profil horaire et hebdomadaire (heure de Paris)."""
    local_today = now.astimezone(PARIS).date()
    offsets = list(range(days))
    day_weights = [
        (1.0 + 0.5 * (1 - off / max(days - 1, 1))) * WEEKDAY_WEIGHTS[(local_today - timedelta(days=off)).weekday()]
        for off in offsets
    ]
    day_choices = rng.choices(offsets, cum_weights=list(itertools.accumulate(day_weights)), k=n)
    hour_cum = list(itertools.accumulate(HOUR_WEIGHTS))
    hour_choices = rng.choices(range(24), cum_weights=hour_cum, k=n)

    def make(off: int, hour: int) -> datetime:
        day = local_today - timedelta(days=off)
        local = datetime(day.year, day.month, day.day, hour, rng.randint(0, 59), rng.randint(0, 59), tzinfo=PARIS)
        return local.astimezone(timezone.utc)

    result = []
    for off, hour in zip(day_choices, hour_choices):
        ts, tries = make(off, hour), 0
        while ts > now and tries < 20:
            ts, tries = make(off, rng.choices(range(24), cum_weights=hour_cum)[0]), tries + 1
        if ts > now:
            ts = now - timedelta(seconds=rng.randint(1, 3 * 3600))
        result.append(ts)
    result.sort()
    return result


def decide(age: timedelta, total_cents: int, rng: random.Random) -> tuple[str, str | None, str | None]:
    """(statut commande, statut paiement ou None, motif d'échec)."""
    if age < timedelta(minutes=10) and rng.random() < 0.6:
        return "PENDING", None, None
    if total_cents > AMOUNT_LIMIT_CENTS:
        return "PAYMENT_FAILED", "FAILED", "amount_limit_exceeded"
    if rng.random() < 0.04:
        return "PAYMENT_FAILED", "FAILED", "card_declined"
    days = age.total_seconds() / 86_400
    if days > 4:
        return ("CANCELLED", "REFUNDED", None) if rng.random() < 0.03 else ("DELIVERED", "SUCCEEDED", None)
    if days > 1:
        return ("DELIVERED" if rng.random() < 0.55 else "PREPARING"), "SUCCEEDED", None
    return ("PAID" if rng.random() < 0.4 else "PREPARING"), "SUCCEEDED", None


_UPDATE_DELTA_SECONDS = {
    "PENDING": (0, 0), "PAYMENT_FAILED": (5, 40), "PAID": (5, 60),
    "PREPARING": (600, 10_800), "DELIVERED": (86_400, 259_200), "CANCELLED": (3_600, 172_800),
}


def iter_order_chunks(n_orders, n_customers, products, stock, timestamps, now, rng, chunk_size) -> Iterator[tuple[list, list, list, list]]:
    """Produit (commandes, lignes, paiements, réservations) par paquets ; met à jour reserved_quantity dans `stock`."""
    n_products = len(products)
    popularity = list(itertools.accumulate(1.0 / (i + 1) ** 0.8 for i in range(n_products)))
    by_product: dict[int, list[list[int]]] = {}
    for row in stock:
        by_product.setdefault(row[0], []).append(row)

    item_id = payment_id = reservation_id = 0
    for start in range(0, n_orders, chunk_size):
        orders, items, payments, reservations = [], [], [], []
        for index in range(start, min(start + chunk_size, n_orders)):
            order_id, ts = index + 1, timestamps[index]
            customer_id = min(n_customers, 1 + int(n_customers * rng.random() ** 1.8))

            picked: set[int] = set()
            wanted = min(1 + int(rng.expovariate(0.6)), 8, n_products)
            while len(picked) < wanted:
                picked.add(min(n_products - 1, bisect.bisect_left(popularity, rng.random() * popularity[-1])))
            bulk = rng.random() < 0.015  # grosses commandes : certaines dépassent 200 €

            lines, total = [], 0
            for product_index in sorted(picked):
                product = products[product_index]
                quantity = rng.randint(8, 25) if bulk else rng.choices([1, 2, 3, 4], [55, 25, 12, 8])[0]
                price = int(product["price_cents"])
                total += quantity * price
                lines.append((product, quantity, price))

            status, pay_status, reason = decide(now - ts, total, rng)
            low, high = _UPDATE_DELTA_SECONDS[status]
            updated = min(ts + timedelta(seconds=rng.randint(low, high)), now)
            orders.append((order_id, customer_id, status, total, "EUR", ts, updated))

            for product, quantity, price in lines:
                item_id += 1
                items.append((item_id, order_id, ts, product["product_id"], str(product["name"])[:200], quantity, price))

            if pay_status is not None:
                payment_id += 1
                paid_at = min(ts + timedelta(seconds=rng.randint(1, 5)), now)
                payments.append((payment_id, order_id, total, "EUR", pay_status, reason, f"seed-pay-{order_id}", paid_at, updated))

            # Saga : réservations en cours (PENDING) et compensations récentes (RELEASED)
            if status == "PENDING" or (status == "PAYMENT_FAILED" and now - ts < timedelta(days=1)):
                for product, quantity, _ in lines:
                    rows = by_product.get(product["product_id"])
                    if not rows:
                        continue
                    best = max(rows, key=lambda r: r[2] - r[3])
                    if status == "PENDING":
                        reserved = min(quantity, best[2] - best[3])
                        if reserved <= 0:
                            continue
                        best[3] += reserved
                        res_status = "RESERVED"
                    else:
                        reserved, res_status = quantity, "RELEASED"
                    reservation_id += 1
                    reservations.append((reservation_id, order_id, product["product_id"], best[1], reserved, res_status, ts, ts, ts + timedelta(minutes=15)))
        yield orders, items, payments, reservations


# ===========================================================================
# 3. CIBLES (sinks)
# ===========================================================================
class Sink:
    """Interface commune : une cible n'implémente que ce qu'elle sait écrire."""

    name = "sink"
    handles_catalog = False
    handles_tables = False

    def open(self) -> None: ...
    def write_catalog(self, docs: list[dict[str, Any]]) -> None: ...
    def write_table(self, table: str, rows: list) -> None: ...
    def finish(self) -> None: ...
    def close(self, ok: bool) -> None: ...


class DryRunSink(Sink):
    name = "dry-run"
    handles_catalog = handles_tables = True

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def write_catalog(self, docs): self.counts["mongo:catalog"] += len(docs)
    def write_table(self, table, rows): self.counts[table] += len(rows)
    def finish(self): print("Dry-run, aucune écriture :", dict(self.counts))


class MongoSink(Sink):
    name = "mongo"
    handles_catalog = True

    def __init__(self, uri: str, db_name: str, reset: bool) -> None:
        self.uri, self.db_name, self.reset, self.written = uri, db_name, reset, 0

    def open(self) -> None:
        from pymongo import MongoClient

        self.db = MongoClient(self.uri, serverSelectionTimeoutMS=5000)[self.db_name]
        if "catalog" not in self.db.list_collection_names():
            raise SystemExit("Collection 'catalog' absente : lancez d'abord mongo_init.js")
        if self.reset:
            self.db["catalog"].delete_many({})
        elif self.db["catalog"].count_documents({}, limit=1):
            raise SystemExit("La collection catalog contient déjà des données : relancez avec --reset.")

    def write_catalog(self, docs) -> None:
        from pymongo.errors import BulkWriteError

        try:
            for start in range(0, len(docs), 5000):
                self.db["catalog"].insert_many(docs[start:start + 5000], ordered=False)
        except BulkWriteError as error:
            print(json.dumps(error.details.get("writeErrors", [])[:3], default=str, indent=2), file=sys.stderr)
            raise SystemExit("Écriture MongoDB refusée (validator ou doublon) : voir ci-dessus.")
        self.written = len(docs)
        last = max((d["product_id"] for d in docs), default=0)
        update = {"$set": {"seq": last}} if self.reset else {"$max": {"seq": last}}
        self.db["counters"].update_one({"_id": "product_id"}, update, upsert=True)


RESET_SQL = """
TRUNCATE orders.order_items, orders.orders, orders.customers, orders.idempotency_keys, orders.outbox,
         payments.payments, payments.outbox,
         inventory.reservations, inventory.stock, inventory.warehouse, inventory.outbox
RESTART IDENTITY CASCADE
"""
RESET_AUTH_SQL = "TRUNCATE auth.refresh_tokens, auth.user_roles, auth.users RESTART IDENTITY CASCADE"
RESYNC_SQL = [
    "SELECT setval('orders.orders_id_seq', COALESCE((SELECT MAX(id) FROM orders.orders), 0) + 1, false)",
] + [
    f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE((SELECT MAX(id) FROM {t}), 0) + 1, false)"
    for t in ("orders.customers", "orders.order_items", "payments.payments", "inventory.warehouse", "inventory.reservations")
]


class PostgresSink(Sink):
    name = "postgres"
    handles_tables = True

    def __init__(self, url: str, reset: bool, with_auth_users: bool) -> None:
        self.url, self.reset, self.with_auth_users = url, reset, with_auth_users

    def open(self) -> None:
        import psycopg

        self.conn = psycopg.connect(self.url)
        self.cur = self.conn.cursor()
        self.cur.execute(
            "SELECT (SELECT count(*) FROM inventory.warehouse) + (SELECT count(*) FROM orders.customers)"
            " + (SELECT count(*) FROM orders.orders)"
        )
        if self.cur.fetchone()[0] and not self.reset:
            raise SystemExit("Des données existent déjà dans PostgreSQL : relancez avec --reset.")
        if self.reset:
            self.cur.execute(RESET_SQL)
            if self.with_auth_users:
                self.cur.execute(RESET_AUTH_SQL)

    def write_table(self, table, rows) -> None:
        cols = ", ".join(TABLE_COLUMNS[table])
        with self.cur.copy(f"COPY {table} ({cols}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)

    def seed_auth(self, password: str) -> None:
        try:
            from argon2 import PasswordHasher
        except ImportError:
            raise SystemExit("--with-auth-users nécessite argon2-cffi (pip install argon2-cffi)")
        hasher = PasswordHasher()

        def upsert(email: str, role: str) -> int:
            self.cur.execute(
                "INSERT INTO auth.users (email, password_hash) VALUES (%s, %s) "
                "ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash RETURNING id",
                (email, hasher.hash(password)),
            )
            user_id = self.cur.fetchone()[0]
            self.cur.execute(
                "INSERT INTO auth.user_roles (user_id, role_id) SELECT %s, id FROM auth.roles WHERE name = %s ON CONFLICT DO NOTHING",
                (user_id, role),
            )
            return user_id

        for email, role in DEMO_USERS:
            upsert(email, role)
        for customer_id, email in enumerate(DEMO_CUSTOMER_EMAILS, start=1):
            self.cur.execute(
                "UPDATE orders.customers SET email = %s, auth_user_id = %s WHERE id = %s",
                (email, upsert(email, "customer"), customer_id),
            )

    def finish(self) -> None:
        for sql in RESYNC_SQL:
            self.cur.execute(sql)
        if self.with_auth_users:
            self.cur.execute("SELECT setval(pg_get_serial_sequence('auth.users', 'id'), COALESCE((SELECT MAX(id) FROM auth.users), 0) + 1, false)")
        self.cur.execute("ANALYZE")  # indispensable avant vos démonstrations EXPLAIN

    def close(self, ok: bool) -> None:
        if not hasattr(self, "conn"):
            return
        self.conn.commit() if ok else self.conn.rollback()
        self.conn.close()


class FilesSink(Sink):
    """Écrit catalog.jsonl (mongoimport), un CSV par table et load_postgres.sql (\\copy)."""

    name = "files"
    handles_catalog = handles_tables = True

    def __init__(self, out_dir: str) -> None:
        self.dir = Path(out_dir)
        self.handles: dict[str, tuple[Any, Any]] = {}
        self.catalog_written = False

    def open(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _ejson(value: Any) -> Any:
        if isinstance(value, datetime):
            return {"$date": value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")}
        raise TypeError(f"Type non sérialisable : {type(value)}")

    def write_catalog(self, docs) -> None:
        with open(self.dir / "catalog.jsonl", "w", encoding="utf-8") as file:
            for doc in docs:
                file.write(json.dumps(doc, default=self._ejson, ensure_ascii=False) + "\n")
        self.catalog_written = True

    def write_table(self, table, rows) -> None:
        if table not in self.handles:
            file = open(self.dir / f"{table}.csv", "w", newline="", encoding="utf-8")
            writer = csv.writer(file, lineterminator="\n")
            writer.writerow(TABLE_COLUMNS[table])
            self.handles[table] = (file, writer)
        writer = self.handles[table][1]
        for row in rows:
            writer.writerow(["" if v is None else (v.isoformat() if isinstance(v, datetime) else v) for v in row])

    def finish(self) -> None:
        for file, _ in self.handles.values():
            file.close()
        self.handles.clear()
        lines = ["-- Chargement des CSV (psql, depuis ce dossier). Base vide ou après TRUNCATE.", "BEGIN;"]
        for table, cols in TABLE_COLUMNS.items():
            if (self.dir / f"{table}.csv").exists():
                lines.append(f"\\copy {table} ({', '.join(cols)}) FROM '{table}.csv' CSV HEADER")
        lines += [f"{sql};" for sql in RESYNC_SQL] + ["ANALYZE;", "COMMIT;"]
        (self.dir / "load_postgres.sql").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Fichiers écrits dans {self.dir}/ :")
        if self.catalog_written:
            print(f"  mongoimport --db market --collection catalog --file {self.dir}/catalog.jsonl")
        print(f"  cd {self.dir} && psql \"$DATABASE_URL\" -f load_postgres.sql")

    def close(self, ok: bool) -> None:
        for file, _ in self.handles.values():
            file.close()


# ===========================================================================
# 4. VÉRIFICATION D'INTÉGRITÉ (PostgreSQL)
# ===========================================================================
CHECKS = {
    "orders_total_differs_from_items": """
        SELECT count(*) FROM orders.orders o
        JOIN (SELECT order_id, sum(quantity::bigint * unit_price_cents) AS s FROM orders.order_items GROUP BY order_id) i
          ON i.order_id = o.id WHERE o.total_cents <> i.s""",
    "orders_without_items": """
        SELECT count(*) FROM orders.orders o WHERE NOT EXISTS (SELECT 1 FROM orders.order_items i WHERE i.order_id = o.id)""",
    "payments_amount_differs_from_order": """
        SELECT count(*) FROM payments.payments p JOIN orders.orders o ON o.id = p.order_id WHERE p.amount_cents <> o.total_cents""",
    "payments_without_order": """
        SELECT count(*) FROM payments.payments p WHERE NOT EXISTS (SELECT 1 FROM orders.orders o WHERE o.id = p.order_id)""",
    "payment_status_incoherent_with_order": """
        SELECT count(*) FROM payments.payments p JOIN orders.orders o ON o.id = p.order_id
        WHERE (p.status = 'FAILED') <> (o.status = 'PAYMENT_FAILED')""",
    "reservations_without_order": """
        SELECT count(*) FROM inventory.reservations r WHERE NOT EXISTS (SELECT 1 FROM orders.orders o WHERE o.id = r.order_id)""",
    "reserved_quantity_differs_from_active_reservations": """
        SELECT count(*) FROM inventory.stock s
        LEFT JOIN (SELECT product_id, warehouse_id, sum(quantity) AS q FROM inventory.reservations WHERE status = 'RESERVED' GROUP BY 1, 2) r
          USING (product_id, warehouse_id)
        WHERE s.reserved_quantity <> COALESCE(r.q, 0)""",
}


def verify(url: str, known_product_ids: set[int]) -> bool:
    import psycopg

    ok = True
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        print("\n== Intégrité PostgreSQL ==")
        for name, sql in CHECKS.items():
            cur.execute(sql)
            count = cur.fetchone()[0]
            ok &= count == 0
            print(f"{'OK ' if count == 0 else 'KO '} {name}: {count}")
        cur.execute("SELECT product_id FROM orders.order_items UNION SELECT product_id FROM inventory.stock")
        orphans = {r[0] for r in cur.fetchall()} - known_product_ids
        ok &= not orphans
        print(f"{'OK ' if not orphans else 'KO '} product_id inconnus du catalogue: {len(orphans)}")
        print("\n== Taux de remplissage des entrepôts ==")
        cur.execute("SELECT name, stored_units, capacity_units, fill_rate_pct, status FROM inventory.v_warehouse_fill ORDER BY warehouse_id")
        for name, stored, capacity, rate, status in cur.fetchall():
            print(f"{name:<30} {stored:>10,} / {capacity:>10,}  {rate:>5}%  {status}")
        print("\n== Commandes par statut ==")
        cur.execute("SELECT status, count(*) FROM orders.orders GROUP BY 1 ORDER BY 2 DESC")
        for status, count in cur.fetchall():
            print(f"{status:<16} {count:>10,}")
    print("\nRésultat :", "intégrité OK" if ok else "ANOMALIES DÉTECTÉES")
    return ok


# ===========================================================================
# 5. PIPELINE
# ===========================================================================
def build_sinks(args: argparse.Namespace) -> list[Sink]:
    if args.dry_run:
        return [DryRunSink()]
    sinks: list[Sink] = []
    for target in args.targets:
        if target == "mongo":
            sinks.append(MongoSink(args.mongo_uri, args.mongo_db, args.reset))
        elif target == "postgres":
            sinks.append(PostgresSink(args.database_url, args.reset, args.with_auth_users))
        elif target == "files":
            sinks.append(FilesSink(args.export_dir))
    return sinks


def run(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    if args.catalog_source == "synthetic":
        catalog = generate_catalog(args, now)
        write_catalog_docs = catalog
    else:
        catalog = load_catalog_from_mongo(args)
        write_catalog_docs = []
    sellable = [p for p in catalog if p.get("status", "active") == "active"]
    if not sellable:
        raise SystemExit("Aucun produit actif : augmentez --products ou baissez --inactive-rate.")
    known_ids = {p["product_id"] for p in sellable}
    print(f"Catalogue : {len(catalog):,} produits ({len(sellable):,} actifs), source={args.catalog_source}"
          + (f", image unique = {args.image_url}" if write_catalog_docs else ""))

    sinks = build_sinks(args)
    table_sinks = [s for s in sinks if s.handles_tables]
    catalog_sinks = [s for s in sinks if s.handles_catalog]

    def emit(table: str, rows: list) -> None:
        for sink in table_sinks:
            sink.write_table(table, rows)

    ok = False
    for sink in sinks:
        sink.open()
    try:
        for sink in catalog_sinks:
            if write_catalog_docs:
                sink.write_catalog(write_catalog_docs)

        if table_sinks:
            warehouses, stock = build_stock(sellable, random.Random(f"{args.seed}:stock"))
            emit("inventory.warehouse", warehouses)
            emit("orders.customers", build_customers(args.customers, random.Random(f"{args.seed}:customers"), now))

            rng = random.Random(f"{args.seed}:orders")
            pool = sellable[:]
            rng.shuffle(pool)  # le rang dans cette liste détermine la popularité du produit
            timestamps = build_timestamps(args.orders, args.days, now, rng)
            reservations_all: list[tuple] = []
            for orders, items, payments, reservations in iter_order_chunks(
                args.orders, args.customers, pool, stock, timestamps, now, rng, args.chunk_size
            ):
                emit("orders.orders", orders)
                emit("orders.order_items", items)
                emit("payments.payments", payments)
                reservations_all.extend(reservations)
            emit("inventory.stock", stock)  # après les commandes : reserved_quantity définitif
            emit("inventory.reservations", reservations_all)

            if args.with_auth_users:
                password = os.getenv("SEED_DEMO_PASSWORD")
                if not password:
                    raise SystemExit("--with-auth-users exige la variable d'environnement SEED_DEMO_PASSWORD")
                for sink in table_sinks:
                    if isinstance(sink, PostgresSink):
                        sink.seed_auth(password)
            print(f"Tables : {len(warehouses)} entrepôts, {len(stock):,} lignes de stock, {args.customers:,} clients, "
                  f"{args.orders:,} commandes, {len(reservations_all)} réservations.")
        for sink in sinks:
            sink.finish()
        ok = True
    finally:
        for sink in sinks:
            sink.close(ok)

    if ok and not args.dry_run and "postgres" in args.targets and args.verify:
        return 0 if verify(args.database_url, known_ids) else 1
    return 0


# ===========================================================================
# 6. LIGNE DE COMMANDE
# ===========================================================================
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", help="Fichier JSON de paramètres (la ligne de commande l'emporte)")
    known, _ = pre.parse_known_args(argv)

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, parents=[pre])
    p.add_argument("--profile", choices=sorted(PROFILES), default="demo")
    p.add_argument("--products", type=int, help="Produits à générer (ou à lire si --catalog-source mongo)")
    p.add_argument("--customers", type=int)
    p.add_argument("--orders", type=int)
    p.add_argument("--days", type=int, help="Fenêtre de dates des commandes (1 à 180)")
    p.add_argument("--inactive-rate", type=float, default=0.02, help="Part de produits archivés (défaut 0.02)")
    p.add_argument("--image-url", default=os.getenv("MARKET_IMAGE_URL", DEFAULT_IMAGE_URL),
                   help="URL unique de l'image de TOUS les produits")
    p.add_argument("--start-product-id", type=int, default=1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--catalog-source", choices=["synthetic", "mongo"], default="synthetic")
    p.add_argument("--targets", default="mongo,postgres", help="Liste parmi : mongo, postgres, files")
    p.add_argument("--export-dir", default="out")
    p.add_argument("--reset", action="store_true", help="Vide les données existantes de la cible avant écriture")
    p.add_argument("--with-auth-users", action="store_true", help="Utilisateurs de démo (SEED_DEMO_PASSWORD)")
    p.add_argument("--no-verify", dest="verify", action="store_false", help="Saute le contrôle d'intégrité")
    p.add_argument("--dry-run", action="store_true", help="Génère sans rien écrire")
    p.add_argument("--chunk-size", type=int, default=10_000)
    p.add_argument("--database-url", default=postgres_url_from_environment())
    p.add_argument("--mongo-uri", default=mongo_uri_from_environment())
    p.add_argument("--mongo-db", default=os.getenv("MONGO_DB", "market"))

    if known.config:
        data = json.loads(Path(known.config).read_text(encoding="utf-8"))
        unknown = set(data) - {a.dest for a in p._actions}
        if unknown:
            p.error(f"Paramètres inconnus dans {known.config} : {sorted(unknown)}")
        p.set_defaults(**data)
    args = p.parse_args(argv)

    for key, value in PROFILES[args.profile].items():
        if getattr(args, key) is None:
            setattr(args, key, value)
    args.targets = [t.strip() for t in str(args.targets).split(",") if t.strip()]
    if not set(args.targets) <= {"mongo", "postgres", "files"} or (not args.targets and not args.dry_run):
        p.error("--targets doit contenir mongo, postgres et/ou files")
    if "postgres" in args.targets and not args.dry_run and not args.database_url:
        p.error("DATABASE_URL (ou --database-url) est obligatoire pour la cible postgres : aucun mot de passe par défaut")
    if args.catalog_source == "mongo" and "mongo" in args.targets and not args.dry_run:
        p.error("--catalog-source mongo lit le catalogue : retirez 'mongo' de --targets")
    if args.products < 1 or args.customers < 3 or args.orders < 0 or not 1 <= args.days <= 180 or args.chunk_size < 1 \
            or not 0 <= args.inactive_rate < 1:
        p.error("Valeurs invalides : --products >= 1, --customers >= 3, --orders >= 0, 1 <= --days <= 180")
    if not args.image_url.startswith(("http://", "https://")):
        p.error("--image-url doit être une URL http(s)")
    return args


if __name__ == "__main__":
    sys.exit(run(parse_args()))