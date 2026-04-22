import json
import aio_pika
from app.config import settings
from app.database import AsyncSessionLocal
from app.indexer import upsert, delete_by_record, delete_by_patient
from app.models import FailedEvent
import logging

logger = logging.getLogger(__name__)

EXCHANGE = "clinical.events"
QUEUE = "search.index.queue"
ROUTING_KEYS = ["record.created", "record.updated"]


async def start_consumer() -> None:
    logger.info(f"Starting consumer, connecting to {settings.rabbitmq_url}")
    try:
        conn = await aio_pika.connect_robust(settings.rabbitmq_url)
        logger.info("Connected to RabbitMQ")

        channel = await conn.channel()
        await channel.set_qos(prefetch_count=10)
        logger.info("QoS set to prefetch_count=10")

        exchange = await channel.declare_exchange(
            EXCHANGE,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        logger.info(f"Exchange '{EXCHANGE}' declared")

        queue = await channel.declare_queue(QUEUE, durable=True)
        logger.info(f"Queue '{QUEUE}' declared")

        for routing_key in ROUTING_KEYS:
            await queue.bind(exchange, routing_key=routing_key)
            logger.info(f"Queue bound to routing key: {routing_key}")

        logger.info("Consumer ready, waiting for messages...")
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    await handle_message(message)

    except Exception as e:
        logger.error(f"Consumer error: {e}", exc_info=True)
        raise


async def handle_message(message: aio_pika.IncomingMessage) -> None:
    try:
        payload = json.loads(message.body.decode())
        routing_key = message.routing_key

        logger.info(f"Processing message: {routing_key}")

        async with AsyncSessionLocal() as session:
            if routing_key in ("record.created", "record.updated"):
                await upsert(
                    session,
                    record_id=payload["recordId"],
                    patient_id=payload["patientId"],
                    hospital_id=payload["hospitalId"],
                    notes=payload.get("notes", ""),
                    version=payload.get("version", 1),
                )
                logger.info(f"Indexed record {payload['recordId']}")

            elif routing_key == "record.deleted":
                await delete_by_record(session, payload["recordId"])
                logger.info(f"Deleted record {payload['recordId']}")

            elif routing_key == "patient.deleted":
                await delete_by_patient(session, payload["patientId"])
                logger.info(f"Deleted all records for patient {payload['patientId']}")

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        await save_failed_event(message.routing_key, message.body.decode(), str(e))


async def save_failed_event(
    routing_key: str,
    payload_str: str,
    error_message: str,
) -> None:
    try:
        async with AsyncSessionLocal() as session:
            failed = FailedEvent(
                routing_key=routing_key,
                payload=json.loads(payload_str),
                error_message=error_message,
                retry_count=0,
            )
            session.add(failed)
            await session.commit()
            logger.info(f"Saved failed event for {routing_key}")
    except Exception as e:
        logger.error(f"Failed to save failed event: {e}", exc_info=True)
# Daniel Useche
