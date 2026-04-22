from pydantic_settings import BaseSettings
from pydantic import field_validator
import logging
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)


def redact_secret_url(url: str) -> str:
    """Redact password from URLs before writing them to logs."""
    try:
        parsed = urlsplit(url)

        if parsed.password is None:
            return url

        user = parsed.username or ""
        host = parsed.hostname or ""

        if parsed.port:
            host = f"{host}:{parsed.port}"

        userinfo = user
        if userinfo:
            userinfo = f"{userinfo}:***"

        netloc = f"{userinfo}@{host}" if userinfo else host
        return urlunsplit(
            (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
        )
    except Exception:
        return "<invalid_url>"


class Settings(BaseSettings):
    jwt_secret: str
    database_url: str
    rabbitmq_url: str
    port: int = 3006
    embedding_model_name: str = "intfloat/multilingual-e5-small"
    similarity_threshold: float = 0.42
    embedding_chunk_size: int = 800
    embedding_chunk_overlap: int = 120
    allowed_roles: list[str] = ["MEDICO", "ENFERMERO", "ADMIN"]

    @field_validator("database_url", mode="before")
    @classmethod
    def ensure_asyncpg_scheme(cls, v: str) -> str:
        if not isinstance(v, str):
            return v

        if v.startswith("postgresql+asyncpg://"):
            return v

        if v.startswith("postgresql://"):
            normalized = v.replace("postgresql://", "postgresql+asyncpg://", 1)
            logger.warning(
                "DATABASE_URL used sync scheme; auto-normalized to asyncpg: %s",
                redact_secret_url(normalized),
            )
            return normalized

        if v.startswith("postgres://"):
            normalized = v.replace("postgres://", "postgresql+asyncpg://", 1)
            logger.warning(
                "DATABASE_URL used legacy postgres scheme; auto-normalized to asyncpg: %s",
                redact_secret_url(normalized),
            )
            return normalized

        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


try:
    settings = Settings()
    logger.info(f"Settings loaded successfully. Port: {settings.port}")
except Exception as e:
    logger.error(f"Failed to load settings: {e}", exc_info=True)
    raise
# Daniel Useche
