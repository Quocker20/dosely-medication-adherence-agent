# ---- Stage 0: Build frontend ----
FROM node:20-slim AS web-builder

WORKDIR /web

COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build

# ---- Stage 1: Build (Python deps) ----
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 100 --retries 10 --upgrade pip && \
    pip install --no-cache-dir --timeout 100 --retries 10 --user -r requirements.txt

# ---- Stage 2: Production ----
FROM python:3.11-slim

WORKDIR /app

# Security: run as non-root user
RUN useradd -m appuser

# Copy installed packages from builder
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application code
COPY --chown=appuser:appuser . .

# Copy built frontend into web/dist — src/main.py mounts this if it exists
COPY --from=web-builder --chown=appuser:appuser /web/dist /app/web/dist

# Create data directory with correct ownership
RUN mkdir -p /app/data

USER appuser

EXPOSE 8000

# Uvicorn worker processes (O-20). Each loads the full app, so size this to the
# host RAM; override with UVICORN_WORKERS in the compose environment.
ENV UVICORN_WORKERS=2

# SEC-04: only trust X-Forwarded-For from the reverse proxy (Caddy) on the Docker
# network. Default is the whole private Docker range; narrow it to the compose
# network subnet (docker network inspect) for a stricter setting.
ENV FORWARDED_ALLOW_IPS=172.16.0.0/12

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Shell form via sh -c so ${UVICORN_WORKERS} expands; exec keeps uvicorn as PID 1.
CMD ["sh", "-c", "exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-2} --proxy-headers --forwarded-allow-ips ${FORWARDED_ALLOW_IPS:-172.16.0.0/12}"]
