FROM python:3.11-slim

WORKDIR /app

# Install backend deps then worker-specific deps
COPY backend/requirements.txt /tmp/backend-requirements.txt
COPY workers/requirements.txt /tmp/worker-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt -r /tmp/worker-requirements.txt

COPY backend/ /app/backend/
COPY workers/ /app/workers/

# Make backend importable as `app.*`
ENV PYTHONPATH=/app/backend

WORKDIR /app/workers
