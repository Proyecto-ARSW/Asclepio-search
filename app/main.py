from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import asyncio
import logging
import sys

from app.config import settings
from app.router import router
from app.database import engine
from app.models import Base
from app.consumer import start_consumer
from app.indexer import load_model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

consumer_task: asyncio.Task | None = None


async def init_db():
    try:
        async with engine.begin() as conn:
            # pgvector ships the binary in the image, pero la extension debe
            # crearse por-base-de-datos antes de declarar columnas VECTOR(n).
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Starting asclepio-search ===")
    logger.info(f"Port: {settings.port}")
    logger.info(f"Database URL: {settings.database_url[:50]}...")
    logger.info(f"RabbitMQ URL: {settings.rabbitmq_url[:50]}...")

    try:
        await init_db()
        load_model()
        logger.info("SentenceTransformer model loaded")

        global consumer_task
        consumer_task = asyncio.create_task(start_consumer())
        logger.info("RabbitMQ consumer started")
    except Exception as e:
        logger.error(f"Failed to start asclepio-search: {e}")
        raise

    yield

    logger.info("=== Shutting down asclepio-search ===")
    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            logger.info("Consumer task cancelled")

    await engine.dispose()
    logger.info("Database connection closed")


app = FastAPI(
    title="asclepio-search",
    description="Clinical Records Semantic Search Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    return {"message": "asclepio-search API", "version": "1.0.0"}
# Daniel Useche
