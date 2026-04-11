import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.database import Base, engine
from app.routers import auth
from app.utils.rsa_keys import get_jwks

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import app.models.user  # noqa: F401 — registra el modelo en Base.metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tablas verificadas/creadas al arrancar")
    yield


app = FastAPI(
    title="TravelHub User Services",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])


@app.exception_handler(OperationalError)
async def handle_db_connection_error(request: Request, exc: OperationalError):
    logger.error("Error de conexion a la base de datos: %s", str(exc.orig))
    return JSONResponse(
        status_code=503,
        content={"detail": "Servicio de base de datos no disponible"},
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    logger.error(
        "Error inesperado en %s %s: %s", request.method, request.url.path, str(exc)
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor"},
    )


@app.get("/.well-known/jwks.json")
async def jwks():
    return get_jwks()


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "user-services", "version": "1.0.0"}
