"""Tests para registro de usuarios (W07)."""

import pytest
from sqlalchemy import select

from app.models.user import User

REGISTER_URL = "/api/v1/auth/register"

VALID_USER = {
    "email": "test@example.com",
    "username": "testuser",
    "nombre": "Test User",
    "password": "securepass123",
    "telefono": "+573001234567",
    "pais": "CO",
    "idioma": "es",
    "moneda_preferida": "COP",
}


# --- Happy path ---


async def test_register_valid_user_returns_201(async_client):
    response = await async_client.post(REGISTER_URL, json=VALID_USER)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == VALID_USER["email"]
    assert data["username"] == VALID_USER["username"]
    assert data["nombre"] == VALID_USER["nombre"]
    assert data["telefono"] == VALID_USER["telefono"]
    assert data["pais"] == VALID_USER["pais"]
    assert data["idioma"] == VALID_USER["idioma"]
    assert data["moneda_preferida"] == VALID_USER["moneda_preferida"]
    assert data["rol"] == "viajero"
    assert data["mfa_activo"] is False
    assert "id" in data
    assert "fecha_registro" in data


async def test_register_does_not_expose_password(async_client):
    response = await async_client.post(REGISTER_URL, json=VALID_USER)
    data = response.json()
    assert "hashed_password" not in data
    assert "password" not in data
    assert "mfa_secret" not in data


async def test_register_stores_hashed_password(async_client, db_session):
    await async_client.post(REGISTER_URL, json=VALID_USER)
    result = await db_session.execute(
        select(User).where(User.email == VALID_USER["email"])
    )
    user = result.scalar_one()
    assert user.hashed_password != VALID_USER["password"]
    assert user.hashed_password.startswith("$2b$")


async def test_register_defaults_without_optional_fields(async_client):
    payload = {
        "email": "minimal@example.com",
        "username": "minuser",
        "nombre": "Min User",
        "password": "securepass123",
    }
    response = await async_client.post(REGISTER_URL, json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["idioma"] == "es"
    assert data["moneda_preferida"] == "USD"
    assert data["telefono"] is None
    assert data["pais"] is None


# --- Errores: duplicados ---


async def test_register_duplicate_email_returns_409(async_client):
    await async_client.post(REGISTER_URL, json=VALID_USER)
    second = VALID_USER.copy()
    second["username"] = "otheruser"
    response = await async_client.post(REGISTER_URL, json=second)
    assert response.status_code == 409
    assert "email" in response.json()["detail"]


async def test_register_duplicate_username_returns_409(async_client):
    await async_client.post(REGISTER_URL, json=VALID_USER)
    second = VALID_USER.copy()
    second["email"] = "other@example.com"
    response = await async_client.post(REGISTER_URL, json=second)
    assert response.status_code == 409
    assert "username" in response.json()["detail"]


# --- Errores: validación ---


@pytest.mark.parametrize(
    "field,value,expected_status",
    [
        ("password", "short", 422),
        ("username", "ab", 422),
        ("email", "not-an-email", 422),
        ("nombre", "", 422),
    ],
)
async def test_register_invalid_field_returns_422(
    async_client, field, value, expected_status
):
    payload = VALID_USER.copy()
    payload[field] = value
    response = await async_client.post(REGISTER_URL, json=payload)
    assert response.status_code == expected_status
