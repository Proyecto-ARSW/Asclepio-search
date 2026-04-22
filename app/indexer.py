from sentence_transformers import SentenceTransformer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.models import ClinicalEmbedding
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None


def load_model() -> None:
    global _model
    if _model is None:
        logger.info("Loading SentenceTransformer model...")
        _model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        logger.info("Model loaded successfully")


def encode(text: str) -> list:
    if _model is None:
        load_model()
    if not text:
        return [0.0] * 384
    embedding = _model.encode(text)
    return embedding.tolist()


async def upsert(
    session: AsyncSession,
    record_id: str,
    patient_id: str,
    hospital_id: int,
    notes: str,
    version: int,
) -> None:
    try:
        embedding = encode(notes)

        stmt = pg_insert(ClinicalEmbedding).values(
            record_id=record_id,
            patient_id=patient_id,
            hospital_id=hospital_id,
            notes_snapshot=notes,
            embedding=embedding,
            source_version=version,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["record_id"],
            set_={
                "notes_snapshot": notes,
                "embedding": embedding,
                "source_version": version,
                "updated_at": datetime.utcnow(),
            },
        )

        await session.execute(stmt)
        await session.commit()
        logger.info(f"Upserted embedding for record {record_id}")
    except Exception as e:
        logger.error(f"Error upserting record {record_id}: {e}", exc_info=True)
        raise


async def delete_by_record(session: AsyncSession, record_id: str) -> None:
    try:
        stmt = delete(ClinicalEmbedding).where(
            ClinicalEmbedding.record_id == record_id
        )
        await session.execute(stmt)
        await session.commit()
        logger.info(f"Deleted record {record_id}")
    except Exception as e:
        logger.error(f"Error deleting record {record_id}: {e}", exc_info=True)
        raise


async def delete_by_patient(session: AsyncSession, patient_id: str) -> None:
    try:
        stmt = delete(ClinicalEmbedding).where(
            ClinicalEmbedding.patient_id == patient_id
        )
        result = await session.execute(stmt)
        await session.commit()
        logger.info(f"Deleted {result.rowcount} records for patient {patient_id}")
    except Exception as e:
        logger.error(f"Error deleting patient {patient_id}: {e}", exc_info=True)
        raise
# Daniel Useche
