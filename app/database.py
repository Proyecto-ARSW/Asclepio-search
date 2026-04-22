from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import logging
from app.config import settings, redact_secret_url

logger = logging.getLogger(__name__)

try:
    logger.info("Creating DB engine using %s", redact_secret_url(settings.database_url))
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    logger.info("Database engine created successfully")
except Exception as e:
    logger.error(
        "Failed to create database engine with %s: %s",
        redact_secret_url(settings.database_url),
        e,
        exc_info=True,
    )
    raise

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session
# Daniel Useche
