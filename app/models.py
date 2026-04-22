from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import declarative_base
import uuid

Base = declarative_base()


class ClinicalEmbedding(Base):
    __tablename__ = "clinical_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), nullable=False)
    record_id = Column(UUID(as_uuid=True), nullable=False, unique=True)
    hospital_id = Column(Integer, nullable=False, index=True)
    notes_snapshot = Column(Text, nullable=False)
    embedding = Column(Vector(384), nullable=False)
    source_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class FailedEvent(Base):
    __tablename__ = "failed_events"

    id = Column(Integer, primary_key=True)
    routing_key = Column(String(100))
    payload = Column(JSON)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
# Daniel Useche
