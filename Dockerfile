# Stage 1: Build
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY README.md .
COPY src/ src/

RUN pip install --no-cache-dir build && \
    python -m build --wheel && \
    pip install --no-cache-dir --prefix=/install dist/*.whl

# Stage 2: Runtime
FROM python:3.12-slim

# Install postgresql-client for schema init and curl for healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client curl && \
    rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd --create-home --shell /bin/bash silkroute
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy runtime files
COPY sql/init.sql /app/sql/init.sql
COPY litellm_config.yaml /app/litellm_config.yaml
COPY scripts/start.sh /app/scripts/start.sh
RUN chmod +x /app/scripts/start.sh

# Switch to non-root user
USER silkroute

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8787}/health || exit 1

CMD ["/app/scripts/start.sh"]
