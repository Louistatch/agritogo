"""
Connexion directe à la base de données PostgreSQL de Haroo (Neon).
Utilise psycopg2-binary — aucune dépendance Django.

Variable d'env requise :
  HAROO_DATABASE_URL  postgresql://user:pwd@host/db?sslmode=require
"""

import os
from functools import lru_cache
from contextlib import contextmanager

try:
    import psycopg2
    import psycopg2.extras
    _PSYCOPG2_AVAILABLE = True
except ImportError:
    _PSYCOPG2_AVAILABLE = False


@lru_cache(maxsize=1)
def _dsn() -> str:
    url = os.environ.get("HAROO_DATABASE_URL", "")
    if not url:
        raise RuntimeError("HAROO_DATABASE_URL non configuré")
    return url


@contextmanager
def get_cursor():
    """Context manager — yields a DictCursor, commits/closes on exit."""
    if not _PSYCOPG2_AVAILABLE:
        raise RuntimeError("psycopg2-binary non installé (pip install psycopg2-binary)")
    conn = psycopg2.connect(_dsn())
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        conn.commit()
    finally:
        conn.close()


def is_available() -> bool:
    """Retourne True si la DB Haroo est configurée et psycopg2 installé."""
    return _PSYCOPG2_AVAILABLE and bool(os.environ.get("HAROO_DATABASE_URL", ""))
