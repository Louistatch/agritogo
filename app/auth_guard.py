"""
Garde d'authentification pour les endpoints d'administration.

Les routes /api/v1/ d'AgriTogo n'avaient aucun contrôle d'accès : les endpoints
d'administration (produits, prix, configuration KoboCollect, état du pipeline
ML) étaient joignables par n'importe qui sur Internet. La configuration Kobo
porte un jeton d'API, et la suppression de produits comme de prix est
destructive.

Le jeton porté par la requête est vérifié auprès de GoTrue plutôt que par
signature locale : cela évite d'introduire un SUPABASE_JWT_SECRET, et le coût
d'un aller-retour HTTP est sans importance sur des routes d'administration. Le
rôle est ensuite relu dans public.profiles, seule source de vérité du produit —
jamais dans les claims du jeton, qui ne sont qu'un miroir différé.

L'inscription (/haroo/auth/register) et les lectures publiques restent ouvertes.
"""

import os
from functools import wraps

import requests
from flask import jsonify, request

from .database import get_client


def _bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    token = header[7:].strip()
    return token or None


def _user_id_from_token(token: str) -> str | None:
    """Valide le jeton auprès de GoTrue et retourne l'identifiant, sinon None."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return None
    try:
        res = requests.get(
            f"{url}/auth/v1/user",
            headers={"apikey": key, "Authorization": f"Bearer {token}"},
            timeout=8,
        )
    except requests.RequestException:
        return None
    if not res.ok:
        return None
    return (res.json() or {}).get("id")


def require_super_admin(fn):
    """Réserve la route au super_admin de la plateforme."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _bearer_token()
        if not token:
            return jsonify({"error": "Authentification requise"}), 401

        user_id = _user_id_from_token(token)
        if not user_id:
            return jsonify({"error": "Jeton invalide ou expiré"}), 401

        try:
            res = (
                get_client()
                .table("profiles")
                .select("role")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
        except Exception:
            return jsonify({"error": "Vérification impossible"}), 502

        rows = res.data or []
        if not rows or rows[0].get("role") != "super_admin":
            return jsonify({"error": "Réservé à l'administration"}), 403

        return fn(*args, **kwargs)

    return wrapper
