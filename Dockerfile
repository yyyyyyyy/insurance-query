FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (curl is required for the docker-compose healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create a non-privileged user and switch to it
RUN groupadd --system --gid 1001 appgroup \
    && useradd --system --uid 1001 --gid appgroup --create-home --home-dir /home/app --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appgroup /app

USER appuser

# Expose API port
EXPOSE 8000

# Run the API server
CMD ["python", "-m", "apps.api.main"]
