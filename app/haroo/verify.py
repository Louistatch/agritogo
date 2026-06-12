"""
Vérification de carte professionnelle Haroo via Supabase (FaîtiereHub).

Tables utilisées :
  member_cards              — carte (card_number, card_type, status, expiry_date)
  haroo_ouvrier_profiles    — profil ouvrier
  haroo_acheteur_profiles   — profil acheteur
  haroo_agronome_profiles   — profil agronome
  haroo_ouvrier_cantons     — M2M ouvrier ↔ canton
  haroo_acheteur_cantons    — M2M acheteur ↔ canton
  haroo_jobs                — offres d'emploi saisonnier
  haroo_presales            — préventes agricoles
  haroo_missions            — missions agronome
  cantons                   — localités (id, name, prefecture_id)
  prefectures               — (id, name, region_id)
"""

from datetime import date as _date
from .database import get_client, is_available


def verify_card(card_number: str) -> dict:
    """
    Vérifie une carte Haroo (OUVRIER / ACHETEUR / AGRONOME) et retourne le profil enrichi.

    Retour :
    {
        "valid": bool,
        "source": "haroo",
        "card_type": "OUVRIER" | "ACHETEUR" | "AGRONOME",
        "card": { card_number, status, expiry_date, created_at },
        "ouvrier" | "acheteur" | "agronome": { ... },
        "offres" | "preventes" | "missions": [ ... ],
        "error": str  # si valid=False
    }
    """
    if not is_available():
        return {"valid": False, "source": "haroo", "error": "Service non disponible"}

    card_number = card_number.upper().strip()
    sb = get_client()

    try:
        # ── 1. Récupérer la carte ─────────────────────────────────────────────
        res = (
            sb.table("member_cards")
            .select("card_number, card_type, status, expiry_date, created_at")
            .eq("card_number", card_number)
            .in_("card_type", ["OUVRIER", "ACHETEUR", "AGRONOME"])
            .limit(1)
            .execute()
        )
        cards = res.data or []
        if not cards:
            return {"valid": False, "source": "haroo", "error": "Carte non trouvée"}

        card = cards[0]
        expiry = card.get("expiry_date")
        is_expired = expiry and expiry < str(_date.today())
        is_active = card["status"] == "active" and not is_expired

        card_data = {
            "card_number": card["card_number"],
            "status": "expired" if is_expired else card["status"],
            "expiry_date": expiry,
            "created_at": card.get("created_at"),
        }

        result = {
            "valid": is_active,
            "source": "haroo",
            "card_type": card["card_type"],
            "card": card_data,
        }

        if not is_active:
            result["error"] = "Carte expirée ou révoquée"
            return result

        # ── 2. Profil selon card_type ─────────────────────────────────────────
        ct = card["card_type"]
        if ct == "OUVRIER":
            result.update(_build_ouvrier(sb, card_number))
        elif ct == "ACHETEUR":
            result.update(_build_acheteur(sb, card_number))
        elif ct == "AGRONOME":
            result.update(_build_agronome(sb, card_number))

        return result

    except Exception as exc:
        return {"valid": False, "source": "haroo", "error": f"Erreur base de données: {exc}"}


# ── Builders par type ──────────────────────────────────────────────────────────

def _build_ouvrier(sb, card_number: str) -> dict:
    res = (
        sb.table("haroo_ouvrier_profiles")
        .select("id, first_name, last_name, phone, photo_url, competences, disponible, note_moyenne, nombre_avis")
        .eq("card_number", card_number)
        .limit(1)
        .execute()
    )
    profiles = res.data or []
    if not profiles:
        return {}
    op = profiles[0]
    ouvrier_id = op["id"]

    # Cantons disponibles (M2M)
    cantons_res = (
        sb.table("haroo_ouvrier_cantons")
        .select("cantons(name)")
        .eq("ouvrier_id", ouvrier_id)
        .execute()
    )
    cantons = [row["cantons"]["name"] for row in (cantons_res.data or []) if row.get("cantons")]

    # Offres d'emploi ouvertes dans ces cantons (max 5)
    offres = []
    if cantons:
        jobs_res = (
            sb.table("haroo_jobs")
            .select("id, type_travail, description, canton_id, date_debut, date_fin, salaire_horaire, nombre_postes, cantons(name)")
            .eq("statut", "OUVERTE")
            .limit(5)
            .execute()
        )
        for r in (jobs_res.data or []):
            canton_nom = r.get("cantons", {}).get("name") if r.get("cantons") else None
            if canton_nom in cantons:
                offres.append({
                    "id": str(r["id"]),
                    "titre": r["type_travail"],
                    "description": r.get("description"),
                    "canton": canton_nom,
                    "date_debut": r.get("date_debut"),
                    "date_fin": r.get("date_fin"),
                    "tarif_journalier": float(r["salaire_horaire"]) if r.get("salaire_horaire") else None,
                    "nombre_ouvriers": r.get("nombre_postes"),
                })

    return {
        "ouvrier": {
            "first_name": op.get("first_name"),
            "last_name": op.get("last_name"),
            "phone": op.get("phone"),
            "photo_url": op.get("photo_url"),
            "competences": op.get("competences") or [],
            "cantons_disponibles": cantons,
            "disponible": op.get("disponible", True),
            "note_moyenne": float(op.get("note_moyenne") or 0),
            "nombre_avis": op.get("nombre_avis", 0),
        },
        "offres": offres,
    }


def _build_acheteur(sb, card_number: str) -> dict:
    res = (
        sb.table("haroo_acheteur_profiles")
        .select("id, first_name, last_name, phone, photo_url, type_acheteur, produits_interesses, prefecture_id")
        .eq("card_number", card_number)
        .limit(1)
        .execute()
    )
    profiles = res.data or []
    if not profiles:
        return {}
    ap = profiles[0]
    acheteur_id = ap["id"]

    # Cantons d'intervention (M2M)
    cantons_res = (
        sb.table("haroo_acheteur_cantons")
        .select("cantons(name)")
        .eq("acheteur_id", acheteur_id)
        .execute()
    )
    cantons = [row["cantons"]["name"] for row in (cantons_res.data or []) if row.get("cantons")]

    # Préventes disponibles (max 5)
    prev_query = (
        sb.table("haroo_presales")
        .select("id, culture, quantite_estimee, prix_par_tonne, date_recolte_prevue, description, canton_id, cantons(name, prefecture_id)")
        .eq("statut", "DISPONIBLE")
        .order("created_at", desc=True)
        .limit(5)
    )
    if ap.get("prefecture_id"):
        # Filter via canton → prefecture join is tricky in SDK; fetch all then filter
        pass

    prev_res = prev_query.execute()
    preventes = []
    for r in (prev_res.data or []):
        canton_info = r.get("cantons") or {}
        # Filter by prefecture if known
        if ap.get("prefecture_id") and canton_info.get("prefecture_id") != ap["prefecture_id"]:
            continue
        preventes.append({
            "id": str(r["id"]),
            "culture": r["culture"],
            "quantite_estimee": float(r["quantite_estimee"]) if r.get("quantite_estimee") else 0,
            "prix_par_kg": float(r["prix_par_tonne"]) / 1000 if r.get("prix_par_tonne") else 0,
            "date_recolte_prevue": r.get("date_recolte_prevue"),
            "canton": canton_info.get("name"),
            "description": r.get("description") or "",
        })

    return {
        "acheteur": {
            "first_name": ap.get("first_name"),
            "last_name": ap.get("last_name"),
            "phone": ap.get("phone"),
            "photo_url": ap.get("photo_url"),
            "type_acheteur": ap.get("type_acheteur"),
            "produits_interesses": ap.get("produits_interesses") or [],
            "cantons_intervention": cantons,
        },
        "preventes": preventes,
    }


def _build_agronome(sb, card_number: str) -> dict:
    res = (
        sb.table("haroo_agronome_profiles")
        .select("id, first_name, last_name, phone, photo_url, specialisations, canton_id, badge_valide, statut_validation, note_moyenne, nombre_missions, cantons(name, prefectures(name, regions(name)))")
        .eq("card_number", card_number)
        .limit(1)
        .execute()
    )
    profiles = res.data or []
    if not profiles:
        return {}
    ag = profiles[0]
    agronome_id = ag["id"]

    canton_info = ag.get("cantons") or {}
    prefecture_info = canton_info.get("prefectures") or {}
    region_info = prefecture_info.get("regions") or {}

    # Missions actives (DEMANDE ou EN_COURS)
    missions_res = (
        sb.table("haroo_missions")
        .select("id, description, statut, budget_propose, date_debut, date_fin, exploitant_name")
        .eq("agronome_id", agronome_id)
        .in_("statut", ["DEMANDE", "EN_COURS"])
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )
    missions = [
        {
            "id": str(r["id"]),
            "description": r.get("description"),
            "statut": r.get("statut"),
            "budget_propose": float(r["budget_propose"]) if r.get("budget_propose") else None,
            "date_debut": r.get("date_debut"),
            "date_fin": r.get("date_fin"),
            "exploitant": r.get("exploitant_name"),
        }
        for r in (missions_res.data or [])
    ]

    return {
        "agronome": {
            "first_name": ag.get("first_name"),
            "last_name": ag.get("last_name"),
            "phone": ag.get("phone"),
            "photo_url": ag.get("photo_url"),
            "specialisations": ag.get("specialisations") or [],
            "canton": canton_info.get("name"),
            "prefecture": prefecture_info.get("name"),
            "region": region_info.get("name"),
            "badge_valide": ag.get("badge_valide", False),
            "statut_validation": ag.get("statut_validation"),
            "note_moyenne": float(ag.get("note_moyenne") or 0),
            "nombre_missions": ag.get("nombre_missions", 0),
        },
        "missions": missions,
    }
