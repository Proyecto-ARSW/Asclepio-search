from pydantic_settings import BaseSettings
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    jwt_secret: str
    database_url: str
    rabbitmq_url: str
    port: int = 3006
    similarity_threshold: float = 0.55
    allowed_roles: list[str] = ["MEDICO", "ENFERMERO", "ADMIN"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


try:
    settings = Settings()
    logger.info(f"Settings loaded successfully. Port: {settings.port}")
except Exception as e:
    logger.error(f"Failed to load settings: {e}")
    raise
# Daniel Useche
