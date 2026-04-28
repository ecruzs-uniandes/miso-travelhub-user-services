"""Tests para flujo de solicitud y promocion de rol admin_hotel."""

import uuid

import pytest_asyncio
from sqlalchemy import select

from app.models.user import User
from app.utils.jwt_handler import create_access_token
from app.utils.security import hash_password

REGISTER_URL = "/api/v1/auth/register"
LIST_URL = "/api/v1/admin/promotion-requests"
PROMOTE_URL = "/api/v1/admin/users/promote"

HOTEL_ID = "11111111-1111-1111-1111-111111111111"


@pytest_asyncio.fixture
async def platform_admin(db_session):
    user = User(
        email="platform@travelhub.app",
        username="platformadmin",
        nombre="Platform Admin",
        hashed_password=hash_password("securepass123"),
        rol="admin_plataforma",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
def admin_headers(platform_admin):
    token = create_access_token(
        {
            "sub": str(platform_admin.id),
            "role": "platform_admin",
            "mfa_verified": True,
            "country": "CO",
            "hotel_id": None,
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
def traveler_headers(db_session):
    async def _make(user_id: str):
        token = create_access_token(
            {
                "sub": user_id,
                "role": "traveler",
                "mfa_verified": False,
                "country": "CO",
                "hotel_id": None,
            }
        )
        return {"Authorization": f"Bearer {token}"}

    return _make


# --- Registro con solicitud ---


async def test_register_without_role_request_keeps_default(async_client):
    payload = {
        "email": "viajero@test.com",
        "username": "viajero1",
        "nombre": "Viajero",
        "password": "securepass123",
    }
    response = await async_client.post(REGISTER_URL, json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["rol"] == "viajero"
    assert data["solicita_rol"] is None
    assert data["hotel_id_solicitado"] is None


async def test_register_with_role_request_persists_fields(async_client, db_session):
    payload = {
        "email": "hotelero@test.com",
        "username": "hotelero1",
        "nombre": "Hotelero",
        "password": "securepass123",
        "solicita_rol": "admin_hotel",
        "hotel_id_solicitado": HOTEL_ID,
    }
    response = await async_client.post(REGISTER_URL, json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["rol"] == "viajero"
    assert data["solicita_rol"] == "admin_hotel"
    assert data["hotel_id_solicitado"] == HOTEL_ID

    result = await db_session.execute(
        select(User).where(User.email == "hotelero@test.com")
    )
    user = result.scalar_one()
    assert user.solicita_rol == "admin_hotel"
    assert str(user.hotel_id_solicitado) == HOTEL_ID


async def test_register_invalid_solicita_rol_returns_422(async_client):
    payload = {
        "email": "invalid@test.com",
        "username": "invalid1",
        "nombre": "Invalid",
        "password": "securepass123",
        "solicita_rol": "admin_plataforma",
    }
    response = await async_client.post(REGISTER_URL, json=payload)
    assert response.status_code == 422


# --- Listado de solicitudes ---


async def test_list_promotion_requests_returns_pending_only(
    async_client, db_session, admin_headers
):
    db_session.add_all(
        [
            User(
                email="pending@test.com",
                username="pending1",
                nombre="Pending",
                hashed_password=hash_password("securepass123"),
                solicita_rol="admin_hotel",
                hotel_id_solicitado=uuid.UUID(HOTEL_ID),
            ),
            User(
                email="other@test.com",
                username="other1",
                nombre="Other",
                hashed_password=hash_password("securepass123"),
            ),
        ]
    )
    await db_session.commit()

    response = await async_client.get(LIST_URL, headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["email"] == "pending@test.com"
    assert data[0]["solicita_rol"] == "admin_hotel"


async def test_list_promotion_requests_without_admin_returns_403(
    async_client, db_session
):
    user = User(
        email="someone@test.com",
        username="someone",
        nombre="Someone",
        hashed_password=hash_password("securepass123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(
        {
            "sub": str(user.id),
            "role": "traveler",
            "mfa_verified": False,
            "country": "CO",
            "hotel_id": None,
        }
    )
    response = await async_client.get(
        LIST_URL, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


async def test_list_promotion_requests_without_token_returns_401(async_client):
    response = await async_client.get(LIST_URL)
    assert response.status_code == 401


# --- Promocion ---


async def test_promote_by_email_sets_role_and_hotel(
    async_client, db_session, admin_headers
):
    user = User(
        email="topromote@test.com",
        username="topromote",
        nombre="To Promote",
        hashed_password=hash_password("securepass123"),
        solicita_rol="admin_hotel",
        hotel_id_solicitado=uuid.UUID(HOTEL_ID),
    )
    db_session.add(user)
    await db_session.commit()

    response = await async_client.post(
        PROMOTE_URL,
        json={
            "email": "topromote@test.com",
            "rol": "admin_hotel",
            "hotel_id": HOTEL_ID,
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["rol"] == "admin_hotel"
    assert data["hotel_id"] == HOTEL_ID
    assert data["solicita_rol"] is None
    assert data["hotel_id_solicitado"] is None


async def test_promote_by_user_id_sets_role_and_hotel(
    async_client, db_session, admin_headers
):
    user = User(
        email="byid@test.com",
        username="byid",
        nombre="By Id",
        hashed_password=hash_password("securepass123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    response = await async_client.post(
        PROMOTE_URL,
        json={
            "user_id": str(user.id),
            "rol": "admin_hotel",
            "hotel_id": HOTEL_ID,
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["rol"] == "admin_hotel"
    assert data["hotel_id"] == HOTEL_ID


async def test_promote_without_email_or_user_id_returns_422(
    async_client, admin_headers
):
    response = await async_client.post(
        PROMOTE_URL,
        json={"rol": "admin_hotel", "hotel_id": HOTEL_ID},
        headers=admin_headers,
    )
    assert response.status_code == 422


async def test_promote_with_both_email_and_user_id_returns_422(
    async_client, admin_headers
):
    response = await async_client.post(
        PROMOTE_URL,
        json={
            "email": "x@test.com",
            "user_id": HOTEL_ID,
            "rol": "admin_hotel",
            "hotel_id": HOTEL_ID,
        },
        headers=admin_headers,
    )
    assert response.status_code == 422


async def test_promote_without_hotel_id_returns_422(async_client, admin_headers):
    response = await async_client.post(
        PROMOTE_URL,
        json={"email": "x@test.com", "rol": "admin_hotel"},
        headers=admin_headers,
    )
    assert response.status_code == 422


async def test_promote_unknown_user_returns_404(async_client, admin_headers):
    response = await async_client.post(
        PROMOTE_URL,
        json={
            "email": "ghost@test.com",
            "rol": "admin_hotel",
            "hotel_id": HOTEL_ID,
        },
        headers=admin_headers,
    )
    assert response.status_code == 404


async def test_promote_without_admin_role_returns_403(async_client, db_session):
    user = User(
        email="caller@test.com",
        username="caller",
        nombre="Caller",
        hashed_password=hash_password("securepass123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(
        {
            "sub": str(user.id),
            "role": "traveler",
            "mfa_verified": False,
            "country": "CO",
            "hotel_id": None,
        }
    )
    response = await async_client.post(
        PROMOTE_URL,
        json={
            "email": "caller@test.com",
            "rol": "admin_hotel",
            "hotel_id": HOTEL_ID,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
