# IBM-compliant base image sourced from Red Hat registry (M-1).
FROM registry.redhat.io/ubi9/python-311-minimal:latest

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements-web.txt requirements-web.lock ./
RUN pip install --no-cache-dir -r requirements-web.lock

COPY . ./
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Schema upgrades are a deliberate release step, not an implicit action each
# time a horizontally scaled web instance starts.
CMD ["sh", "-c", "uvicorn app.web.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
