import logging
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.schemas.user import (
    MessageResponse,
    MFASetupResponse,
    PromoteUserRequest,
    PromotionRequestResponse,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.utils.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.utils.security import (
    generate_totp_secret,
    hash_password,
    verify_password,
    verify_totp,
)

logger = logging.getLogger(__name__)


async def register_user(request: UserRegisterRequest, db: AsyncSession) -> UserResponse:
    result_email = await db.execute(select(User).where(User.email == request.email))
    if result_email.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail="Ya existe un usuario con ese email"
        )

    result_username = await db.execute(
        select(User).where(User.username == request.username)
    )
    if result_username.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail="Ya existe un usuario con ese username"
        )

    user = User(
        email=request.email,
        username=request.username,
        nombre=request.nombre,
        hashed_password=hash_password(request.password),
        telefono=request.telefono,
        pais=request.pais,
        idioma=request.idioma,
        moneda_preferida=request.moneda_preferida,
        solicita_rol=request.solicita_rol,
        hotel_id_solicitado=request.hotel_id_solicitado,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    if user.solicita_rol:
        logger.info(
            "Usuario registrado con solicitud de rol %s: %s",
            user.solicita_rol,
            user.email,
        )
    else:
        logger.info("Usuario registrado: %s", user.email)
    return UserResponse.model_validate(user)


async def login_user(
    email: str, password: str, totp_code: str | None, db: AsyncSession
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not user.activo:
        logger.warning("Login fallido para: %s — usuario no encontrado", email)
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    _check_lockout(user)

    if not verify_password(password, user.hashed_password):
        await _handle_failed_attempt(user, db)
        logger.warning("Login fallido para: %s — contraseña incorrecta", email)
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    if user.mfa_activo:
        _validate_mfa(user, totp_code)

    user.failed_login_attempts = 0
    user.locked_until = None
    await db.commit()

    tokens = _generate_tokens(user)
    logger.info("Login exitoso: %s", user.email)
    return tokens


def _check_lockout(user: User) -> None:
    locked = user.locked_until
    if locked:
        if locked.tzinfo is None:
            locked = locked.replace(tzinfo=timezone.utc)
        if locked > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=423,
                detail="Cuenta bloqueada por múltiples intentos fallidos",
            )


async def _handle_failed_attempt(user: User, db: AsyncSession) -> None:
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
        user.locked_until = datetime.now(timezone.utc) + timedelta(
            minutes=settings.LOCKOUT_MINUTES
        )
        logger.warning("Cuenta bloqueada: %s", user.email)
    await db.commit()


def _validate_mfa(user: User, totp_code: str | None) -> None:
    if not totp_code:
        raise HTTPException(status_code=428, detail="Código MFA requerido")
    if not user.mfa_secret or not verify_totp(user.mfa_secret, totp_code):
        raise HTTPException(status_code=401, detail="Código MFA inválido")


ROLE_MAP = {
    "viajero": "traveler",
    "admin_hotel": "hotel_admin",
    "admin_plataforma": "platform_admin",
    "traveler": "traveler",
    "hotel_admin": "hotel_admin",
    "platform_admin": "platform_admin",
}


def _generate_tokens(user: User) -> TokenResponse:
    mapped_role = ROLE_MAP.get(user.rol, user.rol)
    payload = {
        "sub": str(user.id),
        "role": mapped_role,
        "mfa_verified": user.mfa_activo,
        "country": user.pais or "CO",
        "hotel_id": str(user.hotel_id) if getattr(user, "hotel_id", None) else None,
    }
    access_token = create_access_token(payload)
    refresh_token = create_refresh_token(payload)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TTL,
    )


async def refresh_tokens(refresh_token: str, db: AsyncSession) -> TokenResponse:
    try:
        payload = decode_token(refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Se esperaba un refresh token")

    try:
        user_id = uuid_mod.UUID(payload.get("sub"))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.activo:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    tokens = _generate_tokens(user)
    logger.info("Tokens renovados para: %s", user.email)
    return tokens


async def _get_user_by_id(user_id: str, db: AsyncSession) -> User:
    try:
        uid = uuid_mod.UUID(user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="Token inválido")
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user or not user.activo:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user


async def get_current_user(user_id: str, db: AsyncSession) -> UserResponse:
    user = await _get_user_by_id(user_id, db)
    return UserResponse.model_validate(user)


async def update_user(
    user_id: str, request: UserUpdateRequest, db: AsyncSession
) -> UserResponse:
    user = await _get_user_by_id(user_id, db)

    if request.nombre is not None:
        user.nombre = request.nombre
    if request.password is not None:
        user.hashed_password = hash_password(request.password)
    if request.telefono is not None:
        user.telefono = request.telefono

    await db.commit()
    await db.refresh(user)

    logger.info("Usuario actualizado: %s", user.email)
    return UserResponse.model_validate(user)


async def setup_mfa(user_id: str, db: AsyncSession) -> MFASetupResponse:
    user = await _get_user_by_id(user_id, db)
    secret = generate_totp_secret()
    user.mfa_secret = secret
    await db.commit()

    qr_uri = f"otpauth://totp/TravelHub:{user.email}?secret={secret}&issuer=TravelHub"
    logger.info("MFA configurado para: %s", user.email)
    return MFASetupResponse(secret=secret, qr_uri=qr_uri)


async def list_promotion_requests(
    db: AsyncSession,
) -> list[PromotionRequestResponse]:
    result = await db.execute(
        select(User).where(User.solicita_rol.is_not(None), User.activo.is_(True))
    )
    users = result.scalars().all()
    return [PromotionRequestResponse.model_validate(u) for u in users]


async def promote_user(
    request: PromoteUserRequest, admin_id: str, db: AsyncSession
) -> UserResponse:
    if request.user_id is not None:
        result = await db.execute(select(User).where(User.id == request.user_id))
    else:
        result = await db.execute(select(User).where(User.email == request.email))

    user = result.scalar_one_or_none()
    if not user or not user.activo:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.rol = request.rol
    user.hotel_id = request.hotel_id
    user.solicita_rol = None
    user.hotel_id_solicitado = None

    await db.commit()
    await db.refresh(user)

    logger.info(
        "platform_admin %s elevo a %s a rol %s (hotel_id=%s)",
        admin_id,
        user.email,
        user.rol,
        user.hotel_id,
    )
    return UserResponse.model_validate(user)


async def verify_mfa(user_id: str, totp_code: str, db: AsyncSession) -> MessageResponse:
    user = await _get_user_by_id(user_id, db)

    if not user.mfa_secret:
        raise HTTPException(
            status_code=400, detail="MFA no configurado. Ejecute setup primero"
        )

    if not verify_totp(user.mfa_secret, totp_code):
        raise HTTPException(status_code=401, detail="Código MFA inválido")

    user.mfa_activo = True
    await db.commit()

    logger.info("MFA verificado y activado para: %s", user.email)
    return MessageResponse(message="MFA activado exitosamente")
