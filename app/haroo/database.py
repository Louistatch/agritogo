"""
Connexion Haroo via le client Supabase partagé de FaîtiereHub.

Variables d'env requises (mêmes que le reste d'AgriTogo) :
  SUPABASE_URL         — https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY — service_role key
"""

from app.database import _get_client


def get_client():
    return _get_client()


def is_available() -> bool:
    """Retourne True si le client Supabase est configuré."""
    import os
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"))
