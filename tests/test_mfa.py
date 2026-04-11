"""Tests para flujo MFA."""

import pyotp
import pytest
import pytest_asyncio

from app.models.user import User
from app.utils.jwt_handler import create_access_token
from app.utils.security import generate_totp_secret, hash_password

MFA_SETUP_URL = "/api/v1/auth/mfa/setup"
MFA_VERIFY_URL = "/api/v1/auth/mfa/verify"


@pytest_asyncio.fixture
async def test_user(db_session):
    user = User(
        email="mfa@test.com",
        username="mfauser",
        nombre="MFA User",
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


# --- MFA Setup ---


@pytest.mark.asyncio
async def test_mfa_setup_returns_secret_and_qr(async_client, auth_headers, test_user):
    response = await async_client.post(MFA_SETUP_URL, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["secret"]) == 32
    assert data["qr_uri"].startswith("otpauth://totp/TravelHub:")
    assert test_user.email in data["qr_uri"]


@pytest.mark.asyncio
async def test_mfa_setup_without_token_returns_401(async_client):
    response = await async_client.post(MFA_SETUP_URL)
    assert response.status_code == 401


# --- MFA Verify ---


@pytest.mark.asyncio
async def test_mfa_verify_valid_code_activates_mfa(
    async_client, auth_headers, test_user, db_session
):
    secret = generate_totp_secret()
    test_user.mfa_secret = secret
    await db_session.commit()

    valid_code = pyotp.TOTP(secret).now()
    response = await async_client.post(
        MFA_VERIFY_URL,
        headers=auth_headers,
        json={"totp_code": valid_code},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "MFA activado exitosamente"

    await db_session.refresh(test_user)
    assert test_user.mfa_activo is True


@pytest.mark.asyncio
async def test_mfa_verify_invalid_code_returns_401(
    async_client, auth_headers, test_user, db_session
):
    test_user.mfa_secret = generate_totp_secret()
    await db_session.commit()

    response = await async_client.post(
        MFA_VERIFY_URL,
        headers=auth_headers,
        json={"totp_code": "000000"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_mfa_verify_without_setup_returns_400(async_client, auth_headers):
    response = await async_client.post(
        MFA_VERIFY_URL,
        headers=auth_headers,
        json={"totp_code": "123456"},
    )
    assert response.status_code == 400
    assert "MFA no configurado" in response.json()["detail"]


@pytest.mark.asyncio
async def test_mfa_verify_without_token_returns_401(async_client):
    response = await async_client.post(MFA_VERIFY_URL, json={"totp_code": "123456"})
    assert response.status_code == 401
