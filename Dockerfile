FROM python:3.11-slim

# Use a non-root user for better security
RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY api/ ./api/
COPY database/ ./database/

# Use the PORT env var (Cloud Run default is 8080)
EXPOSE 8080

ENV PYTHONUNBUFFERED=1

CMD ["sh", "-c", "uvicorn api.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8080}"]
