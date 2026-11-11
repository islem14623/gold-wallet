from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import (
    PRICE_CACHE_KEY,
    LoginRequest,
    RegisterRequest,
    TradeRequest,
    buy,
    get_current_user,
    get_price,
    login,
    register,
    sell,
    wallet,
)
from app.models import LedgerEntry, User


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl

    def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.ttls.pop(key, None)


def make_user(session: Session) -> User:
    return register(
        RegisterRequest(email="wallet@example.com", password="correct horse battery"),
        session,
    )


def test_register_login_and_jwt_auth(session: Session) -> None:
    user = make_user(session)
    token = login(
        LoginRequest(email="WALLET@example.com", password="correct horse battery"),
        session,
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token.access_token)

    authenticated_user = get_current_user(credentials, session)
    assert authenticated_user.id == user.id
    assert wallet(authenticated_user, session).balance_grams == Decimal("0")

    with pytest.raises(HTTPException) as error:
        get_current_user(None, session)
    assert error.value.status_code == 401


def test_buy_sell_and_reject_oversell(session: Session) -> None:
    user = make_user(session)
    bought = buy(TradeRequest(grams="5.2500", idempotency_key="buy-1"), user, session)
    assert bought.balance_grams == Decimal("5.2500")

    sold = sell(TradeRequest(grams="2.0000", idempotency_key="sell-1"), user, session)
    assert sold.grams == Decimal("-2.0000")
    assert sold.balance_grams == Decimal("3.2500")

    with pytest.raises(HTTPException) as error:
        sell(TradeRequest(grams="4.0000", idempotency_key="sell-2"), user, session)
    assert error.value.status_code == 409
    assert wallet(user, session).balance_grams == Decimal("3.2500")


def test_idempotency_replays_without_duplicate_ledger_entry(session: Session) -> None:
    user = make_user(session)
    request = TradeRequest(grams="1.0000", idempotency_key="one-purchase")

    first = buy(request, user, session)
    replay = buy(request, user, session)
    assert first.transaction_id == replay.transaction_id
    assert session.scalar(select(LedgerEntry).where(LedgerEntry.user_id == user.id)) is not None
    assert len(session.scalars(select(LedgerEntry).where(LedgerEntry.user_id == user.id)).all()) == 1


def test_price_is_cached_for_sixty_seconds() -> None:
    client = FakeRedis()
    first = get_price(client)
    second = get_price(client)

    assert first == second
    assert first.buy_price_dzd_per_gram == Decimal("15000.0000")
    assert client.ttls[PRICE_CACHE_KEY] == 60


def test_duplicate_registration_and_invalid_login(session: Session) -> None:
    make_user(session)
    with pytest.raises(HTTPException) as duplicate:
        make_user(session)
    assert duplicate.value.status_code == 409

    with pytest.raises(HTTPException) as invalid_login:
        login(LoginRequest(email="wallet@example.com", password="wrong password"), session)
    assert invalid_login.value.status_code == 401
