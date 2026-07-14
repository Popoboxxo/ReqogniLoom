# Backend Dockerfile — ARCH-L1 Django Backend
# ADR-08: Self-Hosted via Docker Compose (no Kubernetes in v1)

FROM python:3.12-slim

# Prevent interactive prompts during package installation
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN addgroup --system app && adduser --system --ingroup app app

# Ensure working directory is owned by app user
RUN chown -R app:app /app

# Collect static files (required for production deployment)
RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Run as non-root user
USER app

# Production: Gunicorn managing uvicorn ASGI workers (REQ-044).
# ASGI is required so the async MCP SSE transport streams without blocking a
# sync worker per connected client. Multi-worker deployment (4 workers).
CMD ["gunicorn", "reqflow.asgi:application", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "4"]
