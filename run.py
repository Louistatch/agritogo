"""Railway startup script — reads $PORT and starts gunicorn."""
import os
import subprocess
import sys

port = os.environ.get("PORT", "8080")
print(f"[run.py] Starting gunicorn on port {port}", flush=True)

cmd = [
    "gunicorn",
    "--bind", f"0.0.0.0:{port}",
    "--workers", "2",
    "--worker-class", "sync",
    "--timeout", "120",
    "--log-level", "info",
    "--access-logfile", "-",
    "--error-logfile", "-",
    "app.server:app",
]

print(f"[run.py] CMD: {' '.join(cmd)}", flush=True)
result = subprocess.run(cmd)
sys.exit(result.returncode)
