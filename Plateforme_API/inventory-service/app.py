import os
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="ReMarket Inventory")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://remarket:remarket@localhost:5432/remarket")
class StockChange(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)

@app.get("/health")
def health():
    with psycopg.connect(DATABASE_URL) as conn: conn.execute("SELECT 1")
    return {"status": "ok", "service": "inventory"}

@app.get("/api/inventory/{product_id}")
def get_stock(product_id: int):
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute("SELECT product_id,warehouse_id,quantity FROM inventory.stock WHERE product_id=%s",
                           (product_id,)).fetchone()
    if not row: raise HTTPException(404, "Stock not found")
    return {"product_id": row[0], "warehouse_id": row[1], "quantity": row[2]}

@app.put("/api/inventory/{product_id}")
def set_stock(product_id: int, body: StockChange):
    with psycopg.connect(DATABASE_URL) as conn:
        warehouse = conn.execute("SELECT id FROM inventory.warehouse ORDER BY id LIMIT 1").fetchone()
        if not warehouse:
            warehouse = conn.execute("INSERT INTO inventory.warehouse(name,capacity_units) VALUES ('default',100000) RETURNING id").fetchone()
        row = conn.execute("""INSERT INTO inventory.stock(product_id,warehouse_id,quantity) VALUES (%s,%s,%s)
                             ON CONFLICT(product_id) DO UPDATE SET quantity=EXCLUDED.quantity RETURNING product_id,warehouse_id,quantity""",
                           (product_id, warehouse[0], body.quantity)).fetchone()
        conn.commit()
    return {"product_id": row[0], "warehouse_id": row[1], "quantity": row[2]}

@app.post("/api/inventory/reserve")
def reserve(body: StockChange):
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute("""UPDATE inventory.stock SET quantity=quantity-%s
                              WHERE product_id=%s AND quantity >= %s
                              RETURNING product_id,warehouse_id,quantity""",
                           (body.quantity, body.product_id, body.quantity)).fetchone()
        if not row: raise HTTPException(409, "Insufficient stock")
        conn.commit()
    return {"product_id": row[0], "warehouse_id": row[1], "quantity": row[2]}
