import os
import psycopg
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="ReMarket Orders")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://remarket:remarket@localhost:5432/remarket")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:8083")
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://localhost:8085")
class Item(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_price_cents: int = Field(ge=0)
class OrderRequest(BaseModel):
    customer_id: int
    items: list[Item] = Field(min_length=1)

@app.get("/health")
def health():
    with psycopg.connect(DATABASE_URL) as conn: conn.execute("SELECT 1")
    return {"status": "ok", "service": "orders"}

@app.post("/api/orders", status_code=201)
async def create_order(body: OrderRequest):
    total = sum(item.quantity * item.unit_price_cents for item in body.items)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for item in body.items:
                response = await client.post(f"{INVENTORY_URL}/api/inventory/reserve",
                                             json={"product_id": item.product_id, "quantity": item.quantity})
                if response.status_code >= 400: raise HTTPException(409, "Insufficient stock")
        with psycopg.connect(DATABASE_URL) as conn:
            if not conn.execute("SELECT 1 FROM orders.customers WHERE id=%s", (body.customer_id,)).fetchone():
                raise HTTPException(404, "Customer not found")
            order = conn.execute("""INSERT INTO orders.orders(customer_id,status,total_cents)
                                    VALUES (%s,'PENDING',%s) RETURNING id,customer_id,status,total_cents,created_at""",
                                 (body.customer_id, total)).fetchone()
            for item in body.items:
                conn.execute("INSERT INTO orders.order_items(order_id,product_id,quantity,unit_price_cents) VALUES (%s,%s,%s,%s)",
                             (order[0], item.product_id, item.quantity, item.unit_price_cents))
            conn.commit()
        async with httpx.AsyncClient(timeout=10) as client:
            payment = await client.post(f"{PAYMENT_URL}/api/payments", json={"order_id": order[0], "amount_cents": total})
        if payment.status_code >= 400: raise HTTPException(502, "Payment service failed")
        return dict(zip(("id","customer_id","status","total_cents","created_at"), order))
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Dependent service unavailable") from exc

@app.get("/api/orders/{order_id}")
def get_order(order_id: int):
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute("SELECT id,customer_id,status,total_cents,created_at FROM orders.orders WHERE id=%s",
                           (order_id,)).fetchone()
        if not row: raise HTTPException(404, "Order not found")
        items = conn.execute("SELECT product_id,quantity,unit_price_cents FROM orders.order_items WHERE order_id=%s",
                             (order_id,)).fetchall()
    result = dict(zip(("id","customer_id","status","total_cents","created_at"), row))
    result["items"] = [dict(zip(("product_id","quantity","unit_price_cents"), item)) for item in items]
    return result
