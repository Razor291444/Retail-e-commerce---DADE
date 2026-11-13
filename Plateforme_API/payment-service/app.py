import os
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="ReMarket Payments")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://remarket:remarket@localhost:5432/remarket")
class PaymentRequest(BaseModel):
    order_id: int
    amount_cents: int = Field(ge=0)

@app.get("/health")
def health():
    with psycopg.connect(DATABASE_URL) as conn: conn.execute("SELECT 1")
    return {"status": "ok", "service": "payment"}

@app.post("/api/payments")
def pay(body: PaymentRequest):
    with psycopg.connect(DATABASE_URL) as conn:
        if conn.execute("SELECT 1 FROM payments.payments WHERE order_id=%s", (body.order_id,)).fetchone():
            raise HTTPException(409, "Payment already exists")
        row = conn.execute("""INSERT INTO payments.payments(order_id,amount_cents,status)
                              VALUES (%s,%s,'SUCCEEDED') RETURNING id,order_id,amount_cents,status,created_at""",
                           (body.order_id, body.amount_cents)).fetchone()
        conn.commit()
    return dict(zip(("id","order_id","amount_cents","status","created_at"), row))

@app.get("/api/payments/{order_id}")
def get_payment(order_id: int):
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute("SELECT id,order_id,amount_cents,status,created_at FROM payments.payments WHERE order_id=%s",
                           (order_id,)).fetchone()
    if not row: raise HTTPException(404, "Payment not found")
    return dict(zip(("id","order_id","amount_cents","status","created_at"), row))
