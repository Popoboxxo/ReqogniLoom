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

# Collect static files (for production; dev uses runserver)
# RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Default: Django development server
# Production: replace with gunicorn
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
