"""ML modules for AgriTogo."""
import os

def get_data_dir():
    """Resolve data directory — works locally and in Docker (WORKDIR=/app)."""
    _here = os.path.dirname(__file__)
    candidates = [
        os.path.join(_here, '..', '..', 'agentscope', 'data'),  # local dev
        os.path.join('/app', 'agentscope', 'data'),              # Docker
        os.path.join(_here, '..', 'data'),                       # fallback
    ]
    for c in candidates:
        if os.path.isdir(c):
            return os.path.abspath(c)
    # Return best guess even if not found (will fail gracefully in each module)
    return os.path.abspath(candidates[0])
