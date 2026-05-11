# asclepio-search — Diagramas de Arquitectura

## 1. Arquitectura de Componentes

```mermaid
graph TB
    subgraph Clients["Clientes externos"]
        UI["UI / Frontend"]
        Core["asclepio-core\nNestJS M1"]
    end

    subgraph Search["asclepio-search · FastAPI · Puerto 3006"]
        Router["Router\n/search · /health"]
        Auth["JWT Auth\nHS256 · Bearer\nhospitalId + rol"]
        Hybrid["Hybrid Scorer\n75% vector + 25% lexical\nthreshold 0.42"]
        Indexer["Embedding Engine\nintfloat/multilingual-e5-small\n384 dim · lazy-loaded"]
        Consumer["RabbitMQ Consumer\nasync task · QoS prefetch=10"]
    end

    subgraph Storage["Almacenamiento"]
        PG[("PostgreSQL + pgvector\nclinical_embeddings\nHNSW index cosine\nfailed_events DLQ")]
    end

    subgraph MQ["Mensajería"]
        RMQ["RabbitMQ\nExchange: clinical.events TOPIC\nQueue: search.index.queue"]
    end

    subgraph ML["ML"]
        HF["HuggingFace Hub\nintfloat/multilingual-e5-small"]
    end

    UI -->|"GET /search · Bearer JWT"| Router
    Core -->|"GET /search · Bearer JWT"| Router
    Core -->|"AMQP record.created / record.updated"| RMQ

    Router --> Auth
    Auth -->|hospitalId| Hybrid
    Hybrid --> Indexer
    Indexer -->|"cosine · HNSW"| PG
    Hybrid -->|"token overlap"| PG

    RMQ --> Consumer
    Consumer --> Indexer
    Indexer -->|"upsert / delete"| PG
    Consumer -->|"error → DLQ"| PG

    Indexer -.->|"lazy load"| HF
```

---

## 2. Flujo de Búsqueda (Sequence)

```mermaid
sequenceDiagram
    actor Client
    participant API as FastAPI /search
    participant Auth as JWT Auth
    participant Enc as Embedding Engine
    participant DB as PostgreSQL + pgvector
    participant Score as Hybrid Scorer

    Client->>API: GET /search?q=dolor pecho&limit=10
    Note over Client,API: Authorization: Bearer JWT

    API->>Auth: verify_token(credentials)
    Auth->>Auth: jwt.decode HS256
    alt token inválido
        Auth-->>Client: 401 Token inválido
    else hospitalId ausente
        Auth-->>Client: 403 Token de pre-autenticación
    else rol no permitido
        Auth-->>Client: 403 Rol no autorizado
    end
    Auth-->>API: payload {hospitalId, rol}

    API->>Enc: encode(q, mode="query")
    Enc->>Enc: normalize · prefijo "query:"
    Enc-->>API: vector[384]

    API->>DB: SELECT top-50 por distancia coseno
    Note over DB: WHERE hospital_id = :hospitalId
    Note over DB: ORDER BY embedding <=> cast(:emb as vector)
    DB-->>API: rows {record_id, patient_id, similarity, notes_snapshot}

    loop cada candidato
        API->>Score: hybrid_score(vector_sim, lexical_overlap)
        Note over Score: 0.75 × vector + 0.25 × lexical
        Score-->>API: combined_score
    end

    API->>API: filtrar threshold 0.42
    API->>API: sort desc · slice [:limit]

    API-->>Client: SearchResponse {results[], total, query}
```

---

## 3. Flujo de Indexación (Sequence)

```mermaid
sequenceDiagram
    actor Core as asclepio-core NestJS
    participant RMQ as RabbitMQ
    participant Cons as Consumer async
    participant Enc as Embedding Engine
    participant DB as PostgreSQL

    Core->>RMQ: publish routing_key=record.created
    Note over Core,RMQ: {recordId, patientId, hospitalId, notes, version}

    Note over RMQ: Exchange clinical.events TOPIC durable
    Note over RMQ: Queue search.index.queue durable · prefetch=10

    RMQ->>Cons: deliver message

    alt record.created o record.updated
        Cons->>Enc: encode(notes, mode="passage")
        Enc->>Enc: normalize_text lowercase + whitespace
        Enc->>Enc: chunk_text size=800 overlap=120
        loop por cada chunk
            Enc->>Enc: prefijo "passage:" + encode
        end
        Enc->>Enc: pool_embeddings mean
        Enc-->>Cons: vector[384]

        Cons->>DB: INSERT ON CONFLICT record_id DO UPDATE
        Note over DB: embedding, notes_snapshot, source_version, updated_at
        DB-->>Cons: OK
        Cons->>RMQ: ack

    else record.deleted
        Cons->>DB: DELETE WHERE record_id = :id
        DB-->>Cons: OK
        Cons->>RMQ: ack

    else patient.deleted
        Cons->>DB: DELETE WHERE patient_id = :id
        DB-->>Cons: N rows deleted
        Cons->>RMQ: ack

    else Error
        Cons->>DB: INSERT failed_events {routing_key, payload, error}
        Cons->>RMQ: ack
        Note over RMQ,Cons: ack evita redelivery infinito · DLQ manual
    end
```

---

## 4. Modelo de Datos (ER)

```mermaid
erDiagram
    CLINICAL_EMBEDDINGS {
        UUID id PK
        UUID record_id UK "índice único"
        UUID patient_id "sin FK deliberado"
        INTEGER hospital_id "índice B-tree · multi-tenancy"
        TEXT notes_snapshot "texto clínico indexado"
        VECTOR_384 embedding "índice HNSW coseno"
        INTEGER source_version
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    FAILED_EVENTS {
        SERIAL id PK
        VARCHAR routing_key "record.* / patient.*"
        JSONB payload "mensaje original"
        TEXT error_message
        INTEGER retry_count
        TIMESTAMPTZ created_at
    }
```

---

## 5. Arquitectura de Despliegue

```mermaid
graph LR
    subgraph GH["GitHub Actions CI/CD"]
        direction TB
        Checkout["checkout code"]
        BuildVenv["setup Python 3.11\ninstall requirements"]
        AzDeploy["azure/webapps-deploy\nProduction slot"]
        Checkout --> BuildVenv --> AzDeploy
    end

    subgraph DockerBuild["Docker multi-stage"]
        direction TB
        Builder["Stage 1: builder\npython:3.11-slim\nlibpq-dev · gcc\npip install --user"]
        Runtime["Stage 2: runtime\npython:3.11-slim\nlibpq5 · curl\ncopy /root/.local"]
        Builder -->|"COPY --from=builder"| Runtime
    end

    subgraph Azure["Azure App Service"]
        WebApp["asclepio-search\nPort 3006\nuvicorn ASGI"]
        HC["Healthcheck\nGET /health 30s\nstart-period 120s"]
    end

    subgraph Deps["Servicios externos"]
        HF["HuggingFace Hub\nmultilingual-e5-small\ncache /root/.cache"]
        PGDB["PostgreSQL 13+\npgvector extension\nHNSW vector index"]
        RMQBroker["RabbitMQ AMQP\nclinical.events\nsearch.index.queue"]
    end

    AzDeploy --> Azure
    Runtime --> Azure
    WebApp -.->|"lazy download\nprimer uso"| HF
    WebApp -->|"asyncpg pool=10"| PGDB
    WebApp -->|"aio-pika robust"| RMQBroker
    HC --> WebApp
```

<!-- Daniel Useche -->
