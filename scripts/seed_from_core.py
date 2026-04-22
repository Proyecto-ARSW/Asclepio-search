"""
Script de migración única para indexar todos los historiales existentes en asclepio-core.
Lee todos los registros de historial_medico de la BD de core y publica eventos
record.created para que el consumer de asclepio-search los indexe.

Uso:
    python scripts/seed_from_core.py \
        --core-db postgresql://user:pass@localhost:5432/asclepio_core \
        --rabbitmq amqp://guest:guest@localhost:5672
"""

import asyncio
import json
import argparse
import asyncpg
import aio_pika
import logging
from uuid import UUID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_from_core(core_db_url: str, rabbitmq_url: str):
    conn = await asyncpg.connect(core_db_url)

    rabbitmq_conn = await aio_pika.connect_robust(rabbitmq_url)
    channel = await rabbitmq_conn.channel()
    exchange = await channel.declare_exchange(
        "clinical.events",
        aio_pika.ExchangeType.TOPIC,
        durable=True,
    )

    query = """
        SELECT h.id, h.paciente_id, h.medico_id, h.diagnostico, h.tratamiento,
               h.observaciones, d.usuario_id as doctor_id
        FROM historial_medico h
        LEFT JOIN medicos m ON h.medico_id = m.id
        LEFT JOIN usuarios u ON m.usuario_id = u.id
    """

    rows = await conn.fetch(query)
    logger.info(f"Found {len(rows)} historial records to index")

    for row in rows:
        notes = [row["diagnostico"], row["tratamiento"], row["observaciones"]]
        notes_text = " | ".join([n for n in notes if n])

        payload = {
            "recordId": str(row["id"]),
            "patientId": str(row["paciente_id"]),
            "hospitalId": 1,
            "notes": notes_text or "",
            "version": 1,
        }

        msg = aio_pika.Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )

        await exchange.publish(msg, routing_key="record.created")
        logger.info(f"Published record {row['id']}")

    await conn.close()
    await channel.close()
    await rabbitmq_conn.close()
    logger.info("Migration complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-db", required=True)
    parser.add_argument("--rabbitmq", required=True)
    args = parser.parse_args()

    asyncio.run(migrate_from_core(args.core_db, args.rabbitmq))
# Daniel Useche
