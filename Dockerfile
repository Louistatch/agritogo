FROM python:3.11-slim

WORKDIR /app

# libportaudio2 required by sounddevice (agentscope dependency)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

# Install app dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Install local agentscope (dev0) — overrides PyPI version
RUN pip install --no-cache-dir -e . --no-deps

ENV PORT=8080
EXPOSE 8080

CMD gunicorn --bind "0.0.0.0:${PORT}" --workers 1 --timeout 120 --log-level info app.server:app
