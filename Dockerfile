# Stage 1: Builder
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /tmp

COPY requirements.txt .

# Install to user site-packages to reduce size
RUN pip install --user --no-cache-dir -r requirements.txt && \
    pip install --user tqdm && \
    python -m pip list | grep tqdm && \
    find /root/.local -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true

# Stage 2: Runtime (ultra-slim)
FROM python:3.11-slim

# Install only runtime dependencies (libpq-client, NOT libpq-dev)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app

# Copy only pip packages from builder
COPY --from=builder /root/.local /root/.local

# Set PATH to use user-installed packages
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/root/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/root/.cache/sentence_transformers

COPY . .

# Clean up unnecessary files
RUN find /root/.local -type f -name "*.pyc" -delete && \
    find /root/.local -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find /root/.local -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true && \
    rm -rf /root/.local/lib/python*/site-packages/pip* && \
    rm -rf /root/.local/lib/python*/site-packages/setuptools* && \
    rm -rf /root/.local/lib/python*/site-packages/wheel*

EXPOSE 3006

# Increased start period to allow model download on first start
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:3006/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3006"]
# Daniel Useche
