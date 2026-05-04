FROM python:3.11-slim

WORKDIR /app

# System deps: gcc for compiled packages, libportaudio2 for sounddevice (agentscope)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

# Install ALL dependencies from requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY . .

# DO NOT run pip install -e . — pyproject.toml belongs to agentscope upstream framework
# gunicorn finds app.server:app via WORKDIR /app

ENV PORT=8080
EXPOSE 8080

CMD gunicorn --bind "0.0.0.0:${PORT}" --workers 1 --timeout 120 --log-level info app.server:app
