# ---- Build stage ----
FROM python:3.12-slim AS builder

WORKDIR /build

# Install deps in a virtual env to keep the final image clean
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt


# ---- Runtime stage ----
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="AuditIQ API"
LABEL org.opencontainers.image.description="FastAPI backend for AuditIQ"

WORKDIR /app

# Copy the venv and the application code
COPY --from=builder /opt/venv /opt/venv
COPY ./app ./app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

EXPOSE 8000

# Non-root user for security
RUN addgroup --system auditiq && adduser --system --ingroup auditiq auditiq
USER auditiq

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
