"""Tests para login de usuarios (W08)."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.models.user import User
from app.utils.security import generate_totp_secret, hash_password

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"

VALID_USER = {
    "email": "login@test.com",
    "username": "loginuser",
    "nombre": "Login User",
    "password": "securepass123",
}


@pytest_asyncio.fixture
async def test_user(db_session):
    user = User(
        email=VALID_USER["email"],
        username=VALID_USER["username"],
        nombre=VALID_USER["nombre"],
        hashed_password=hash_password(VALID_USER["password"]),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# --- Happy path ---


@pytest.mark.asyncio
async def test_login_valid_credentials_returns_200(async_client, test_user):
    response = await async_client.post(
        LOGIN_URL,
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 900


@pytest.mark.asyncio
async def test_login_successful_resets_failed_attempts(
    async_client, test_user, db_session
):
    # Fail once
    await async_client.post(
        LOGIN_URL,
        json={"email": VALID_USER["email"], "password": "wrongpass1"},
    )
    # Then succeed
    await async_client.post(
        LOGIN_URL,
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    await db_session.refresh(test_user)
    assert test_user.failed_login_attempts == 0
    assert test_user.locked_until is None


# --- Error cases ---


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(async_client, test_user):
    response = await async_client.post(
        LOGIN_URL,
        json={"email": VALID_USER["email"], "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales inválidas"


@pytest.mark.asyncio
async def test_login_nonexistent_email_returns_401(async_client):
    response = await async_client.post(
        LOGIN_URL,
        json={"email": "noexiste@test.com", "password": "whatever123"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_increments_failed_attempts(async_client, test_user, db_session):
    await async_client.post(
        LOGIN_URL,
        json={"email": VALID_USER["email"], "password": "wrongpass1"},
    )
    await db_session.refresh(test_user)
    assert test_user.failed_login_attempts == 1


@pytest.mark.asyncio
async def test_login_five_failures_locks_account(async_client, test_user, db_session):
    for _ in range(5):
        await async_client.post(
            LOGIN_URL,
            json={"email": VALID_USER["email"], "password": "wrongpass1"},
        )
    await db_session.refresh(test_user)
    assert test_user.failed_login_attempts >= 5
    assert test_user.locked_until is not None


@pytest.mark.asyncio
async def test_login_locked_account_returns_423(async_client, test_user, db_session):
    test_user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
    test_user.failed_login_attempts = 5
    await db_session.commit()

    response = await async_client.post(
        LOGIN_URL,
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert response.status_code == 423


@pytest.mark.asyncio
async def test_login_lockout_checked_before_password(
    async_client, test_user, db_session
):
    test_user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
    test_user.failed_login_attempts = 5
    await db_session.commit()

    response = await async_client.post(
        LOGIN_URL,
        json={"email": VALID_USER["email"], "password": "wrongpassword"},
    )
    assert response.status_code == 423


@pytest.mark.asyncio
async def test_login_inactive_user_returns_401(async_client, test_user, db_session):
    test_user.activo = False
    await db_session.commit()

    response = await async_client.post(
        LOGIN_URL,
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert response.status_code == 401


# --- MFA ---


@pytest.mark.asyncio
async def test_login_mfa_active_no_code_returns_428(
    async_client, test_user, db_session
):
    test_user.mfa_activo = True
    test_user.mfa_secret = generate_totp_secret()
    await db_session.commit()

    response = await async_client.post(
        LOGIN_URL,
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert response.status_code == 428
    assert response.json()["detail"] == "Código MFA requerido"


@pytest.mark.asyncio
async def test_login_mfa_active_invalid_code_returns_401(
    async_client, test_user, db_session
):
    test_user.mfa_activo = True
    test_user.mfa_secret = generate_totp_secret()
    await db_session.commit()

    response = await async_client.post(
        LOGIN_URL,
        json={
            "email": VALID_USER["email"],
            "password": VALID_USER["password"],
            "totp_code": "000000",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_mfa_active_valid_code_returns_200(
    async_client, test_user, db_session
):
    import pyotp

    secret = generate_totp_secret()
    test_user.mfa_activo = True
    test_user.mfa_secret = secret
    await db_session.commit()

    valid_code = pyotp.TOTP(secret).now()
    response = await async_client.post(
        LOGIN_URL,
        json={
            "email": VALID_USER["email"],
            "password": VALID_USER["password"],
            "totp_code": valid_code,
        },
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
