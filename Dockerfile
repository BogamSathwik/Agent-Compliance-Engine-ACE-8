FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and migrations
COPY app/ app/
COPY migrations/ migrations/
COPY alembic.ini .
COPY README.md .

EXPOSE 8000

# Default command starts the API service
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
