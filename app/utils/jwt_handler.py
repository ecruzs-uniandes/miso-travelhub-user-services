import logging
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from jose import JWTError, jwt

from app.config import settings
from app.utils.rsa_keys import get_key_id, get_private_key

logger = logging.getLogger(__name__)


def _get_private_pem() -> bytes:
    return get_private_key().private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _get_public_pem() -> bytes:
    return get_private_key().public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(seconds=settings.JWT_ACCESS_TTL)
    to_encode.update({
        "type": "access",
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    })
    return jwt.encode(
        to_encode,
        _get_private_pem(),
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": get_key_id()},
    )


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(seconds=settings.JWT_REFRESH_TTL)
    to_encode.update({
        "type": "refresh",
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    })
    return jwt.encode(
        to_encode,
        _get_private_pem(),
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": get_key_id()},
    )


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            _get_public_pem(),
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
        return payload
    except JWTError as e:
        logger.warning("Token invalido: %s", str(e))
        raise
