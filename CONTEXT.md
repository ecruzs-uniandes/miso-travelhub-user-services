# CONTEXT.md — TravelHub user-services

> **Propósito de este archivo:** Pasar como contexto a Claude Code (CLI) para implementar el microservicio completo. Incluye todas las decisiones de diseño, reglas de negocio y convenciones del proyecto. **Las decisiones de arquitectura son finales y no deben modificarse.**

---

## 1. Resumen del Servicio

`user-services` es el microservicio de gestión de usuarios y autenticación de TravelHub, una plataforma de reservas hoteleras que opera en 6 países de Latinoamérica (~1,200 propiedades, ~450,000 viajeros). Este servicio implementa registro de usuarios (W07), login con JWT + MFA (W08), API Gateway con cadena de autenticación (I04), y RBAC. Es el primer servicio del ecosistema y debe funcionar como base para que los demás microservicios validen tokens. Despliega en GCP Cloud Run con PostgreSQL como base de datos.

---

## 2. Stack Técnico (versiones exactas)

| Componente | Tecnología | Versión |
|---|---|---|
| Lenguaje | Python | 3.12 |
| Framework web | FastAPI | 0.115.6 |
| Server ASGI | Uvicorn | 0.34.0 |
| ORM | SQLAlchemy (async) | 2.0.36 |
| Driver PostgreSQL (async) | asyncpg | 0.30.0 |
| Driver PostgreSQL (sync/Alembic) | psycopg2-binary | 2.9.10 |
| Migraciones | Alembic | 1.14.1 |
| Validación | Pydantic | 2.10.4 |
| Config | pydantic-settings | 2.7.1 |
| Hashing | bcrypt | 4.2.1 |
| JWT | python-jose[cryptography] | 3.3.0 |
| TOTP/MFA | pyotp | 2.9.0 |
| QR codes | qrcode[pil] | 8.0 |
| Testing | pytest + pytest-asyncio | 8.3.4 / 0.25.0 |
| Cobertura | pytest-cov | 6.0.0 |
| HTTP client (tests) | httpx | 0.28.1 |
| Contenedores | Docker + Docker Compose | latest |
| Base de datos local | PostgreSQL | 16 (Alpine) |
| Cloud | GCP Cloud Run | - |

---

## 3. Estructura de Directorios

```
user-services/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app, CORS, routers, health check
│   ├── config.py                  # pydantic-settings, env vars
│   ├── database.py                # AsyncSession engine, Base, get_db dependency
│   ├── models/
│   │   ├── __init__.py
│   │   └── user.py                # SQLAlchemy User model
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── user.py                # Pydantic request/response schemas
│   ├── routers/
│   │   ├── __init__.py
│   │   └── auth.py                # Auth endpoints (register, login, refresh, mfa, profile)
│   ├── services/
│   │   ├── __init__.py
│   │   └── auth_service.py        # Business logic layer
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── auth_chain.py          # Chain of Responsibility (AH008)
│   └── utils/
│       ├── __init__.py
│       ├── jwt_handler.py         # JWT create/decode
│       └── security.py            # bcrypt + TOTP helpers
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                  # Migration files
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Fixtures: async client, test DB, test user
│   ├── test_register.py           # W07 tests
│   ├── test_login.py              # W08 tests
│   ├── test_auth_chain.py         # AH008 chain tests
│   ├── test_mfa.py                # MFA flow tests
│   └── test_health.py             # Health check test
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── CONTEXT.md                     # Este archivo
```

### Convenciones de nombres

- **Archivos:** `snake_case.py`
- **Clases:** `PascalCase`
- **Funciones/variables:** `snake_case`
- **Endpoints:** `kebab-case` en URL (ej. `/auth/mfa/setup`), `snake_case` en funciones
- **Tablas BD:** `snake_case` plural (ej. `users`)
- **Columnas BD:** `snake_case` (ej. `fecha_registro`)

---

## 4. Modelo de Datos — DDL PostgreSQL

```sql
-- ============================================================
-- Tabla: users
-- Entidad del dominio: Viajero (VC-005)
-- Microservicio: user-services
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TYPE user_role AS ENUM ('viajero', 'admin_hotel', 'admin_sistema');

CREATE TABLE users (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email                VARCHAR(255) NOT NULL UNIQUE,
    username             VARCHAR(100) NOT NULL UNIQUE,
    nombre               VARCHAR(255) NOT NULL,
    hashed_password      VARCHAR(255) NOT NULL,
    telefono             VARCHAR(50),
    pais                 VARCHAR(100),
    idioma               VARCHAR(10)  NOT NULL DEFAULT 'es',
    moneda_preferida     VARCHAR(10)  NOT NULL DEFAULT 'USD',

    -- Seguridad / MFA (AH008)
    mfa_activo           BOOLEAN      NOT NULL DEFAULT FALSE,
    mfa_secret           VARCHAR(255),
    failed_login_attempts INTEGER     NOT NULL DEFAULT 0,
    locked_until         TIMESTAMPTZ,

    -- RBAC
    rol                  VARCHAR(50)  NOT NULL DEFAULT 'viajero',

    -- Auditoría
    activo               BOOLEAN      NOT NULL DEFAULT TRUE,
    fecha_registro       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    fecha_actualizacion  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Índices
CREATE INDEX idx_users_email    ON users (email);
CREATE INDEX idx_users_username ON users (username);
CREATE INDEX idx_users_rol      ON users (rol);
CREATE INDEX idx_users_pais     ON users (pais);

-- Trigger para auto-actualizar fecha_actualizacion
CREATE OR REPLACE FUNCTION update_fecha_actualizacion()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fecha_actualizacion = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_fecha_actualizacion();
```

### Campos del dominio (VC-005) → Columnas

| Campo dominio | Columna | Tipo | Nota |
|---|---|---|---|
| id | `id` | UUID | PK, auto-generado |
| email | `email` | VARCHAR(255) | UNIQUE, NOT NULL |
| nombre | `nombre` | VARCHAR(255) | NOT NULL |
| telefono | `telefono` | VARCHAR(50) | nullable |
| pais | `pais` | VARCHAR(100) | nullable, ISO 3166 recomendado |
| idioma | `idioma` | VARCHAR(10) | default 'es' |
| monedaPreferida | `moneda_preferida` | VARCHAR(10) | default 'USD' |
| mfaActivo | `mfa_activo` | BOOLEAN | default FALSE |
| fechaRegistro | `fecha_registro` | TIMESTAMPTZ | auto |
| — (agregado) | `username` | VARCHAR(100) | UNIQUE, para login |
| — (agregado) | `hashed_password` | VARCHAR(255) | bcrypt hash |
| — (agregado) | `mfa_secret` | VARCHAR(255) | TOTP base32 secret |
| — (agregado) | `failed_login_attempts` | INTEGER | brute force counter |
| — (agregado) | `locked_until` | TIMESTAMPTZ | account lockout |
| — (agregado) | `rol` | VARCHAR(50) | RBAC: viajero, admin_hotel, admin_sistema |
| — (agregado) | `activo` | BOOLEAN | soft delete |

---

## 5. Endpoints — Firmas Exactas

Prefijo base: `/api/v1`

### Públicos (sin autenticación)

```
POST /api/v1/auth/register
  Request:  UserRegisterRequest  → { email, username, nombre, password, telefono?, pais?, idioma?, moneda_preferida? }
  Response: 201 UserResponse     → { id, email, username, nombre, telefono, pais, idioma, moneda_preferida, mfa_activo, rol, fecha_registro }
  Errors:   409 (duplicado), 422 (validación)

POST /api/v1/auth/login
  Request:  UserLoginRequest     → { email, password, totp_code? }
  Response: 200 TokenResponse    → { access_token, refresh_token, token_type, expires_in }
  Errors:   401 (credenciales), 423 (cuenta bloqueada), 428 (MFA requerido)

POST /api/v1/auth/refresh
  Request:  RefreshTokenRequest  → { refresh_token }
  Response: 200 TokenResponse
  Errors:   401 (token inválido)
```

### Protegidos (requieren Bearer token)

```
GET /api/v1/auth/me
  Headers:  Authorization: Bearer <access_token>
  Response: 200 UserResponse
  Errors:   401 (token inválido/expirado)

POST /api/v1/auth/mfa/setup
  Headers:  Authorization: Bearer <access_token>
  Response: 200 MFASetupResponse → { secret, qr_uri }
  Errors:   401

POST /api/v1/auth/mfa/verify
  Headers:  Authorization: Bearer <access_token>
  Request:  MFAVerifyRequest     → { totp_code }
  Response: 200 MessageResponse  → { message }
  Errors:   401 (código inválido), 400 (MFA no configurado)
```

### Infraestructura

```
GET /health
  Response: 200 → { status: "healthy", service: "user-services", version: "1.0.0" }
```

---

## 6. Reglas de Negocio (assertions verificables)

### Registro (W07)

```python
assert len(password) >= 8                        # Mínimo 8 caracteres
assert len(username) >= 3                        # Mínimo 3 caracteres
assert email is valid                            # Validación por Pydantic EmailStr
assert not exists(User.email == email)           # Email único
assert not exists(User.username == username)     # Username único
assert password is stored as bcrypt hash         # Nunca en texto plano
assert new_user.rol == "viajero"                 # Rol por defecto
assert new_user.mfa_activo == False              # MFA desactivado por defecto
assert response.status_code == 201               # Created
assert "hashed_password" not in response.json()  # Nunca exponer hash
```

### Login (W08)

```python
assert valid_email and valid_password → 200 + tokens
assert invalid_password → 401 + failed_login_attempts += 1
assert failed_login_attempts >= 5 → locked_until = now + 15min
assert account_locked → 423 (sin verificar password)
assert successful_login → failed_login_attempts = 0, locked_until = None
assert mfa_activo and no totp_code → 428
assert mfa_activo and invalid totp_code → 401
assert mfa_activo and valid totp_code → 200 + tokens
```

### JWT

```python
assert access_token.payload contains { sub: user_id, rol, type: "access", exp, iat }
assert refresh_token.payload contains { sub: user_id, type: "refresh", exp, iat }
assert access_token expires in 30 minutes
assert refresh_token expires in 7 days
assert expired_token → 401
assert token_type != "access" on protected endpoint → 401
assert refresh with access_token → 401 (type mismatch)
```

### MFA (AH008)

```python
assert mfa_setup generates 32-char base32 secret
assert qr_uri starts with "otpauth://totp/TravelHub:"
assert verify_totp allows valid_window=1 (±30 seconds)
assert successful verify → user.mfa_activo = True
assert mfa_verify without prior setup → 400
```

### Chain of Responsibility (AH008)

```python
assert no Authorization header → 401
assert malformed Bearer token → 401
assert expired token → 401
assert valid token + wrong role → 403
assert valid token + correct role → 200 (passes through chain)
assert chain order: RateLimit → TokenValidation → Role
```

---

## 7. Patrones Obligatorios

### 7.1 Patrón: Chain of Responsibility (GoF) — AH008

Implementado en `app/middleware/auth_chain.py`. La cadena de filtros de autenticación sigue este orden:

```
Request → RateLimitFilter → TokenValidationFilter → RoleFilter → Handler
```

Cada filtro hereda de `AuthFilter` (abstract). Tiene `set_next()` y `handle()`. Cada filtro puede aprobar (pasar al siguiente) o rechazar (HTTPException). **No modificar el orden de la cadena.**

### 7.2 Error Handling

Todas las excepciones de negocio usan `fastapi.HTTPException` con códigos estándar:

| Código | Uso |
|---|---|
| 201 | Recurso creado (registro) |
| 200 | Operación exitosa |
| 400 | Bad request (MFA no configurado, datos inválidos) |
| 401 | No autenticado / credenciales inválidas / token expirado |
| 403 | No autorizado (RBAC, rol insuficiente) |
| 409 | Conflicto (email/username duplicado) |
| 422 | Validación de Pydantic (automático) |
| 423 | Cuenta bloqueada (lockout por brute force) |
| 428 | Precondición requerida (código MFA faltante) |

Formato de error estándar:
```json
{
  "detail": "Mensaje descriptivo en español"
}
```

### 7.3 Logging

```python
import logging

logger = logging.getLogger(__name__)

# Niveles:
logger.info("Usuario registrado: %s", user.email)      # Operaciones exitosas
logger.warning("Login fallido para: %s", email)         # Intentos fallidos
logger.error("Error en DB: %s", str(e))                 # Errores de sistema
logger.critical("JWT secret no configurado")             # Configuración crítica

# NUNCA loguear:
# - Contraseñas (ni en texto plano ni hash)
# - Tokens JWT completos
# - mfa_secret
# - Datos de tarjeta (PCI-DSS)
```

### 7.4 Estructura de capas

```
Router (recibe HTTP) → Service (lógica de negocio) → Model (acceso a datos)
```

- **Router:** Solo recibe request, llama al service, retorna response. Sin lógica de negocio.
- **Service:** Toda la lógica de negocio. Recibe `AsyncSession` como dependencia. Lanza `HTTPException`.
- **Model:** SQLAlchemy ORM. Sin lógica de negocio.

### 7.5 Testing

```python
# Estructura de cada test file:
# 1. Fixtures específicas del test
# 2. Tests del happy path
# 3. Tests de errores y edge cases

# conftest.py debe proveer:
# - async_client: httpx.AsyncClient apuntando a test app
# - test_db: AsyncSession con rollback automático
# - test_user: usuario pre-creado para tests de login
# - auth_headers: dict con Authorization Bearer válido

# Naming convention:
# test_<action>_<scenario>_<expected>
# Ejemplo: test_register_duplicate_email_returns_409
```

**Cobertura mínima:** 80% en servicios críticos (`auth_service.py`, `auth_chain.py`).

### 7.6 Async everywhere

- Todo acceso a DB usa `async/await` con `AsyncSession`.
- Nunca usar operaciones síncronas de SQLAlchemy (`Session`).
- El driver async es `asyncpg`. El sync (`psycopg2`) solo se usa en Alembic.

---

## 8. Comandos

### Desarrollo local

```bash
# Levantar PostgreSQL + servicio con hot reload
docker-compose up -d

# Solo la base de datos (para correr uvicorn manualmente)
docker-compose up -d db

# Correr el servicio localmente (sin Docker)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Ver docs de la API
open http://localhost:8000/docs
```

### Migraciones (Alembic)

```bash
# Generar migración a partir de cambios en modelos
alembic revision --autogenerate -m "descripción del cambio"

# Aplicar migraciones
alembic upgrade head

# Rollback una migración
alembic downgrade -1

# Ver estado actual
alembic current
```

### Tests

```bash
# Correr todos los tests
pytest

# Con cobertura
pytest --cov=app --cov-report=term-missing

# Solo un archivo
pytest tests/test_register.py -v

# Solo tests que matchean un nombre
pytest -k "test_login" -v
```

### Build y Deploy (Cloud Run)

```bash
# Build imagen de producción
docker build --target production -t gcr.io/<PROJECT_ID>/user-services:latest .

# Push a Container Registry
docker push gcr.io/<PROJECT_ID>/user-services:latest

# Deploy a Cloud Run
gcloud run deploy user-services \
  --image gcr.io/<PROJECT_ID>/user-services:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "DATABASE_URL=<PROD_DB_URL>,JWT_SECRET_KEY=<PROD_SECRET>,ENVIRONMENT=production" \
  --min-instances 1 \
  --max-instances 10 \
  --memory 512Mi \
  --cpu 1 \
  --port 8000
```

### Lint / Format

```bash
# Format
black app/ tests/
isort app/ tests/

# Lint
ruff check app/ tests/
mypy app/
```

---

## 9. Lo que NO debe hacer (Anti-patterns)

### Seguridad — NUNCA

- ❌ Almacenar contraseñas en texto plano o con MD5/SHA.
- ❌ Loguear contraseñas, tokens JWT, mfa_secret, o datos de tarjeta.
- ❌ Retornar `hashed_password` o `mfa_secret` en ningún response JSON.
- ❌ Usar un JWT secret hardcodeado en producción (dev-only OK para local).
- ❌ Permitir login sin verificar lockout (`locked_until`) primero.
- ❌ Aceptar refresh tokens donde se espera access tokens (y viceversa).

### Arquitectura — NUNCA

- ❌ Poner lógica de negocio en los routers. Los routers solo reciben y delegan al service.
- ❌ Usar SQLAlchemy síncrono (`Session`) en los endpoints. Todo es `AsyncSession`.
- ❌ Hacer queries SQL raw cuando SQLAlchemy ORM puede resolverlo.
- ❌ Importar modelos de otros microservicios. Cada servicio tiene sus propios modelos.
- ❌ Comunicación directa (HTTP sync) entre microservicios para operaciones críticas. Usar eventos async (Kafka/Pub-Sub) — pero esto se implementa en sprints posteriores.
- ❌ Cambiar el orden de la Chain of Responsibility (Rate Limit → Token → Role).
- ❌ Modificar las decisiones de arquitectura de PF1 (están aprobadas y entregadas).

### Código — NUNCA

- ❌ `from app.* import *` — siempre imports explícitos.
- ❌ Funciones de más de 40 líneas. Extraer a helpers privados.
- ❌ `try/except Exception: pass` — siempre manejar o re-raise.
- ❌ Tests sin assertions. Todo test debe tener al menos un `assert`.
- ❌ Dejar `print()` en código de producción. Usar `logging`.
- ❌ Hardcodear strings de configuración. Todo va en `config.py` / env vars.

### Base de Datos — NUNCA

- ❌ SQLite en producción. Solo PostgreSQL.
- ❌ Migraciones manuales con `ALTER TABLE`. Todo via Alembic.
- ❌ Borrar datos físicamente. Usar soft delete (`activo = False`).
- ❌ Índices faltantes en columnas de búsqueda frecuente (`email`, `username`).

---

## 10. Referencia Rápida — Patrones del Proyecto

Estos patrones fueron definidos en PF1 y deben respetarse:

| Patrón | Dónde aplica en user-services | ASR |
|---|---|---|
| **Chain of Responsibility** (GoF) | `middleware/auth_chain.py` — cadena de filtros de auth | AH008 (Seguridad) |
| **Strategy** (GoF) | Futuro: algoritmos de cifrado intercambiables | AH007 |
| **Decorator** (GoF) | Futuro: instrumentación de métricas sin alterar lógica | AH015 |
| **SOLID — Single Responsibility** | Cada archivo tiene una sola razón de cambio | AH011 |
| **SOLID — Open/Closed** | AuthFilter extensible sin modificar la cadena existente | AH008 |
| **GRASP — Low Coupling** | Service no conoce HTTP; Router no conoce DB queries | General |

---

## 11. Variables de Entorno

```env
# .env.example
DATABASE_URL=postgresql+asyncpg://travelhub:travelhub_dev@localhost:5432/travelhub_users
DATABASE_URL_SYNC=postgresql+psycopg2://travelhub:travelhub_dev@localhost:5432/travelhub_users
JWT_SECRET_KEY=dev-secret-key-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
BCRYPT_ROUNDS=12
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_MINUTES=15
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60
ENVIRONMENT=development
DEBUG=true
```

---

## 12. Configuración de Alembic

`alembic.ini` debe apuntar a `DATABASE_URL_SYNC` (psycopg2, no asyncpg).

`alembic/env.py` debe importar `Base` y todos los modelos:
```python
from app.database import Base
from app.models import User  # Importar para que Alembic detecte los modelos
target_metadata = Base.metadata
```

---

## 13. Criterios de Aceptación (Definition of Done)

Un endpoint se considera completo cuando:

1. ✅ El endpoint responde según la firma documentada en la sección 5
2. ✅ Todas las reglas de negocio de la sección 6 pasan como tests
3. ✅ Cobertura de tests ≥ 80% para el service asociado
4. ✅ `pytest` pasa sin errores
5. ✅ `docker-compose up` levanta el servicio sin errores
6. ✅ El endpoint aparece en Swagger (`/docs`)
7. ✅ No hay ningún anti-pattern de la sección 9
8. ✅ Los logs siguen el formato de la sección 7.3

---

## 14. Contexto del Proyecto (para entender decisiones)

- **Proyecto:** TravelHub — plataforma de reservas hoteleras para LATAM
- **Curso:** MISW4501/4502 — Universidad de los Andes, Maestría en Ingeniería de Software
- **Fase:** Proyecto Final 2, Sprint 1 (Semana 0)
- **Equipo:** 4 personas. Edwin (autor) se encarga de I01, I03 (parcial), I04, W07, W08.
- **PF1 ya entregado:** Arquitectura aprobada, patrones validados experimentalmente, prototipos web/móvil.
- **Deuda técnica conocida:** Rate limiting distribuido (migrar a Redis), gestión de secretos JWT (migrar a Cloud KMS), observabilidad (Cloud Trace).
