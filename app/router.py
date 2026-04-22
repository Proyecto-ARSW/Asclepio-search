from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.auth import verify_token
from app.database import get_session
from app.schemas import SearchResponse, SearchResult, HealthResponse
from app.indexer import encode
from app.config import settings
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health_check(session: AsyncSession = Depends(get_session)):
    try:
        await session.execute(select(1))
        return HealthResponse(
            status="healthy",
            database="connected",
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            database="disconnected",
            message=str(e),
        )


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=3, max_length=500),
    limit: int = Query(10, ge=1, le=100),
    threshold: float = Query(settings.similarity_threshold, ge=0, le=1),
    user: dict = Depends(verify_token),
    session: AsyncSession = Depends(get_session),
):
    hospital_id = user.get("hospitalId")
    query_embedding = encode(q)

    # asyncpg no tiene codec para el tipo vector — inferiría el parámetro como
    # TEXT y fallaría con una lista Python. Serializar al formato literal de
    # pgvector "[v1,v2,...,vn]" permite que PostgreSQL haga el CAST correctamente.
    embedding_literal = "[" + ",".join(str(v) for v in query_embedding) + "]"

    stmt = text("""
        SELECT
            id,
            record_id,
            patient_id,
            notes_snapshot,
            updated_at,
            1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM clinical_embeddings
        WHERE hospital_id = :hospital_id
          AND 1 - (embedding <=> CAST(:embedding AS vector)) > :threshold
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)

    result = await session.execute(
        stmt,
        {
            "embedding": embedding_literal,
            "hospital_id": hospital_id,
            "threshold": threshold,
            "limit": limit,
        },
    )

    rows = result.fetchall()

    return SearchResponse(
        results=[
            SearchResult(
                record_id=row[1],
                patient_id=row[2],
                similarity=float(row[5]),
                notes_snippet=row[3][:200] + ("..." if len(row[3]) > 200 else ""),
                updated_at=row[4],
            )
            for row in rows
        ],
        total=len(rows),
        query=q,
    )

# Daniel Useche
