CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS clinical_embeddings (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id  UUID NOT NULL,
    record_id   UUID NOT NULL UNIQUE,
    hospital_id INTEGER NOT NULL,
    notes_snapshot TEXT NOT NULL,
    embedding   VECTOR(384) NOT NULL,
    source_version INTEGER NOT NULL DEFAULT 1,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_embeddings_hnsw
    ON clinical_embeddings USING HNSW (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_embeddings_hospital
    ON clinical_embeddings (hospital_id);

CREATE TABLE IF NOT EXISTS failed_events (
    id          SERIAL PRIMARY KEY,
    routing_key VARCHAR(100),
    payload     JSONB,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
-- Daniel Useche
