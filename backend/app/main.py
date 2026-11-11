from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from typing import Annotated
from uuid import UUID

import jwt
import redis
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import create_database_engine, get_session
from app.models import LedgerEntry, PriceSnapshot, User
from app.security import hash_password, verify_password


app = FastAPI()
bearer_scheme = HTTPBearer(auto_error=False)
FAKE_BUY_PRICE = Decimal("15000.0000")
FAKE_SELL_PRICE = Decimal("14500.0000")
PRICE_CACHE_KEY = "gold_price_dzd_per_gram"
TOKEN_LIFETIME = timedelta(hours=1)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=8, max_length=72)]

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=8, max_length=72)]

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TradeRequest(BaseModel):
    grams: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4)]
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=255)]


class TradeResponse(BaseModel):
    transaction_id: UUID
    entry_type: str
    grams: Decimal
    balance_grams: Decimal


class PriceResponse(BaseModel):
    buy_price_dzd_per_gram: Decimal
    sell_price_dzd_per_gram: Decimal
    source: str


class WalletResponse(BaseModel):
    balance_grams: Decimal


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: str


def get_redis_client() -> redis.Redis:
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise HTTPException(status_code=503, detail="Redis is not configured")
    return redis.Redis.from_url(redis_url, decode_responses=True)


def require_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="JWT_SECRET is not configured")
    return secret


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    try:
        payload = jwt.decode(credentials.credentials, require_jwt_secret(), algorithms=["HS256"])
        user_id = UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from None
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user


@app.get("/health")
def health() -> dict[str, str]:
    checks = {"db": "error", "redis": "error"}
    try:
        from sqlalchemy import text

        with Session(create_database_engine()) as session:
            session.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception:
        pass
    try:
        get_redis_client().ping()
        checks["redis"] = "ok"
    except Exception:
        pass
    if checks["db"] != "ok" or checks["redis"] != "ok":
        raise HTTPException(status_code=503, detail={"status": "error", **checks})
    return {"status": "ok", **checks}


@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, session: Annotated[Session, Depends(get_session)]) -> User:
    normalized_email = str(payload.email).strip().lower()
    if session.scalar(select(User).where(func.lower(User.email) == normalized_email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")
    user = User(email=normalized_email, password_hash=hash_password(payload.password), role="customer")
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered") from None
    session.refresh(user)
    return user


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Annotated[Session, Depends(get_session)]) -> TokenResponse:
    email = str(payload.email).strip().lower()
    user = session.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": str(user.id), "iat": now, "exp": now + TOKEN_LIFETIME},
        require_jwt_secret(),
        algorithm="HS256",
    )
    return TokenResponse(access_token=token)


@app.get("/price", response_model=PriceResponse)
def get_price(client: Annotated[redis.Redis, Depends(get_redis_client)]) -> PriceResponse:
    cached = client.get(PRICE_CACHE_KEY)
    if cached:
        try:
            return PriceResponse.model_validate_json(cached)
        except ValueError:
            client.delete(PRICE_CACHE_KEY)
    response = PriceResponse(
        buy_price_dzd_per_gram=FAKE_BUY_PRICE,
        sell_price_dzd_per_gram=FAKE_SELL_PRICE,
        source="fixed_fake_price",
    )
    client.setex(PRICE_CACHE_KEY, 60, response.model_dump_json())
    return response


def _balance(session: Session, user_id: UUID) -> Decimal:
    return session.scalar(select(func.coalesce(func.sum(LedgerEntry.grams), 0)).where(LedgerEntry.user_id == user_id)) or Decimal("0")


def _trade(
    payload: TradeRequest,
    user: User,
    session: Session,
    entry_type: str,
) -> TradeResponse:
    existing = session.scalar(select(LedgerEntry).where(LedgerEntry.idempotency_key == payload.idempotency_key))
    if existing:
        if existing.user_id != user.id or existing.entry_type != entry_type or abs(existing.grams) != payload.grams:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency key was already used")
        return TradeResponse(
            transaction_id=existing.id,
            entry_type=existing.entry_type,
            grams=existing.grams,
            balance_grams=_balance(session, user.id),
        )

    # Lock the user's row so simultaneous sells cannot both spend the same balance.
    session.scalar(select(User).where(User.id == user.id).with_for_update())
    if entry_type == "sell" and _balance(session, user.id) < payload.grams:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Insufficient gold balance")

    snapshot = PriceSnapshot(
        buy_price_dzd_per_gram=FAKE_BUY_PRICE,
        sell_price_dzd_per_gram=FAKE_SELL_PRICE,
        source="fixed_fake_price",
    )
    session.add(snapshot)
    session.flush()
    signed_grams = payload.grams if entry_type == "buy" else -payload.grams
    entry = LedgerEntry(
        user_id=user.id,
        entry_type=entry_type,
        grams=signed_grams,
        price_snapshot_id=snapshot.id,
        idempotency_key=payload.idempotency_key,
    )
    session.add(entry)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency key was already used") from None
    session.refresh(entry)
    return TradeResponse(
        transaction_id=entry.id,
        entry_type=entry.entry_type,
        grams=entry.grams,
        balance_grams=_balance(session, user.id),
    )


@app.post("/buy", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
def buy(
    payload: TradeRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> TradeResponse:
    return _trade(payload, user, session, "buy")


@app.post("/sell", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
def sell(
    payload: TradeRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> TradeResponse:
    return _trade(payload, user, session, "sell")


@app.get("/wallet", response_model=WalletResponse)
def wallet(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> WalletResponse:
    return WalletResponse(balance_grams=_balance(session, user.id))
