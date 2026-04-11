# CLAUDE.md — user-services

## Comandos

```bash
# Dev local
docker-compose up -d                # PostgreSQL + servicio
docker-compose up -d db             # Solo BD (para uvicorn manual)
uvicorn app.main:app --reload --port 8000

# Tests
pytest                              # Todos
pytest --cov=app --cov-report=term-missing  # Con cobertura (≥80% en auth_service, auth_chain)
pytest tests/test_register.py -v    # Un archivo
pytest -k "test_login" -v           # Por nombre

# Migraciones (Alembic usa DATABASE_URL_SYNC con psycopg2, NO asyncpg)
alembic revision --autogenerate -m "descripción"
alembic upgrade head
alembic downgrade -1

# Lint (debe pasar antes del push — CI lo valida)
isort app/ tests/ && black app/ tests/
ruff check app/ tests/

# Docker build
docker build --target production -t user-services:latest .
```

## CI/CD

Pipeline en `.github/workflows/ci.yml`. Se ejecuta automáticamente en cada push.

| Rama | Acción |
|------|--------|
| `feature/*`, `develop` | Tests + Lint + Build + Deploy a **DEV** (Cloud Run directo) |
| `main` | Tests + Lint + Build + **Cloud Deploy canary** a PROD (10%→50%→100%, requiere aprobación) |
| PR a `main`/`develop` | Tests + Lint + Docker Build (sin deploy) |

### Variables de entorno en CI/CD
- **No sensibles** (JWT config, rate limits, etc.): definidas en `ci.yml` (dev) y `k8s/service-prod.yaml` (prod)
- **Secrets** (`DATABASE_URL`, `DATABASE_URL_SYNC`): GCP Secret Manager, inyectados via `--set-secrets`
- **Guía de setup GCP**: `docs/gcp-setup.md`

### Proyectos GCP
- **DEV**: `gen-lang-client-0930444414` (Cloud Run directo, deploy automático)
- **PROD**: configurado via secret `GCP_PROJECT_ID` (Cloud Deploy con canary + aprobación manual)

## Stack

Python 3.12 · FastAPI 0.115.6 · SQLAlchemy async 2.0.36 · asyncpg 0.30.0 · Pydantic 2.10.4 · Alembic 1.14.1 · bcrypt 4.2.1 · python-jose 3.3.0 · cryptography 44.0.0 · pyotp 2.9.0 · PostgreSQL 16

## Estructura

```
app/
├── main.py              # App, CORS, routers, health, JWKS endpoint
├── config.py            # pydantic-settings, env vars
├── database.py          # AsyncSession, Base, get_db
├── models/user.py       # SQLAlchemy User (incluye hotel_id)
├── schemas/user.py      # Pydantic request/response
├── routers/auth.py      # Endpoints HTTP (sin lógica de negocio)
├── services/auth_service.py  # Toda la lógica de negocio + mapeo de roles
├── middleware/auth_chain.py  # Chain of Responsibility: RateLimit → Token → IPValidation → RBAC → MFA
└── utils/
    ├── jwt_handler.py   # JWT create/decode (RS256)
    ├── rsa_keys.py      # Generación RSA 2048, JWKS
    └── security.py      # bcrypt + TOTP
tests/
├── conftest.py          # Fixtures: async_client, test_db, test_user, auth_headers
├── test_register.py     # W07
├── test_login.py        # W08
├── test_auth_chain.py   # AH008
├── test_mfa.py          # MFA
└── test_health.py
.github/workflows/
└── ci.yml               # Pipeline CI/CD (tests, lint, deploy dev/prod)
clouddeploy.yaml         # Cloud Deploy pipeline (prod canary: 10%→50%→100%)
skaffold.yaml            # Skaffold config con health verification (prod)
k8s/
└── service-prod.yaml    # Manifiesto Cloud Run producción (env vars + secrets)
docs/
└── gcp-setup.md         # Guía de configuración GCP por primera vez
```

## Arquitectura — Reglas obligatorias

- **Capas:** Router → Service → Model. Routers solo reciben/delegan. Services tienen la lógica. Models sin lógica.
- **Async everywhere:** Solo `AsyncSession` en endpoints. `psycopg2` solo en Alembic.
- **Chain of Responsibility (AH008):** Orden fijo `RateLimitFilter → TokenValidationFilter → IPValidationFilter → RBACFilter → MFAFilter`. Cada filtro hereda de `AuthFilter` con `set_next()` y `handle()`. No cambiar el orden.
- **JWT con RS256:** Claves RSA 2048 generadas al arrancar. Clave pública expuesta en `/.well-known/jwks.json`. Header incluye `kid: "travelhub-key-1"`.
- **Roles gateway:** El JWT usa roles en inglés (`traveler`, `hotel_admin`, `platform_admin`). El mapeo desde BD (`viajero`, etc.) se hace en `_generate_tokens()`.

## Convenciones

- Archivos: `snake_case.py` · Clases: `PascalCase` · URLs: `kebab-case` · Tablas: `snake_case` plural
- Tests: `test_<action>_<scenario>_<expected>` (ej. `test_register_duplicate_email_returns_409`)
- Errores: `HTTPException` con `{"detail": "Mensaje en español"}`
- Logging: `logging.getLogger(__name__)` — info (éxito), warning (fallo), error (sistema)

## Reglas de negocio clave

### Registro
- Password ≥ 8 chars, username ≥ 3 chars, email validado por Pydantic
- Email y username únicos (409 si duplicado)
- Rol default: `viajero`, MFA default: `False`
- Nunca retornar `hashed_password` ni `mfa_secret` en responses

### Login
- Verificar lockout (`locked_until`) ANTES de verificar password
- 5 intentos fallidos → bloqueo 15 min (423)
- Login exitoso → reset `failed_login_attempts` y `locked_until`
- MFA activo sin `totp_code` → 428; código inválido → 401

### JWT

- Algoritmo: RS256 (RSA 2048). Claves generadas en memoria al arrancar.
- Access token: 15 min (900s), payload `{sub, role, mfa_verified, country, hotel_id, iss, aud, type: "access", exp, iat}`
- Refresh token: 7 días (604800s), payload `{sub, role, mfa_verified, country, hotel_id, iss, aud, type: "refresh", exp, iat}`
- `iss` = `https://auth.travelhub.app`, `aud` = `travelhub-api`
- Header JWT incluye `kid: "travelhub-key-1"`
- Nunca aceptar refresh donde se espera access (y viceversa)
- Endpoint JWKS: `GET /.well-known/jwks.json` expone la clave pública para el API Gateway

### Update User

- `PUT /api/v1/auth/me` — solo permite actualizar `nombre`, `password` y `telefono`
- Todos los campos son opcionales; solo se actualizan los enviados
- Password se hashea con bcrypt antes de guardar

### MFA
- Setup genera secret base32 de 32 chars, QR URI `otpauth://totp/TravelHub:...`
- Verify con `valid_window=1` (±30s). Éxito → `mfa_activo = True`
- Verify sin setup previo → 400

## Códigos HTTP

| Código | Uso |
|--------|-----|
| 201 | Registro exitoso |
| 200 | Operación exitosa |
| 400 | MFA no configurado / datos inválidos |
| 401 | Credenciales / token inválido o expirado |
| 403 | Rol insuficiente (RBAC) |
| 409 | Email/username duplicado |
| 423 | Cuenta bloqueada |
| 428 | Código MFA requerido |

## Infraestructura desplegada (DEV)

| Capa | Recurso |
|------|---------|
| Cloud Run | `user-services` → `https://user-services-ridyy4wz4q-uc.a.run.app` |
| API Gateway | `https://travelhub-gateway-1yvtqj7r.uc.gateway.dev` |
| JWKS | `https://user-services-ridyy4wz4q-uc.a.run.app/.well-known/jwks.json` |
| Cloud SQL | `travelhub-db` (PostgreSQL 15, IP privada `10.100.0.3`) |
| VPC | `travelhub-vpc` con 3 subnets + VPC connector `travelhub-connector` |
| Cloud Armor | `travelhub-security-policy` (WAF + rate limiting + geo-blocking) |

## Integración gateway ↔ backend

- El API Gateway reemplaza el header `Authorization` con un OIDC token de servicio y mueve el JWT original del usuario a `X-Forwarded-Authorization`.
- El middleware `TokenValidationFilter` lee primero `X-Forwarded-Authorization` y luego `Authorization` como fallback.
- Las claves RSA se persisten via variable de entorno `RSA_PRIVATE_KEY_B64` (base64 del PEM). Se setea con `gcloud run services update`.
- Al redesplegar con una nueva clave RSA, hay que redesplegar la config del API Gateway para que refresque el JWKS cacheado.
- Rutas públicas (no pasan por el chain): `/api/v1/auth/login`, `/api/v1/auth/register`, `/api/v1/auth/refresh`, `/.well-known/jwks.json`, `/health`, `/docs`, `/openapi.json`

## NUNCA

- Contraseñas en texto plano o MD5/SHA — solo bcrypt
- Loguear passwords, tokens JWT, mfa_secret
- `from app.* import *` — imports explícitos
- Funciones > 40 líneas
- `try/except Exception: pass`
- `print()` en producción — usar logging
- SQL raw si SQLAlchemy ORM lo resuelve
- DELETE físico — usar soft delete (`activo = False`)
- SQLite en producción
