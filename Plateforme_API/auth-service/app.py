import os
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
import psycopg
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

app = FastAPI(title="ReMarket Auth")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://remarket:remarket@localhost:5432/remarket")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")

class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)

def connection():
    return psycopg.connect(DATABASE_URL)

def make_token(user_id: int, email: str) -> str:
    claims = {"sub": str(user_id), "email": email, "role": "CUSTOMER",
              "exp": datetime.now(timezone.utc) + timedelta(hours=8)}
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")

@app.get("/health")
def health():
    with connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok", "service": "auth"}

@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register(body: Credentials):
    with connection() as conn:
        try:
            hashed = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
            row = conn.execute("INSERT INTO auth.users(email,password_hash) VALUES (%s,%s) RETURNING id,email",
                               (body.email.lower(), hashed)).fetchone()
            conn.commit()
        except psycopg.errors.UniqueViolation:
            conn.rollback()
            raise HTTPException(409, "Email already registered")
    return {"access_token": make_token(row[0], row[1]), "token_type": "bearer", "user_id": row[0], "email": row[1]}

@app.post("/api/auth/login")
def login(body: Credentials):
    with connection() as conn:
        row = conn.execute("SELECT id,email,password_hash FROM auth.users WHERE email=%s AND is_active",
                           (body.email.lower(),)).fetchone()
    if not row or not bcrypt.checkpw(body.password.encode(), row[2].encode()):
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": make_token(row[0], row[1]), "token_type": "bearer", "user_id": row[0], "email": row[1]}
