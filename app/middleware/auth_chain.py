import logging
from abc import ABC, abstractmethod

from fastapi import HTTPException, Request

from app.utils.jwt_handler import decode_token

logger = logging.getLogger(__name__)

PUBLIC_PATHS = [
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/.well-known/jwks.json",
    "/health",
    "/docs",
    "/openapi.json",
]


class AuthFilter(ABC):
    def __init__(self):
        self._next: AuthFilter | None = None

    def set_next(self, handler: "AuthFilter") -> "AuthFilter":
        self._next = handler
        return handler

    @abstractmethod
    async def handle(self, request: Request) -> dict:
        pass

    async def _call_next(self, request: Request) -> dict:
        if self._next:
            return await self._next.handle(request)
        return request.state.token_payload


class RateLimitFilter(AuthFilter):
    async def handle(self, request: Request) -> dict:
        return await self._call_next(request)


class TokenValidationFilter(AuthFilter):
    async def handle(self, request: Request) -> dict:
        auth_header = request.headers.get(
            "X-Forwarded-Authorization"
        ) or request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Token no proporcionado")

        token = auth_header.split(" ", 1)[1]
        try:
            payload = decode_token(token)
        except Exception:
            raise HTTPException(status_code=401, detail="Token invalido o expirado")

        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Se esperaba un access token")

        request.state.token_payload = payload
        request.state.user_id = payload.get("sub")
        request.state.user_role = payload.get("role")
        request.state.user_country = payload.get("country")
        request.state.mfa_verified = payload.get("mfa_verified", False)
        request.state.hotel_id = payload.get("hotel_id")

        return await self._call_next(request)


class IPValidationFilter(AuthFilter):
    async def handle(self, request: Request) -> dict:
        # Placeholder: validacion de geolocalizacion consistente
        return await self._call_next(request)


class RBACFilter(AuthFilter):
    def __init__(self, allowed_roles: list[str] | None = None):
        super().__init__()
        self._allowed_roles = allowed_roles or []

    async def handle(self, request: Request) -> dict:
        payload = request.state.token_payload
        if self._allowed_roles and payload.get("role") not in self._allowed_roles:
            raise HTTPException(status_code=403, detail="Rol insuficiente")
        return await self._call_next(request)


class MFAFilter(AuthFilter):
    def __init__(self, require_mfa_paths: list[str] | None = None):
        super().__init__()
        self._require_mfa_paths = require_mfa_paths or ["/payments", "/admin"]

    async def handle(self, request: Request) -> dict:
        path = request.url.path
        requires_mfa = any(path.startswith(p) for p in self._require_mfa_paths)
        if requires_mfa and not request.state.mfa_verified:
            raise HTTPException(status_code=403, detail="Verificacion MFA requerida")
        return await self._call_next(request)


def build_auth_chain(allowed_roles: list[str] | None = None) -> AuthFilter:
    rate_limit = RateLimitFilter()
    token_validation = TokenValidationFilter()
    ip_validation = IPValidationFilter()
    rbac_filter = RBACFilter(allowed_roles)
    mfa_filter = MFAFilter()

    rate_limit.set_next(token_validation)
    token_validation.set_next(ip_validation)
    ip_validation.set_next(rbac_filter)
    rbac_filter.set_next(mfa_filter)

    return rate_limit


async def get_current_user_id(request: Request) -> str:
    chain = build_auth_chain()
    payload = await chain.handle(request)
    return payload["sub"]


def require_roles(allowed_roles: list[str]):
    async def dependency(request: Request) -> str:
        chain = build_auth_chain(allowed_roles)
        payload = await chain.handle(request)
        return payload["sub"]

    return dependency
