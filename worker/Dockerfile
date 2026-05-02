FROM python:3.12-slim

WORKDIR /app

# System deps (ffmpeg for video timestamp extraction, curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Reuse backend requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared backend app package (models, services, database, config)
COPY backend/app ./app

# Copy worker entrypoint and main module
COPY worker/entrypoint.sh .
COPY worker/main.py .

RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
