#!/usr/bin/env python3
"""
Script to initialize the search database schema.
Reads migrations from migrations/ directory and applies them.
"""

import asyncio
import asyncpg
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def init_database():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable not set")

    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    logger.info(f"Connecting to database...")
    conn = await asyncpg.connect(db_url)

    try:
        migrations_dir = Path(__file__).parent.parent / "migrations"
        migration_files = sorted(migrations_dir.glob("*.sql"))

        for migration_file in migration_files:
            logger.info(f"Running migration: {migration_file.name}")
            with open(migration_file, "r") as f:
                sql = f.read()
                await conn.execute(sql)
            logger.info(f"✓ Completed: {migration_file.name}")

        logger.info("Database initialization completed successfully")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(init_database())
