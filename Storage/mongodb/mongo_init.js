// =========================================================
// MARKET - Initialisation MongoDB (service Catalogue)
// Exécution avec mongosh, rejouable (idempotent) :
//
//   mongosh "$MONGO_ADMIN_URI" --file mongo_init.js
//
// Variables d'environnement lues (définies dans .env, jamais dans le dépôt) :
//   CATALOG_MONGO_PASSWORD   obligatoire
//   MONGO_DB                 défaut "market"
//   CATALOG_MONGO_USER       défaut "catalog_svc"
//
// Avec le conteneur officiel mongo, déposer ce fichier dans
// /docker-entrypoint-initdb.d/ : il ne s'exécute qu'au premier démarrage
// (volume vide). Pour le rejouer, utiliser la commande ci-dessus.
// =========================================================

const DB_NAME = process.env.MONGO_DB || "market";
const SVC_USER = process.env.CATALOG_MONGO_USER || "catalog_svc";
const SVC_PASSWORD = process.env.CATALOG_MONGO_PASSWORD;
const ROLE_NAME = "catalog_rw";

if (!SVC_PASSWORD) {
  throw new Error("CATALOG_MONGO_PASSWORD est obligatoire (voir .env)");
}

const mdb = db.getSiblingDB(DB_NAME);

// ---------------------------------------------------------
// 1. Collection "catalog" + validation du socle commun
//    Le champ "attributes" reste libre : c'est la raison d'être de MongoDB ici.
//    Les prix sont en centimes, comme dans PostgreSQL.
// ---------------------------------------------------------
const validator = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "product_id", "barcode", "name", "category",
      "price_cents", "currency", "status", "created_at", "updated_at",
    ],
    properties: {
      product_id:  { bsonType: ["int", "long"], minimum: 1,
                     description: "Identifiant attribué par l'application (lien logique avec PostgreSQL)" },
      barcode:     { bsonType: "string", pattern: "^[0-9]{8,14}$",
                     description: "Code-barres Open Food Facts (EAN-8/UPC/EAN-13/GTIN-14), chaîne pour garder les zéros" },
      seller_id:   { bsonType: ["int", "long", "null"],
                     description: "Réservé à une future place de marché multi-vendeurs" },
      name:        { bsonType: "string", minLength: 1, maxLength: 200 },
      brand:       { bsonType: ["string", "null"] },
      category:    { bsonType: "string", minLength: 1 },
      subcategory: { bsonType: ["string", "null"] },
      price_cents: { bsonType: ["int", "long"], minimum: 0 },
      currency:    { bsonType: "string", enum: ["EUR"] },
      status:      { enum: ["active", "inactive"],
                     description: "inactive = produit archivé (jamais supprimé s'il a été commandé)" },
      image_url:   { bsonType: ["string", "null"] },
      attributes:  { bsonType: "object" },
      created_at:  { bsonType: "date" },
      updated_at:  { bsonType: "date" },
    },
  },
};

const options = { validator, validationLevel: "strict", validationAction: "error" };

if (mdb.getCollectionNames().includes("catalog")) {
  mdb.runCommand({ collMod: "catalog", ...options });
  print("catalog : validator mis à jour");
} else {
  mdb.createCollection("catalog", options);
  print("catalog : collection créée");
}

// ---------------------------------------------------------
// 2. Index
// ---------------------------------------------------------
const catalog = mdb.getCollection("catalog");

// Unicité : MongoDB n'a pas de clé étrangère, ces deux index protègent le lien avec PostgreSQL.
catalog.createIndex({ product_id: 1 }, { name: "uq_product_id", unique: true });
catalog.createIndex({ barcode: 1 },    { name: "uq_barcode",    unique: true });

// Recherche plein texte (un seul index texte par collection).
catalog.createIndex(
  { name: "text", brand: "text" },
  { name: "idx_text_name_brand", weights: { name: 10, brand: 5 }, default_language: "french" }
);

// Liste paginée par curseur (_id) filtrée par catégorie : écran catalogue de l'appli mobile.
catalog.createIndex({ status: 1, category: 1, _id: 1 }, { name: "idx_status_category" });

// Filtre par Nutri-Score.
catalog.createIndex({ status: 1, "attributes.nutriscore_grade": 1, _id: 1 }, { name: "idx_status_nutriscore" });

// ---------------------------------------------------------
// 3. Compteur pour attribuer product_id à la création d'un produit via l'API
//    (le seed met à jour seq avec $max à la fin du chargement).
//    Usage applicatif : findOneAndUpdate({_id:"product_id"}, {$inc:{seq:1}}, {returnDocument:"after"})
// ---------------------------------------------------------
mdb.getCollection("counters").updateOne(
  { _id: "product_id" },
  { $setOnInsert: { seq: 0 } },
  { upsert: true }
);

// ---------------------------------------------------------
// 4. Rôle et utilisateur du service Catalogue (moindre droit)
//    Accès uniquement aux collections catalog et counters.
// ---------------------------------------------------------
const privileges = [
  { resource: { db: DB_NAME, collection: "catalog" },
    actions: ["find", "insert", "update", "remove"] },
  { resource: { db: DB_NAME, collection: "counters" },
    actions: ["find", "insert", "update"] },
];

if (mdb.getRole(ROLE_NAME)) {
  mdb.updateRole(ROLE_NAME, { privileges, roles: [] });
} else {
  mdb.createRole({ role: ROLE_NAME, privileges, roles: [] });
}

const roles = [{ role: ROLE_NAME, db: DB_NAME }];
if (mdb.getUser(SVC_USER)) {
  mdb.updateUser(SVC_USER, { pwd: SVC_PASSWORD, roles });
} else {
  mdb.createUser({ user: SVC_USER, pwd: SVC_PASSWORD, roles });
}

// ---------------------------------------------------------
// 5. Vérification
// ---------------------------------------------------------
print("Index de catalog :");
catalog.getIndexes().forEach((i) => print("  - " + i.name));
print("Utilisateur : " + SVC_USER + " (rôle " + ROLE_NAME + " sur " + DB_NAME + ")");