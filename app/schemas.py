from pydantic import BaseModel
from datetime import datetime
from uuid import UUID


class SearchResult(BaseModel):
    record_id: UUID
    patient_id: UUID
    similarity: float
    notes_snippet: str
    updated_at: datetime

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    query: str


class HealthResponse(BaseModel):
    status: str
    database: str
    message: str = ""
# Daniel Useche
