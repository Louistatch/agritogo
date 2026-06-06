"""
Client HTTP vers l'API Haroo (plateforme Django).
Expose verify_card() utilisé par le blueprint /api/v1/haroo/*.

Variable d'env requise : HAROO_API_URL
  ex: https://haroo-production.up.railway.app
"""

import os
import requests

_HAROO_URL = os.environ.get("HAROO_API_URL", "").rstrip("/")
_TIMEOUT = 5  # secondes


def verify_card(card_number: str) -> dict | None:
    """
    GET {HAROO_URL}/api/cards/verify/<card_number>/

    Retourne le dict JSON Haroo si trouvé (valid ou non),
    None si Haroo non configuré ou erreur réseau.
    """
    if not _HAROO_URL:
        return None
    url = f"{_HAROO_URL}/api/cards/verify/{card_number.upper().strip()}/"
    try:
        resp = requests.get(url, timeout=_TIMEOUT, headers={"Accept": "application/json"})
        if resp.status_code in (200, 404):
            return resp.json()
        return None
    except requests.RequestException:
        return None
