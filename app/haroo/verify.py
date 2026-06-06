"""
Vérification de carte professionnelle Haroo.

Requête directe sur la DB PostgreSQL (Neon) de Haroo.
Tables Django auto-nommées : <app>_<model> en minuscules.

Schéma utilisé :
  cards_card          → carte (card_number, card_type, statut, expiry_date, ouvrier_id, acheteur_id, agronome_id)
  users_user          → utilisateur (first_name, last_name, phone_number, photo_profil)
  users_ouvrierprofile   → ouvrier (user_id, competences, note_moyenne, nombre_avis, disponible)
  users_acheteurprofile  → acheteur (user_id, type_acheteur, produits_interesses, prefecture_id)
  users_agronomeprofile  → agronome (user_id, canton_rattachement_id, specialisations, badge_valide, statut_validation, note_moyenne, nombre_avis)
  users_ouvrierprofile_cantons_disponibles  → M2M ouvrier ↔ canton
  users_acheteurprofile_cantons_intervention → M2M acheteur ↔ canton
  jobs_offreemploisaisonnier    → offres emploi (type_travail, description, canton_id, date_debut, date_fin, salaire_horaire, nombre_postes, statut)
  presales_preventeagricole     → préventes (culture, quantite_estimee, prix_par_tonne, date_recolte_prevue, canton_production_id, description, statut)
  missions_mission              → missions (description, statut, budget_propose, date_debut, date_fin, exploitant_id, agronome_id)
  locations_canton              → canton (nom, prefecture_id)
  locations_prefecture          → prefecture (nom, region_id)
  locations_region              → region (nom)
"""

from datetime import date as _date
from .database import get_cursor, is_available


def verify_card(card_number: str) -> dict:
    """
    Vérifie une carte Haroo et retourne le profil enrichi.

    Retour :
    {
        "valid": bool,
        "source": "haroo",
        "card_type": "OUVRIER" | "ACHETEUR" | "AGRONOME",
        "card": { card_number, status, expiry_date, created_at },
        "ouvrier" | "acheteur" | "agronome": { ... },
        "offres" | "preventes" | "missions": [ ... ],   # données contextuelles
        "error": str  # si valid=False
    }
    """
    if not is_available():
        return {"valid": False, "source": "haroo", "error": "Service non disponible"}

    card_number = card_number.upper().strip()

    try:
        with get_cursor() as cur:
            # ── 1. Récupérer la carte ─────────────────────────────────────────
            cur.execute("""
                SELECT c.id, c.card_number, c.card_type, c.statut, c.expiry_date,
                       c.created_at, c.ouvrier_id, c.acheteur_id, c.agronome_id
                FROM cards_card c
                WHERE c.card_number = %s
                LIMIT 1
            """, (card_number,))
            card = cur.fetchone()

            if not card:
                return {"valid": False, "source": "haroo", "error": "Carte non trouvée"}

            # Vérifier expiration
            is_expired = card["expiry_date"] and card["expiry_date"] < _date.today()
            is_active = card["statut"] == "active" and not is_expired

            card_data = {
                "card_number": card["card_number"],
                "status": "expired" if is_expired else card["statut"],
                "expiry_date": str(card["expiry_date"]) if card["expiry_date"] else None,
                "created_at": card["created_at"].isoformat() if card["created_at"] else None,
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

            # ── 2. Profil selon card_type ��────────────────────────────────────
            if card["card_type"] == "OUVRIER" and card["ouvrier_id"]:
                result.update(_build_ouvrier(cur, card["ouvrier_id"]))

            elif card["card_type"] == "ACHETEUR" and card["acheteur_id"]:
                result.update(_build_acheteur(cur, card["acheteur_id"]))

            elif card["card_type"] == "AGRONOME" and card["agronome_id"]:
                result.update(_build_agronome(cur, card["agronome_id"]))

            return result

    except Exception as exc:
        return {"valid": False, "source": "haroo", "error": f"Erreur base de données: {exc}"}


# ── Builders par type ─────────────────────────────────────────────────────────

def _build_ouvrier(cur, ouvrier_id: int) -> dict:
    cur.execute("""
        SELECT op.competences, op.note_moyenne, op.nombre_avis, op.disponible,
               u.first_name, u.last_name, u.phone_number, u.photo_profil
        FROM users_ouvrierprofile op
        JOIN users_user u ON u.id = op.user_id
        WHERE op.id = %s
    """, (ouvrier_id,))
    op = cur.fetchone()
    if not op:
        return {}

    # Cantons disponibles (M2M)
    cur.execute("""
        SELECT lc.nom
        FROM users_ouvrierprofile_cantons_disponibles m
        JOIN locations_canton lc ON lc.id = m.canton_id
        WHERE m.ouvrierprofile_id = %s
    """, (ouvrier_id,))
    cantons = [r["nom"] for r in cur.fetchall()]

    # Offres d'emploi ouvertes dans ces cantons (max 5)
    cur.execute("""
        SELECT j.id, j.type_travail, j.description, lc.nom AS canton,
               j.date_debut, j.date_fin, j.salaire_horaire, j.nombre_postes
        FROM jobs_offreemploisaisonnier j
        JOIN locations_canton lc ON lc.id = j.canton_id
        WHERE j.statut = 'OUVERTE'
          AND lc.nom = ANY(%s)
        ORDER BY j.created_at DESC
        LIMIT 5
    """, (cantons or ['__none__'],))
    offres = [
        {
            "id": str(r["id"]),
            "titre": r["type_travail"],
            "description": r["description"],
            "canton": r["canton"],
            "date_debut": str(r["date_debut"]),
            "date_fin": str(r["date_fin"]),
            "tarif_journalier": float(r["salaire_horaire"]) if r["salaire_horaire"] else None,
            "nombre_ouvriers": r["nombre_postes"],
        }
        for r in cur.fetchall()
    ]

    return {
        "ouvrier": {
            "first_name": op["first_name"],
            "last_name": op["last_name"],
            "phone": op["phone_number"],
            "photo_url": op["photo_profil"] or None,
            "competences": op["competences"] if isinstance(op["competences"], list) else [],
            "cantons_disponibles": cantons,
            "disponible": op["disponible"],
            "note_moyenne": float(op["note_moyenne"]),
            "nombre_avis": op["nombre_avis"],
        },
        "offres": offres,
    }


def _build_acheteur(cur, acheteur_id: int) -> dict:
    cur.execute("""
        SELECT ap.type_acheteur, ap.produits_interesses, ap.prefecture_id,
               u.first_name, u.last_name, u.phone_number, u.photo_profil
        FROM users_acheteurprofile ap
        JOIN users_user u ON u.id = ap.user_id
        WHERE ap.id = %s
    """, (acheteur_id,))
    ap = cur.fetchone()
    if not ap:
        return {}

    # Cantons d'intervention (M2M)
    cur.execute("""
        SELECT lc.nom
        FROM users_acheteurprofile_cantons_intervention m
        JOIN locations_canton lc ON lc.id = m.canton_id
        WHERE m.acheteurprofile_id = %s
    """, (acheteur_id,))
    cantons = [r["nom"] for r in cur.fetchall()]

    # Préventes disponibles (filtrées par préfecture si connue, max 5)
    if ap["prefecture_id"]:
        cur.execute("""
            SELECT p.id, p.culture, p.quantite_estimee, p.prix_par_tonne,
                   p.date_recolte_prevue, lc.nom AS canton, p.description
            FROM presales_preventeagricole p
            JOIN locations_canton lc ON lc.id = p.canton_production_id
            WHERE p.statut = 'DISPONIBLE'
              AND lc.prefecture_id = %s
            ORDER BY p.created_at DESC
            LIMIT 5
        """, (ap["prefecture_id"],))
    else:
        cur.execute("""
            SELECT p.id, p.culture, p.quantite_estimee, p.prix_par_tonne,
                   p.date_recolte_prevue, lc.nom AS canton, p.description
            FROM presales_preventeagricole p
            JOIN locations_canton lc ON lc.id = p.canton_production_id
            WHERE p.statut = 'DISPONIBLE'
            ORDER BY p.created_at DESC
            LIMIT 5
        """)
    preventes = [
        {
            "id": str(r["id"]),
            "culture": r["culture"],
            "quantite_estimee": float(r["quantite_estimee"]),
            "prix_par_kg": float(r["prix_par_tonne"]) / 1000 if r["prix_par_tonne"] else 0,
            "date_recolte_prevue": str(r["date_recolte_prevue"]),
            "canton": r["canton"],
            "description": r["description"] or "",
        }
        for r in cur.fetchall()
    ]

    return {
        "acheteur": {
            "first_name": ap["first_name"],
            "last_name": ap["last_name"],
            "phone": ap["phone_number"],
            "photo_url": ap["photo_profil"] or None,
            "type_acheteur": ap["type_acheteur"],
            "produits_interesses": ap["produits_interesses"] if isinstance(ap["produits_interesses"], list) else [],
            "cantons_intervention": cantons,
        },
        "preventes": preventes,
    }


def _build_agronome(cur, agronome_id: int) -> dict:
    cur.execute("""
        SELECT ag.specialisations, ag.badge_valide, ag.statut_validation,
               ag.note_moyenne, ag.nombre_avis, ag.canton_rattachement_id,
               u.id AS user_id, u.first_name, u.last_name, u.phone_number, u.photo_profil,
               lc.nom AS canton, lp.nom AS prefecture, lr.nom AS region
        FROM users_agronomeprofile ag
        JOIN users_user u ON u.id = ag.user_id
        LEFT JOIN locations_canton lc ON lc.id = ag.canton_rattachement_id
        LEFT JOIN locations_prefecture lp ON lp.id = lc.prefecture_id
        LEFT JOIN locations_region lr ON lr.id = lp.region_id
        WHERE ag.id = %s
    """, (agronome_id,))
    ag = cur.fetchone()
    if not ag:
        return {}

    # Missions actives (DEMANDE ou EN_COURS)
    cur.execute("""
        SELECT m.id, m.description, m.statut, m.budget_propose,
               m.date_debut, m.date_fin,
               u.first_name || ' ' || u.last_name AS exploitant
        FROM missions_mission m
        JOIN users_user u ON u.id = m.exploitant_id
        WHERE m.agronome_id = %s
          AND m.statut IN ('DEMANDE', 'EN_COURS')
        ORDER BY m.created_at DESC
        LIMIT 5
    """, (ag["user_id"],))
    missions = [
        {
            "id": str(r["id"]),
            "description": r["description"],
            "statut": r["statut"],
            "budget_propose": float(r["budget_propose"]) if r["budget_propose"] else None,
            "date_debut": str(r["date_debut"]) if r["date_debut"] else None,
            "date_fin": str(r["date_fin"]) if r["date_fin"] else None,
            "exploitant": r["exploitant"],
        }
        for r in cur.fetchall()
    ]

    return {
        "agronome": {
            "first_name": ag["first_name"],
            "last_name": ag["last_name"],
            "phone": ag["phone_number"],
            "photo_url": ag["photo_profil"] or None,
            "specialisations": ag["specialisations"] if isinstance(ag["specialisations"], list) else [],
            "canton": ag["canton"],
            "prefecture": ag["prefecture"],
            "region": ag["region"],
            "badge_valide": ag["badge_valide"],
            "statut_validation": ag["statut_validation"],
            "note_moyenne": float(ag["note_moyenne"]),
            "nombre_missions": ag["nombre_avis"],
        },
        "missions": missions,
    }
