FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Install agentscope in editable mode
RUN pip install --no-cache-dir -e .

# Railway injects PORT at runtime — default to 8080 if not set
ENV PORT=8080
EXPOSE 8080

# Use shell form so $PORT is expanded by the shell at runtime
CMD gunicorn --bind "0.0.0.0:${PORT}" --workers 2 --timeout 120 --log-level info app.server:app
