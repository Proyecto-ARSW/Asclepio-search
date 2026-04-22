from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.auth import verify_token
from app.database import get_session
from app.schemas import SearchResponse, SearchResult, HealthResponse
from app.indexer import encode
from app.config import settings
import logging
import re

router = APIRouter()
logger = logging.getLogger(__name__)

HYBRID_VECTOR_WEIGHT = 0.75
HYBRID_LEXICAL_WEIGHT = 0.25


def tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9áéíóúñ]+", text.lower())
    return {token for token in tokens if len(token) >= 3}


def lexical_overlap_score(query: str, document: str) -> float:
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0

    document_tokens = tokenize(document)
    if not document_tokens:
        return 0.0

    matches = query_tokens.intersection(document_tokens)
    return len(matches) / len(query_tokens)


def hybrid_score(vector_similarity: float, lexical_score: float) -> float:
    return (
        (HYBRID_VECTOR_WEIGHT * vector_similarity)
        + (HYBRID_LEXICAL_WEIGHT * lexical_score)
    )


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
    query_embedding = encode(q, mode="query")

    # asyncpg no tiene codec para el tipo vector — inferiría el parámetro como
    # TEXT y fallaría con una lista Python. Serializar al formato literal de
    # pgvector "[v1,v2,...,vn]" permite que PostgreSQL haga el CAST correctamente.
    embedding_literal = "[" + ",".join(str(v) for v in query_embedding) + "]"

    candidate_limit = min(max(limit * 5, 25), 50)

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
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :candidate_limit
    """)

    result = await session.execute(
        stmt,
        {
            "embedding": embedding_literal,
            "hospital_id": hospital_id,
            "candidate_limit": candidate_limit,
        },
    )

    rows = result.fetchall()

    ranked_rows = []
    for row in rows:
        vector_similarity = float(row[5])
        lexical_score = lexical_overlap_score(q, row[3] or "")
        combined_similarity = hybrid_score(vector_similarity, lexical_score)

        if combined_similarity >= threshold:
            ranked_rows.append(
                (
                    combined_similarity,
                    vector_similarity,
                    lexical_score,
                    row,
                )
            )

    ranked_rows.sort(key=lambda item: item[0], reverse=True)
    ranked_rows = ranked_rows[:limit]

    return SearchResponse(
        results=[
            SearchResult(
                record_id=row[1],
                patient_id=row[2],
                similarity=float(combined_similarity),
                notes_snippet=row[3][:200] + ("..." if len(row[3]) > 200 else ""),
                updated_at=row[4],
            )
            for combined_similarity, _, _, row in ranked_rows
        ],
        total=len(ranked_rows),
        query=q,
    )

# Daniel Useche
