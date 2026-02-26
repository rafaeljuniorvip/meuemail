FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY migrations/ ./migrations/

WORKDIR /app/backend

EXPOSE 8467

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8467"]
