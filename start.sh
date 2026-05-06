#!/bin/bash
set -e

echo "=== AgriTogo Startup ==="
echo "PORT=${PORT:-8080}"
echo "Python: $(python --version)"
echo "Working dir: $(pwd)"
echo "Files: $(ls app/)"

# Test critical import before starting gunicorn
echo "Testing Flask import..."
python -c "
import sys
try:
    from flask import Flask
    print('Flask OK')
except Exception as e:
    print(f'Flask FAILED: {e}')
    sys.exit(1)

try:
    from app.database import init_db
    print('Database OK')
except Exception as e:
    print(f'Database FAILED: {e}')
    sys.exit(1)

try:
    from app.server import app
    print('Server import OK')
except Exception as e:
    print(f'Server FAILED: {e}')
    sys.exit(1)

print('All imports OK — starting gunicorn')
"

PORT=${PORT:-8080}
echo "Starting gunicorn on port $PORT..."
exec gunicorn \
    --bind "0.0.0.0:$PORT" \
    --workers 1 \
    --worker-class sync \
    --timeout 120 \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    app.server:app
