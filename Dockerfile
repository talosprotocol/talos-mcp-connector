# ========================================
# Builder Stage
# ========================================
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY sdks/python /build/sdks/python
COPY contracts/python /build/contracts/python
COPY libs/talos-config /build/libs/talos-config
COPY services/mcp-connector/requirements.txt .

RUN pip wheel --no-cache-dir --wheel-dir /wheels \
    -r requirements.txt \
    /build/sdks/python \
    /build/contracts/python \
    /build/libs/talos-config

# ========================================
# Runtime Stage
# ========================================
FROM python:3.11-slim

ARG GIT_SHA=unknown
ARG VERSION=unknown
ARG BUILD_TIME=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GIT_SHA=${GIT_SHA} \
    VERSION=${VERSION} \
    BUILD_TIME=${BUILD_TIME}

RUN groupadd --system --gid 1001 talos && \
    useradd --system --uid 1001 --gid talos --create-home talos

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

COPY --chown=1001:1001 services/mcp-connector/ .

# Legacy Layout Support: Copy schemas to where main.py expects them
COPY --chown=1001:1001 contracts/schemas /app/talos-contracts/schemas

# Writable mounts for read-only root filesystem
RUN mkdir -p /tmp /var/run && chown -R 1001:1001 /tmp /var/run

USER 1001:1001

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8082/health')" || exit 1

CMD ["uvicorn", "legacy.main:app", "--host", "0.0.0.0", "--port", "8082"]

LABEL org.opencontainers.image.source="https://github.com/talosprotocol/talos" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_TIME}" \
      org.opencontainers.image.licenses="Apache-2.0"
