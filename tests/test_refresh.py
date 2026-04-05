"""Tests para refresh de tokens."""

import pytest
import pytest_asyncio

from app.models.user import User
from app.utils.jwt_handler import create_access_token, create_refresh_token
from app.utils.security import hash_password


REFRESH_URL = "/api/v1/auth/refresh"


@pytest_asyncio.fixture
async def test_user(db_session):
    user = User(
        email="refresh@test.com",
        username="refreshuser",
        nombre="Refresh User",
        hashed_password=hash_password("securepass123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# --- Happy path ---


@pytest.mark.asyncio
async def test_refresh_valid_token_returns_200(async_client, test_user):
    refresh_token = create_refresh_token({"sub": str(test_user.id), "role": "traveler", "mfa_verified": False, "country": "CO", "hotel_id": None})
    response = await async_client.post(
        REFRESH_URL, json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 900


# --- Error cases ---


@pytest.mark.asyncio
async def test_refresh_with_access_token_returns_401(async_client, test_user):
    access_token = create_access_token({"sub": str(test_user.id), "role": "traveler", "mfa_verified": False, "country": "CO", "hotel_id": None})
    response = await async_client.post(
        REFRESH_URL, json={"refresh_token": access_token}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Se esperaba un refresh token"


@pytest.mark.asyncio
async def test_refresh_invalid_token_returns_401(async_client):
    response = await async_client.post(
        REFRESH_URL, json={"refresh_token": "token.invalido.aqui"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_inactive_user_returns_401(async_client, test_user, db_session):
    refresh_token = create_refresh_token({"sub": str(test_user.id), "role": "traveler", "mfa_verified": False, "country": "CO", "hotel_id": None})
    test_user.activo = False
    await db_session.commit()

    response = await async_client.post(
        REFRESH_URL, json={"refresh_token": refresh_token}
    )
    assert response.status_code == 401
