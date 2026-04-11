"""Tests para Chain of Responsibility de autenticación (AH008)."""

import pytest
import pytest_asyncio

from app.models.user import User
from app.utils.jwt_handler import create_access_token, create_refresh_token
from app.utils.security import hash_password

ME_URL = "/api/v1/auth/me"


@pytest_asyncio.fixture
async def test_user(db_session):
    user = User(
        email="chain@test.com",
        username="chainuser",
        nombre="Chain User",
        hashed_password=hash_password("securepass123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
def auth_headers(test_user):
    token = create_access_token(
        {
            "sub": str(test_user.id),
            "role": "traveler",
            "mfa_verified": False,
            "country": "CO",
            "hotel_id": None,
        }
    )
    return {"Authorization": f"Bearer {token}"}


# --- Happy path ---


@pytest.mark.asyncio
async def test_chain_valid_token_passes(async_client, auth_headers):
    response = await async_client.get(ME_URL, headers=auth_headers)
    assert response.status_code == 200


# --- No token ---


@pytest.mark.asyncio
async def test_chain_no_auth_header_returns_401(async_client):
    response = await async_client.get(ME_URL)
    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"


# --- Malformed token ---


@pytest.mark.asyncio
async def test_chain_malformed_bearer_returns_401(async_client):
    response = await async_client.get(
        ME_URL, headers={"Authorization": "InvalidHeader"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chain_invalid_token_returns_401(async_client):
    response = await async_client.get(
        ME_URL, headers={"Authorization": "Bearer token.invalido.aqui"}
    )
    assert response.status_code == 401


# --- Refresh token used as access ---


@pytest.mark.asyncio
async def test_chain_refresh_token_rejected_returns_401(async_client, test_user):
    refresh = create_refresh_token(
        {
            "sub": str(test_user.id),
            "role": "traveler",
            "mfa_verified": False,
            "country": "CO",
            "hotel_id": None,
        }
    )
    response = await async_client.get(
        ME_URL, headers={"Authorization": f"Bearer {refresh}"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Se esperaba un access token"


# --- Role filter ---


@pytest.mark.asyncio
async def test_chain_valid_token_wrong_role_returns_403(async_client, test_user):
    from fastapi import Depends, Request

    from app.middleware.auth_chain import build_auth_chain

    # Simulamos un endpoint que requiere admin_sistema
    # Usamos directamente el chain para testear el RoleFilter
    chain = build_auth_chain(allowed_roles=["admin_sistema"])

    from unittest.mock import AsyncMock, MagicMock

    from starlette.datastructures import Headers

    token = create_access_token(
        {
            "sub": str(test_user.id),
            "role": "traveler",
            "mfa_verified": False,
            "country": "CO",
            "hotel_id": None,
        }
    )
    mock_request = MagicMock(spec=Request)
    mock_request.headers = Headers({"authorization": f"Bearer {token}"})
    mock_request.state = MagicMock()

    with pytest.raises(Exception) as exc_info:
        await chain.handle(mock_request)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Rol insuficiente"
