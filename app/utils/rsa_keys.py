import base64
import logging
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key

logger = logging.getLogger(__name__)

_KEY_ID = "travelhub-key-1"
_private_key = None
_jwk = None


def _load_or_generate_key():
    global _private_key, _jwk

    key_b64 = os.getenv("RSA_PRIVATE_KEY_B64")
    if key_b64:
        pem_bytes = base64.b64decode(key_b64)
        _private_key = load_pem_private_key(
            pem_bytes, password=None, backend=default_backend()
        )
        logger.info("RSA private key loaded from RSA_PRIVATE_KEY_B64")
    else:
        _private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )
        logger.info("RSA key pair generated in memory (ephemeral)")

    public_key = _private_key.public_key()
    public_numbers = public_key.public_numbers()

    n_bytes = public_numbers.n.to_bytes(256, byteorder="big")
    e_bytes = public_numbers.e.to_bytes(3, byteorder="big")

    _jwk = {
        "kty": "RSA",
        "kid": _KEY_ID,
        "use": "sig",
        "alg": "RS256",
        "n": base64.urlsafe_b64encode(n_bytes).rstrip(b"=").decode("utf-8"),
        "e": base64.urlsafe_b64encode(e_bytes).rstrip(b"=").decode("utf-8"),
    }
    logger.info("JWKS configured with kid=%s", _KEY_ID)


def get_private_key():
    if _private_key is None:
        _load_or_generate_key()
    return _private_key


def get_jwk() -> dict:
    if _jwk is None:
        _load_or_generate_key()
    return _jwk


def get_jwks() -> dict:
    return {"keys": [get_jwk()]}


def get_key_id() -> str:
    return _KEY_ID
