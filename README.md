# TravelHub User Services

Microservicio de gestion de usuarios y autenticacion de la plataforma TravelHub. Provee registro de usuarios, autenticacion mediante JWT con soporte para autenticacion multifactor (TOTP), control de acceso basado en roles (RBAC) y un API Gateway implementado con el patron Chain of Responsibility.

Este servicio es el componente central del ecosistema de microservicios de TravelHub y actua como autoridad de identidad para la validacion de tokens en los demas servicios.

---

## Tabla de Contenidos

1. [Arquitectura](#arquitectura)
2. [Stack Tecnologico](#stack-tecnologico)
3. [Estructura del Proyecto](#estructura-del-proyecto)
4. [Instalacion y Configuracion](#instalacion-y-configuracion)
5. [Ejecucion](#ejecucion)
6. [API Reference](#api-reference)
7. [Autenticacion y Autorizacion](#autenticacion-y-autorizacion)
8. [Base de Datos y Migraciones](#base-de-datos-y-migraciones)
9. [Pruebas](#pruebas)
10. [Despliegue](#despliegue)
11. [Coleccion Postman](#coleccion-postman)

---

## Arquitectura

El servicio sigue una arquitectura de capas con separacion estricta de responsabilidades:

```
Request HTTP
    |
    v
Router (auth.py)            -- Recibe HTTP, delega al Service. Sin logica de negocio.
    |
    v
Middleware (auth_chain.py)   -- Chain of Responsibility: RateLimit -> Token -> IPValidation -> RBAC -> MFA
    |
    v
Service (auth_service.py)   -- Toda la logica de negocio. Lanza HTTPException.
    |
    v
Model (user.py)             -- SQLAlchemy ORM. Sin logica de negocio.
    |
    v
PostgreSQL (asyncpg)
```

### Patrones de Diseno Implementados

| Patron | Ubicacion | Proposito |
|--------|-----------|-----------|
| Chain of Responsibility (GoF) | `app/middleware/auth_chain.py` | Cadena de filtros de autenticacion: RateLimitFilter, TokenValidationFilter, IPValidationFilter, RBACFilter, MFAFilter |
| Repository (implicito) | `app/services/auth_service.py` | Acceso a datos mediante SQLAlchemy AsyncSession |
| Dependency Injection | Routers via FastAPI `Depends()` | Inyeccion de sesion de BD y autenticacion |
| SOLID - Single Responsibility | Todas las capas | Cada modulo tiene una unica razon de cambio |
| SOLID - Open/Closed | `AuthFilter` | Extensible sin modificar la cadena existente |

### Chain of Responsibility

La cadena de autenticacion procesa cada request protegido en orden fijo e inmutable:

```
RateLimitFilter -> TokenValidationFilter -> IPValidationFilter -> RBACFilter -> MFAFilter -> Handler
```

Cada filtro hereda de la clase abstracta `AuthFilter` e implementa el metodo `handle()`. Un filtro puede aprobar la solicitud (delegando al siguiente) o rechazarla (lanzando `HTTPException`).

---

## Stack Tecnologico

| Componente | Tecnologia | Version |
|------------|------------|---------|
| Lenguaje | Python | 3.12 |
| Framework Web | FastAPI | 0.115.6 |
| Servidor ASGI | Uvicorn | 0.34.0 |
| ORM | SQLAlchemy (async) | 2.0.36 |
| Driver PostgreSQL (async) | asyncpg | 0.30.0 |
| Driver PostgreSQL (sync/Alembic) | psycopg2-binary | 2.9.10 |
| Migraciones | Alembic | 1.14.1 |
| Validacion | Pydantic | 2.10.4 |
| Configuracion | pydantic-settings | 2.7.1 |
| Hashing de contrasenas | bcrypt | 4.2.1 |
| Tokens JWT | python-jose[cryptography] | 3.3.0 |
| Criptografia RSA | cryptography | 44.0.0 |
| TOTP/MFA | pyotp | 2.9.0 |
| Codigos QR | qrcode[pil] | 8.0 |
| Testing | pytest + pytest-asyncio | 8.3.4 / 0.25.0 |
| Cobertura | pytest-cov | 6.0.0 |
| Cliente HTTP (tests) | httpx | 0.28.1 |
| Base de datos | PostgreSQL | 16 (Alpine) |
| Contenedores | Docker + Docker Compose | latest |
| Cloud | GCP Cloud Run | - |

---

## Estructura del Proyecto

```
user-services/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app, CORS, routers, health check
│   ├── config.py                   # pydantic-settings, variables de entorno
│   ├── database.py                 # AsyncSession engine, Base, get_db
│   ├── models/
│   │   └── user.py                 # Modelo SQLAlchemy: User
│   ├── schemas/
│   │   └── user.py                 # Schemas Pydantic: request/response
│   ├── routers/
│   │   └── auth.py                 # Endpoints HTTP (register, login, refresh, me, mfa)
│   ├── services/
│   │   └── auth_service.py         # Logica de negocio
│   ├── middleware/
│   │   └── auth_chain.py           # Chain of Responsibility (AH008)
│   └── utils/
│       ├── jwt_handler.py          # Creacion y decodificacion de JWT (RS256)
│       ├── rsa_keys.py             # Generacion de claves RSA 2048, JWKS
│       └── security.py             # bcrypt + TOTP helpers
├── alembic/
│   ├── env.py                      # Configuracion de migraciones
│   └── versions/                   # Archivos de migracion
├── tests/
│   ├── conftest.py                 # Fixtures: async_client, test_db, db_session
│   ├── test_register.py            # Tests de registro (W07)
│   ├── test_login.py               # Tests de login (W08)
│   ├── test_refresh.py             # Tests de refresh token
│   ├── test_auth_chain.py          # Tests de Chain of Responsibility (AH008)
│   ├── test_mfa.py                 # Tests de flujo MFA
│   └── test_health.py              # Test de health check
├── postman/
│   ├── user-services.postman_collection.json
│   └── user-services.postman_environment.json
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .coveragerc
└── pytest.ini
```

---

## Instalacion y Configuracion

### Prerrequisitos

- Python 3.12
- Docker y Docker Compose
- PostgreSQL 16 (provisto via Docker)

### Variables de Entorno

Crear un archivo `.env` en la raiz del proyecto con las siguientes variables:

```env
DATABASE_URL=postgresql+asyncpg://travelhub:travelhub_dev@localhost:5432/travelhub_users
DATABASE_URL_SYNC=postgresql+psycopg2://travelhub:travelhub_dev@localhost:5432/travelhub_users
JWT_SECRET_KEY=dev-secret-key-change-in-production
JWT_ALGORITHM=RS256
JWT_ISSUER=https://auth.travelhub.app
JWT_AUDIENCE=travelhub-api
JWT_ACCESS_TTL=900
JWT_REFRESH_TTL=604800
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
BCRYPT_ROUNDS=12
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_MINUTES=15
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60
ENVIRONMENT=development
DEBUG=true
```

> **Importante:** En produccion, las claves RSA deberian gestionarse mediante Cloud KMS o un servicio de secretos equivalente. Para este sprint se generan en memoria al arrancar.

### Instalacion Local

```bash
# Clonar el repositorio
git clone <repository-url>
cd user-services

# Crear y activar entorno virtual
python3.12 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

---

## Ejecucion

### Con Docker Compose (recomendado)

```bash
# Levantar PostgreSQL y el servicio con hot reload
docker-compose up -d

# Verificar estado
docker-compose ps
```

### Ejecucion Manual

```bash
# Levantar solo la base de datos
docker-compose up -d db

# Aplicar migraciones
alembic upgrade head

# Iniciar el servidor de desarrollo
uvicorn app.main:app --reload --port 8000
```

### Verificacion

```bash
curl http://localhost:8000/health
```

Respuesta esperada:
```json
{
  "status": "healthy",
  "service": "user-services",
  "version": "1.0.0"
}
```

La documentacion interactiva de la API esta disponible en `http://localhost:8000/docs` (Swagger UI).

---

## API Reference

Prefijo base: `/api/v1`

### Endpoints Publicos

#### POST /api/v1/auth/register

Registra un nuevo usuario en la plataforma.

**Request Body:**
```json
{
  "email": "usuario@example.com",
  "username": "usuario01",
  "nombre": "Juan Perez",
  "password": "securepass123",
  "telefono": "+57 300 1234567",
  "pais": "CO",
  "idioma": "es",
  "moneda_preferida": "COP"
}
```

Los campos `telefono`, `pais`, `idioma` y `moneda_preferida` son opcionales. Los valores por defecto de `idioma` y `moneda_preferida` son `"es"` y `"USD"` respectivamente.

**Validaciones:**
- `email`: formato valido (Pydantic EmailStr)
- `username`: minimo 3 caracteres
- `password`: minimo 8 caracteres
- `nombre`: minimo 1 caracter

**Response 201:**
```json
{
  "id": "uuid",
  "email": "usuario@example.com",
  "username": "usuario01",
  "nombre": "Juan Perez",
  "telefono": "+57 300 1234567",
  "pais": "CO",
  "idioma": "es",
  "moneda_preferida": "COP",
  "mfa_activo": false,
  "rol": "viajero",
  "fecha_registro": "2026-03-28T00:00:00Z"
}
```

**Errores:**

| Codigo | Condicion |
|--------|-----------|
| 409 | Email o username ya registrado |
| 422 | Error de validacion en los campos |

---

#### POST /api/v1/auth/login

Autentica un usuario y retorna tokens JWT.

**Request Body:**
```json
{
  "email": "usuario@example.com",
  "password": "securepass123",
  "totp_code": "123456"
}
```

El campo `totp_code` es obligatorio unicamente cuando el usuario tiene MFA activado.

**Response 200:**
```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 900
}
```

**Errores:**

| Codigo | Condicion |
|--------|-----------|
| 401 | Credenciales invalidas o codigo MFA invalido |
| 423 | Cuenta bloqueada por multiples intentos fallidos |
| 428 | MFA activo y campo `totp_code` no proporcionado |

**Politica de bloqueo:** Tras 5 intentos fallidos consecutivos, la cuenta se bloquea durante 15 minutos. El bloqueo se verifica antes de validar la contrasena. Un login exitoso reinicia el contador de intentos fallidos.

---

#### POST /api/v1/auth/refresh

Renueva los tokens JWT utilizando un refresh token valido.

**Request Body:**
```json
{
  "refresh_token": "eyJhbGciOi..."
}
```

**Response 200:** Misma estructura que la respuesta de login.

**Errores:**

| Codigo | Condicion |
|--------|-----------|
| 401 | Token invalido, expirado, o se proporciono un access token en lugar de refresh token |

---

### Endpoints Protegidos

Todos los endpoints protegidos requieren el header `Authorization: Bearer <access_token>`. La autenticacion se procesa mediante la Chain of Responsibility descrita en la seccion de Arquitectura.

#### GET /api/v1/auth/me

Retorna el perfil del usuario autenticado.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response 200:** Misma estructura que la respuesta de registro.

**Errores:**

| Codigo | Condicion |
|--------|-----------|
| 401 | Token no proporcionado, invalido, expirado, o de tipo incorrecto |

---

#### PUT /api/v1/auth/me

Actualiza el perfil del usuario autenticado. Solo permite modificar `nombre`, `password` y `telefono`. Todos los campos son opcionales; solo se actualizan los que se envian.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "nombre": "Nuevo Nombre",
  "password": "nuevapass123",
  "telefono": "+57 300 9876543"
}
```

**Response 200:** Misma estructura que la respuesta de registro.

**Errores:**

| Codigo | Condicion |
|--------|-----------|
| 401 | Token no proporcionado, invalido, expirado, o de tipo incorrecto |
| 422 | Error de validacion (password < 8 chars, nombre vacio) |

---

#### POST /api/v1/auth/mfa/setup

Genera un secreto TOTP y la URI para configurar MFA en una aplicacion authenticator.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response 200:**
```json
{
  "secret": "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
  "qr_uri": "otpauth://totp/TravelHub:usuario@example.com?secret=...&issuer=TravelHub"
}
```

El campo `qr_uri` puede utilizarse para generar un codigo QR escaneable por aplicaciones como Google Authenticator o Authy. El secreto tiene una longitud de 32 caracteres en formato base32.

---

#### POST /api/v1/auth/mfa/verify

Verifica un codigo TOTP y activa MFA para el usuario. Requiere haber ejecutado previamente `/mfa/setup`.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "totp_code": "123456"
}
```

**Response 200:**
```json
{
  "message": "MFA activado exitosamente"
}
```

**Errores:**

| Codigo | Condicion |
|--------|-----------|
| 400 | MFA no configurado (setup no ejecutado previamente) |
| 401 | Codigo TOTP invalido |

La verificacion acepta una ventana de validez de +/- 30 segundos (`valid_window=1`).

---

### Infraestructura

#### GET /health

Health check del servicio.

**Response 200:**
```json
{
  "status": "healthy",
  "service": "user-services",
  "version": "1.0.0"
}
```

---

## Autenticacion y Autorizacion

### Tokens JWT

El servicio emite dos tipos de tokens firmados con **RS256** (RSA 2048 bits):

| Tipo          | Expiracion        | Payload                                                                               |
|---------------|-------------------|---------------------------------------------------------------------------------------|
| Access Token  | 15 minutos (900s) | `{ sub, role, mfa_verified, country, hotel_id, iss, aud, type: "access", exp, iat }`  |
| Refresh Token | 7 dias (604800s)  | `{ sub, role, mfa_verified, country, hotel_id, iss, aud, type: "refresh", exp, iat }` |

- **Issuer (`iss`):** `https://auth.travelhub.app`
- **Audience (`aud`):** `travelhub-api`
- **Key ID (`kid`):** `travelhub-key-1` (incluido en el header JWT)

Las claves RSA se generan en memoria al arrancar el servicio. La clave publica se expone en formato JWKS en `GET /.well-known/jwks.json` para que el API Gateway valide los tokens.

El servicio valida estrictamente el tipo de token: un refresh token no es aceptado donde se espera un access token, y viceversa.

### JWKS Endpoint

`GET /.well-known/jwks.json` retorna la clave publica en formato JWK:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "travelhub-key-1",
      "use": "sig",
      "alg": "RS256",
      "n": "<modulus-base64url>",
      "e": "<exponent-base64url>"
    }
  ]
}
```

### RBAC (Control de Acceso Basado en Roles)

Los roles en BD se mapean a roles del gateway al generar el JWT:

| Rol en BD           | Rol en JWT       | Descripcion                              |
|---------------------|------------------|------------------------------------------|
| `viajero`           | `traveler`       | Rol por defecto asignado en el registro  |
| `admin_hotel`       | `hotel_admin`    | Administrador de una propiedad hotelera  |
| `admin_plataforma`  | `platform_admin` | Administrador de la plataforma           |

Permisos por rol:

| Rol              | Acceso                                           |
|------------------|--------------------------------------------------|
| `traveler`       | search, bookings, payments, cart, notifications  |
| `hotel_admin`    | search, bookings, inventory, pms, notifications  |
| `platform_admin` | todo, incluyendo /admin                          |

El `RBACFilter` en la cadena de autenticacion verifica que el rol del usuario (contenido en el JWT) este dentro de la lista de roles permitidos para el endpoint solicitado. El `MFAFilter` requiere `mfa_verified=true` para rutas `/payments` y `/admin`.

### MFA (Autenticacion Multifactor)

El flujo de activacion de MFA consta de dos pasos:

1. **Setup** (`POST /mfa/setup`): Genera un secreto TOTP de 32 caracteres (base32) y una URI compatible con el estandar `otpauth://`. El usuario registra este secreto en su aplicacion authenticator.
2. **Verify** (`POST /mfa/verify`): El usuario proporciona un codigo de 6 digitos generado por su aplicacion. Si el codigo es valido, el campo `mfa_activo` del usuario se establece en `true`.

Una vez activado, todos los intentos de login requieren el campo `totp_code` adicional.

---

## Base de Datos y Migraciones

### Modelo de Datos

Tabla `users`:

| Columna | Tipo | Restricciones | Descripcion |
|---------|------|---------------|-------------|
| `id` | UUID | PK, auto-generado | Identificador unico |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL | Correo electronico |
| `username` | VARCHAR(100) | UNIQUE, NOT NULL | Nombre de usuario |
| `nombre` | VARCHAR(255) | NOT NULL | Nombre completo |
| `hashed_password` | VARCHAR(255) | NOT NULL | Hash bcrypt de la contrasena |
| `telefono` | VARCHAR(50) | nullable | Telefono de contacto |
| `pais` | VARCHAR(100) | nullable | Pais (ISO 3166 recomendado) |
| `idioma` | VARCHAR(10) | NOT NULL, default 'es' | Idioma preferido |
| `moneda_preferida` | VARCHAR(10) | NOT NULL, default 'USD' | Moneda preferida |
| `mfa_activo` | BOOLEAN | NOT NULL, default FALSE | Estado de MFA |
| `mfa_secret` | VARCHAR(255) | nullable | Secreto TOTP (base32) |
| `failed_login_attempts` | INTEGER | NOT NULL, default 0 | Contador de intentos fallidos |
| `locked_until` | TIMESTAMPTZ | nullable | Fecha limite de bloqueo |
| `rol` | VARCHAR(50) | NOT NULL, default 'viajero' | Rol RBAC |
| `hotel_id` | UUID | nullable | ID de hotel (solo para hotel_admin) |
| `activo` | BOOLEAN | NOT NULL, default TRUE | Soft delete |
| `fecha_registro` | TIMESTAMPTZ | NOT NULL, auto | Fecha de creacion |
| `fecha_actualizacion` | TIMESTAMPTZ | NOT NULL, auto | Fecha de ultima actualizacion |

Indices: `email`, `username`, `rol`, `pais`.

### Comandos de Migracion

```bash
# Generar una nueva migracion a partir de cambios en los modelos
alembic revision --autogenerate -m "descripcion del cambio"

# Aplicar todas las migraciones pendientes
alembic upgrade head

# Revertir la ultima migracion
alembic downgrade -1

# Ver el estado actual de migraciones
alembic current
```

> **Nota:** Alembic utiliza `DATABASE_URL_SYNC` con el driver `psycopg2`. Los endpoints del servicio utilizan `DATABASE_URL` con `asyncpg`. No mezclar los drivers.

---

## Pruebas

### Ejecucion de Tests

```bash
# Ejecutar todas las pruebas
pytest

# Ejecutar con salida detallada
pytest -v

# Ejecutar un archivo especifico
pytest tests/test_login.py -v

# Ejecutar tests por nombre
pytest -k "test_login" -v

# Ejecutar con reporte de cobertura
pytest --cov=app --cov-report=term-missing
```

### Estructura de Tests

| Archivo | Funcionalidad | Cantidad |
|---------|---------------|----------|
| `test_register.py` | Registro de usuarios (W07) | 10 |
| `test_login.py` | Login con JWT y MFA (W08) | 12 |
| `test_refresh.py` | Renovacion de tokens | 4 |
| `test_auth_chain.py` | Chain of Responsibility (AH008) | 6 |
| `test_mfa.py` | Flujo completo de MFA | 6 |
| `test_health.py` | Health check | 1 |
| **Total** | | **39** |

### Cobertura

La cobertura minima requerida es del 80% en los modulos criticos (`auth_service.py`, `auth_chain.py`). La cobertura actual del proyecto es:

| Modulo | Cobertura |
|--------|-----------|
| `auth_service.py` | 96% |
| `auth_chain.py` | 90% |
| `routers/auth.py` | 100% |
| `jwt_handler.py` | 100% |
| `security.py` | 100% |
| **Total** | **96%** |

### Convenciones de Nomenclatura

Los tests siguen el patron: `test_<accion>_<escenario>_<resultado_esperado>`

Ejemplos:
- `test_register_duplicate_email_returns_409`
- `test_login_locked_account_returns_423`
- `test_chain_valid_token_wrong_role_returns_403`

---

## Despliegue

### Build de Imagen Docker

```bash
# Imagen de desarrollo (con hot reload)
docker build --target development -t user-services:dev .

# Imagen de produccion (con 4 workers)
docker build --target production -t gcr.io/<PROJECT_ID>/user-services:latest .
```

### Despliegue en GCP Cloud Run

```bash
# Push a Container Registry
docker push gcr.io/<PROJECT_ID>/user-services:latest

# Deploy
gcloud run deploy user-services \
  --image gcr.io/<PROJECT_ID>/user-services:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --vpc-connector=travelhub-connector \
  --set-env-vars "DATABASE_URL=<PROD_DB_URL>,JWT_ISSUER=https://auth.travelhub.app,JWT_AUDIENCE=travelhub-api,ENVIRONMENT=production" \
  --min-instances 1 \
  --max-instances 10 \
  --memory 512Mi \
  --cpu 1 \
  --port 8000
```

---

## Coleccion Postman

El directorio `postman/` contiene la coleccion y el environment para probar la API con Postman:

- `user-services.postman_collection.json` -- Coleccion con 16 requests organizados en carpetas
- `user-services.postman_environment.json` -- Variables de entorno para ejecucion local

### Importacion

1. Abrir Postman.
2. Seleccionar Import y arrastrar ambos archivos JSON.
3. Seleccionar el environment "User Services - Local" en el selector de entornos.

### Flujo de Prueba Recomendado

1. Health Check
2. Register (crea un usuario)
3. Login (guarda tokens automaticamente en el environment)
4. Get Me (usa el access token guardado)
5. MFA Setup (genera secreto TOTP)
6. MFA Verify (activa MFA con codigo TOTP)
7. Login con MFA (requiere `totp_code`)
8. Refresh Token (renueva tokens)

Los requests de Login, Login con MFA y Refresh guardan automaticamente los tokens en las variables del environment mediante scripts de post-ejecucion.

---

## Codigos HTTP de Referencia

| Codigo | Significado | Uso en el Servicio |
|--------|-------------|--------------------|
| 200 | OK | Operacion exitosa (login, refresh, me, mfa) |
| 201 | Created | Recurso creado (registro) |
| 400 | Bad Request | MFA no configurado, datos invalidos |
| 401 | Unauthorized | Credenciales invalidas, token invalido o expirado |
| 403 | Forbidden | Rol insuficiente (RBAC) |
| 409 | Conflict | Email o username duplicado |
| 422 | Unprocessable Entity | Error de validacion de Pydantic |
| 423 | Locked | Cuenta bloqueada por intentos fallidos |
| 428 | Precondition Required | Codigo MFA requerido |

---

## Contexto del Proyecto

- **Plataforma:** TravelHub -- plataforma de reservas hoteleras para Latinoamerica (~1,200 propiedades, ~450,000 viajeros)
- **Institucion:** Universidad de los Andes -- Maestria en Ingenieria de Software (MISW4501/4502)
- **Fase:** Proyecto Final 2, Sprint 1
- **Arquitectura:** Microservicios. Este servicio es el componente de identidad y autenticacion del ecosistema.
