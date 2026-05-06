FROM python:3.11-slim

WORKDIR /app

# System deps: gcc for compiled packages, libportaudio2 for sounddevice (agentscope)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libportaudio2 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies with pinned versions
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY . .

# Verify critical imports at build time — fail fast if something is broken
RUN python -c "import flask, gunicorn, sklearn, xgboost, arch, pandas, agentscope; print('All imports OK')"

EXPOSE 8080

# --preload: load app once, share across workers (saves memory, faster startup)
# --worker-class sync: stable for Flask + blocking ML calls
# --workers 1: Railway free tier (512MB RAM) — increase if on paid plan
# --timeout 120: ML inference can take time
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "1", \
     "--worker-class", "sync", \
     "--timeout", "120", \
     "--preload", \
     "--log-level", "info", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app.server:app"]
