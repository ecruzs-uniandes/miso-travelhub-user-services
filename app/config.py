from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = (
        "postgresql+asyncpg://travelhub:travelhub_dev@localhost:5432/travelhub_users"
    )
    DATABASE_URL_SYNC: str = (
        "postgresql+psycopg2://travelhub:travelhub_dev@localhost:5432/travelhub_users"
    )
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "RS256"
    JWT_ISSUER: str = "https://auth.travelhub.app"
    JWT_AUDIENCE: str = "travelhub-api"
    JWT_ACCESS_TTL: int = 86400
    JWT_REFRESH_TTL: int = 604800
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    BCRYPT_ROUNDS: int = 12
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_MINUTES: int = 15
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Kafka producer — publica eventos de usuario (user.welcome, etc.)
    # hacia notification-services via topic user-events. En DEV: 10.10.3.3:9092
    # En PROD: 10.20.3.3:9092. Local/tests: false (no produce, log warning).
    KAFKA_ENABLED: bool = False
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_USER_EVENTS_TOPIC: str = "user-events"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
