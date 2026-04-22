from sentence_transformers import SentenceTransformer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.models import ClinicalEmbedding
from datetime import datetime
from app.config import settings
import logging
import re

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None


def load_model() -> None:
    global _model
    if _model is None:
        logger.info("Loading SentenceTransformer model...")
        _model = SentenceTransformer(settings.embedding_model_name)
        logger.info("Model loaded successfully")


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def chunk_text(text: str) -> list[str]:
    """Split long text into overlapping chunks to preserve local clinical signals."""
    cleaned = normalize_text(text)
    if not cleaned:
        return []

    chunk_size = max(settings.embedding_chunk_size, 100)
    overlap = max(min(settings.embedding_chunk_overlap, chunk_size - 1), 0)
    step = max(chunk_size - overlap, 1)

    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    start = 0

    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        chunk = cleaned[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(cleaned):
            break

        start += step

    return chunks


def pool_embeddings(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return [0.0] * 384

    dimension = len(vectors[0])
    pooled = [0.0] * dimension

    for vector in vectors:
        for index, value in enumerate(vector[:dimension]):
            pooled[index] += float(value)

    count = float(len(vectors))
    return [value / count for value in pooled]


def encode(text: str, mode: str = "passage") -> list:
    if _model is None:
        load_model()
    if not text:
        return [0.0] * 384

    normalized = normalize_text(text)
    if mode == "query":
        query_text = f"query: {normalized}"
        embedding = _model.encode(query_text, normalize_embeddings=True)
        return embedding.tolist()

    chunks = chunk_text(normalized)
    if not chunks:
        return [0.0] * 384

    passages = [f"passage: {chunk}" for chunk in chunks]
    embeddings = _model.encode(passages, normalize_embeddings=True)

    if len(chunks) == 1:
        return embeddings[0].tolist()

    pooled = pool_embeddings([vector.tolist() for vector in embeddings])
    return pooled


async def upsert(
    session: AsyncSession,
    record_id: str,
    patient_id: str,
    hospital_id: int,
    notes: str,
    version: int,
) -> None:
    try:
        embedding = encode(notes, mode="passage")

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
