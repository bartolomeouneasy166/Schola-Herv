# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt pyproject.toml setup.py README.md ./
COPY schola_herv/ ./schola_herv/

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir -e .

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="Yahia Shawon" \
      description="Schola-herv: Mass-scale academic paper harvester" \
      version="2.0.0"

WORKDIR /app

# Copy installed packages and binary from builder
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin/schola-herv /usr/local/bin/schola-herv

# Copy project files
COPY schola_herv/ ./schola_herv/
COPY webapp/ ./webapp/
COPY config.yaml ./
COPY data/ ./data/

# Output volume — mount your host directory here
VOLUME ["/app/corpus_output"]

# Default: show help
ENTRYPOINT ["schola-herv"]
CMD ["--help"]
