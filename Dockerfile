FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libportaudio2 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# Use shell form so ${PORT:-8080} is expanded at runtime
CMD gunicorn --bind "0.0.0.0:${PORT:-8080}" --workers 1 --worker-class sync --timeout 120 --log-level info --access-logfile - --error-logfile - app.server:app
