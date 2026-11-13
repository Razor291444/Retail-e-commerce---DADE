import os
from typing import Optional
from pymongo import MongoClient
import strawberry
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

client = MongoClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"))
products = client[os.getenv("MONGO_DATABASE", "market")][os.getenv("MONGO_COLLECTION", "catalog")]

@strawberry.type
class Product:
    product_id: Optional[int] = None
    barcode: str = ""
    name: str = ""
    brand: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    price: float = 0
    quantity: int = 0

def to_product(document):
    price_cents = document.get("price_cents")
    price = (
        float(price_cents) / 100
        if price_cents is not None
        else float(document.get("price", 0) or 0)
    )
    return Product(product_id=document.get("product_id"), barcode=document.get("barcode", ""),
                   name=document.get("name", document.get("product_name", "")),
                   brand=document.get("brand", document.get("brands")),
                   category=document.get("category", document.get("categories")),
                   image_url=document.get("imageUrl", document.get("image_url")),
                   price=price, quantity=int(document.get("quantity", 0) or 0))

@strawberry.type
class Query:
    @strawberry.field
    def products(self, search: Optional[str] = None, limit: int = 20) -> list[Product]:
        query = {"$text": {"$search": search}} if search else {}
        return [to_product(p) for p in products.find(query).limit(min(max(limit, 1), 100))]

    @strawberry.field
    def product(self, product_id: int) -> Optional[Product]:
        document = products.find_one({"product_id": product_id})
        return to_product(document) if document else None

schema = strawberry.Schema(query=Query)
app = FastAPI(title="ReMarket Catalog GraphQL")
app.include_router(GraphQLRouter(schema), prefix="/graphql")

@app.get("/health")
def health():
    client.admin.command("ping")
    return {"status": "ok", "service": "catalog"}
