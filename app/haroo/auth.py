"""
Authentification Haroo — utilisateurs OUVRIER / ACHETEUR / AGRONOME.

Les comptes vivent dans l'unique base Supabase partagée de FaîtiereHub
(auth.users). Flux d'inscription :

  1. Création de l'utilisateur via l'API admin GoTrue (service_role).
  2. Le trigger Supabase handle_new_user crée public.profiles.
  3. profiles.haroo_type est posé à 'ouvrier' / 'acheteur' / 'agronome'.
  4. Un profil métier est créé dans haroo_<type>_profiles.

Un compte porte deux couches indépendantes : profiles.role pour la couche
organisationnelle (coopératives) et profiles.haroo_type pour la couche Haroo.
Écrire le type Haroo dans role écraserait la couche organisationnelle, ce qui
empêchait jusqu'ici un membre de coopérative d'être aussi ouvrier. role est
encore écrit ici le temps que le front bascule, puis cessera de l'être.

La connexion est un simple grant password GoTrue : les jetons retournés sont
les mêmes que ceux émis pour FaîtiereHub (même auth, même base).

Variables d'env requises (mêmes que le reste d'AgriTogo) :
  SUPABASE_URL         — https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY — service_role key
"""

import os
import re

import requests

from .database import get_client, is_available

# card_type carte → (table de profil, type de profil Haroo)
PROFILE_TABLES = {
    "OUVRIER": ("haroo_ouvrier_profiles", "ouvrier"),
    "ACHETEUR": ("haroo_acheteur_profiles", "acheteur"),
    "AGRONOME": ("haroo_agronome_profiles", "agronome"),
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[+0-9 ()\-.]{8,40}$")


def _supabase_url() -> str:
    return os.environ["SUPABASE_URL"].rstrip("/")


def _auth_headers() -> dict:
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _validate_registration(payload: dict) -> tuple[dict | None, str | None]:
    """Retourne (données nettoyées, None) ou (None, message d'erreur)."""
    profile_type = str(payload.get("profile_type", "")).upper().strip()
    if profile_type not in PROFILE_TABLES:
        return None, "profile_type doit être OUVRIER, ACHETEUR ou AGRONOME"

    email = str(payload.get("email", "")).strip().lower()
    if not _EMAIL_RE.match(email):
        return None, "Adresse email invalide"

    password = str(payload.get("password", ""))
    if len(password) < 8:
        return None, "Le mot de passe doit contenir au moins 8 caractères"

    first_name = str(payload.get("first_name", "")).strip()
    last_name = str(payload.get("last_name", "")).strip()
    if not (2 <= len(first_name) <= 100) or not (2 <= len(last_name) <= 100):
        return None, "Prénom et nom sont requis (2 à 100 caractères)"

    phone = str(payload.get("phone", "")).strip()
    if phone and not _PHONE_RE.match(phone):
        return None, "Numéro de téléphone invalide"

    return {
        "profile_type": profile_type,
        "email": email,
        "password": password,
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone or None,
    }, None


def register_user(payload: dict) -> tuple[dict, int]:
    """
    Inscrit un professionnel Haroo dans la Supabase partagée.

    Retour : (corps JSON, code HTTP)
    """
    if not is_available():
        return {"success": False, "error": "Service non disponible"}, 503

    data, error = _validate_registration(payload or {})
    if error:
        return {"success": False, "error": error}, 400

    # ── 1. Créer l'utilisateur auth (email confirmé : pas de SMTP côté Haroo) ──
    try:
        res = requests.post(
            f"{_supabase_url()}/auth/v1/admin/users",
            json={
                "email": data["email"],
                "password": data["password"],
                "email_confirm": True,
                "user_metadata": {
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "phone": data["phone"],
                },
                "app_metadata": {"haroo_type": data["profile_type"]},
            },
            headers=_auth_headers(),
            timeout=10,
        )
    except requests.RequestException as exc:
        return {"success": False, "error": f"Auth indisponible: {exc}"}, 502

    if res.status_code in (409, 422):
        return {"success": False, "error": "Un compte existe déjà avec cet email"}, 409
    if not res.ok:
        return {"success": False, "error": "Création du compte impossible"}, 502

    user_id = res.json().get("id")
    if not user_id:
        return {"success": False, "error": "Réponse auth invalide"}, 502

    table, haroo_type = PROFILE_TABLES[data["profile_type"]]
    sb = get_client()

    try:
        # ── 2. Poser la couche Haroo ────────────────────────────────────────────
        # Double écriture transitoire (étape 2 du passage au compte à deux
        # couches) : haroo_type est la nouvelle source, role reste écrit le
        # temps que le front bascule. L'écriture de role disparaîtra à l'étape 5,
        # pour qu'un compte puisse être à la fois membre d'une coopérative et
        # professionnel Haroo — aujourd'hui ce role écrase la couche org.
        sb.table("profiles").upsert(
            {
                "id": user_id,
                "email": data["email"],
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "role": haroo_type,
                "haroo_type": haroo_type,
            },
            on_conflict="id",
        ).execute()

        # ── 3. Profil métier Haroo ──────────────────────────────────────────────
        sb.table(table).insert(
            {
                "user_id": user_id,
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "phone": data["phone"],
            }
        ).execute()
    except Exception as exc:
        # Rollback : ne pas laisser un compte auth orphelin sans profil Haroo.
        try:
            requests.delete(
                f"{_supabase_url()}/auth/v1/admin/users/{user_id}",
                headers=_auth_headers(),
                timeout=10,
            )
        except requests.RequestException:
            pass
        return {"success": False, "error": f"Création du profil impossible: {exc}"}, 502

    return {
        "success": True,
        "user_id": user_id,
        "profile_type": data["profile_type"],
        "role": haroo_type,
        "haroo_type": haroo_type,
    }, 201


def login_user(payload: dict) -> tuple[dict, int]:
    """
    Connexion par email / mot de passe (grant password GoTrue).

    Retourne les jetons Supabase + le type de profil Haroo. Utilise requests
    plutôt que le client partagé pour ne pas écraser sa session service_role.
    """
    if not is_available():
        return {"success": False, "error": "Service non disponible"}, 503

    payload = payload or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    if not _EMAIL_RE.match(email) or not password:
        return {"success": False, "error": "Email et mot de passe requis"}, 400

    try:
        res = requests.post(
            f"{_supabase_url()}/auth/v1/token?grant_type=password",
            json={"email": email, "password": password},
            headers=_auth_headers(),
            timeout=10,
        )
    except requests.RequestException as exc:
        return {"success": False, "error": f"Auth indisponible: {exc}"}, 502

    if res.status_code == 400:
        return {"success": False, "error": "Email ou mot de passe incorrect"}, 401
    if not res.ok:
        return {"success": False, "error": "Connexion impossible"}, 502

    session = res.json()
    user = session.get("user") or {}
    user_id = user.get("id")

    # Rôle + profil métier depuis la base partagée
    role = None
    haroo_type = None
    profile = None
    profile_type = None
    if user_id:
        sb = get_client()
        prof_res = (
            sb.table("profiles")
            .select("role, haroo_type, first_name, last_name")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        rows = prof_res.data or []
        if rows:
            role = rows[0].get("role")
            # haroo_type fait foi ; role n'est qu'un repli pour les comptes
            # créés avant la bascule et pas encore migrés.
            haroo_type = rows[0].get("haroo_type") or role

        for ptype, (table, table_haroo_type) in PROFILE_TABLES.items():
            if haroo_type and haroo_type != table_haroo_type:
                continue
            hp_res = (
                sb.table(table)
                .select("id, card_number, first_name, last_name, phone, photo_url")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            hp_rows = hp_res.data or []
            if hp_rows:
                profile = hp_rows[0]
                profile_type = ptype
                break

    return {
        "success": True,
        "access_token": session.get("access_token"),
        "refresh_token": session.get("refresh_token"),
        "expires_in": session.get("expires_in"),
        "user_id": user_id,
        "role": role,
        "haroo_type": haroo_type,
        "profile_type": profile_type,
        "profile": profile,
    }, 200
