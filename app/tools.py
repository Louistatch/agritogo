"""Outils custom pour l'agent de forecasting agricole au Togo."""

from agentscope.tool import ToolResponse
from app.database import (
    get_prix_historiques,
    get_tendance_zone,
    get_produits,
    get_marches,
    save_prevision,
)


async def consulter_prix(
    produit: str,
    marche: str = "",
    limit: int = 12,
) -> ToolResponse:
    """Consulte les prix historiques d'un produit agricole au Togo.

    Args:
        produit: Nom du produit (ex: Maïs, Riz local, Tomate, Igname...)
        marche: Nom du marché (ex: Lomé-Adawlato, Kara, Sokodé). Vide = tous.
        limit: Nombre max d'entrées à retourner.

    Returns:
        Les prix historiques du produit.
    """
    data = get_prix_historiques(produit, marche or None, limit)
    if not data:
        return ToolResponse(
            content=f"Aucun prix trouvé pour '{produit}'"
            + (f" au marché de {marche}" if marche else ""),
        )
    lines = [f"Prix historiques de {produit}"
             + (f" - {marche}" if marche else " - tous marchés") + ":"]
    for row in data:
        lines.append(
            f"  {row['date']} | {row['marche']}: {row['prix']:.0f} FCFA/kg"
        )
    return ToolResponse(content="\n".join(lines))


async def lister_produits() -> ToolResponse:
    """Liste tous les produits agricoles disponibles dans la base.

    Returns:
        La liste des produits avec leur catégorie.
    """
    produits = get_produits()
    lines = ["Produits agricoles disponibles au Togo:"]
    for p in produits:
        lines.append(f"  - {p['nom']} ({p['categorie']}, unité: {p['unite']})")
    return ToolResponse(content="\n".join(lines))


async def lister_marches() -> ToolResponse:
    """Liste tous les marchés disponibles au Togo.

    Returns:
        La liste des marchés.
    """
    marches = get_marches()
    return ToolResponse(
        content="Marchés disponibles: " + ", ".join(marches)
    )


async def enregistrer_prevision(
    produit: str,
    marche: str,
    prix_prevu: float,
    date_cible: str,
    confiance: float = 0.7,
) -> ToolResponse:
    """Enregistre une prévision de prix dans la base de données.

    Args:
        produit: Nom du produit agricole.
        marche: Nom du marché.
        prix_prevu: Prix prévu en FCFA/kg.
        date_cible: Date cible de la prévision (YYYY-MM-DD).
        confiance: Niveau de confiance (0.0 à 1.0).

    Returns:
        Confirmation de l'enregistrement.
    """
    save_prevision(produit, marche, prix_prevu, date_cible, confiance)
    return ToolResponse(
        content=f"Prévision enregistrée: {produit} à {marche} → "
        f"{prix_prevu:.0f} FCFA/kg pour le {date_cible} "
        f"(confiance: {confiance*100:.0f}%)",
    )


def _sens(row: dict) -> str:
    if not row.get("trend_known"):
        return "pas de période de comparaison"
    trend = row.get("trend")
    pct = row.get("change_pct")
    pct_txt = f"{float(pct):+.1f} %" if pct is not None else ""
    label = {"up": "📈 HAUSSE", "down": "📉 BAISSE"}.get(trend, "➡️ STABLE")
    return f"{label} {pct_txt} sur 21 jours (contre {row.get('previous_price')} FCFA/kg avant)"


async def analyser_tendance(
    produit: str,
    marche: str = "",
) -> ToolResponse:
    """Prix actuel et tendance d'un produit, par zone (région, préfecture ou canton).

    À utiliser pour toute question « quand vendre », « le prix monte-t-il »,
    « où vendre ». Données observées (SIM-CPC et saisies FaîtiereHub),
    dédupliquées : médiane par marché puis par zone, tendance = 21 derniers jours
    contre les 42 jours précédents, courbe = médianes hebdomadaires.

    Args:
        produit: Nom du produit (ex: Maïs, Soja, Riz, Riz paddy, Haricot, Gari...).
        marche: Zone : région (Kara), préfecture (Binah) ou canton/marché (Kétao).
            Vide = une ligne par région.

    Returns:
        Par zone : prix médian, fourchette, nombre de marchés, date du dernier
        relevé, tendance chiffrée et courbe hebdomadaire.
    """
    try:
        rows = get_tendance_zone(produit, marche or None)
    except Exception:
        rows = []

    if rows:
        niveau = {"region": "région", "prefecture": "préfecture", "canton": "canton"}
        lines = [f"Prix et tendance — {produit}" + (f" — {marche}" if marche else " — par région") + ":"]
        for r in rows[:12]:
            age = r.get("age_days") or 0
            fraicheur = "relevé récent" if age <= 14 else f"⚠️ relevé ancien ({age} jours)"
            courbe = r.get("history") or []
            lines.append(
                f"  • {r.get('scope_name')} ({niveau.get(r.get('scope'), r.get('scope'))}, {r.get('region_name')}) : "
                f"{r.get('price')} FCFA/kg (fourchette {r.get('price_min')}–{r.get('price_max')}, "
                f"{r.get('n_markets')} marché(s) : {', '.join((r.get('markets') or [])[:6])}) — "
                f"dernier relevé {r.get('last_observed')} ({fraicheur}) — {_sens(r)}"
                + (f" — courbe hebdo : {' → '.join(str(v) for v in courbe[-8:])}" if len(courbe) >= 2 else "")
                + f" — source : {', '.join(r.get('sources') or [])}"
            )
        lines.append(
            "  Méthode : données observées dédupliquées, médiane par marché puis par zone ; "
            "tendance = 21 j contre les 42 j précédents (seuil ±3 %)."
        )
        return ToolResponse(content="\n".join(lines))

    # Repli : relevés bruts, si la vue partagée n'est pas disponible.
    data = get_prix_historiques(produit, marche or None, 60)
    if len(data) < 2:
        return ToolResponse(
            content=f"Pas assez de données pour analyser {produit}"
            + (f" à {marche}" if marche else "") + ".",
        )

    prix_list = [r["prix"] for r in data]
    prix_recent = prix_list[:3]
    prix_ancien = prix_list[-3:]

    moy_recent = sum(prix_recent) / len(prix_recent)
    moy_ancien = sum(prix_ancien) / len(prix_ancien)
    variation = ((moy_recent - moy_ancien) / moy_ancien) * 100

    if variation > 5:
        tendance = "📈 HAUSSE"
    elif variation < -5:
        tendance = "📉 BAISSE"
    else:
        tendance = "➡️ STABLE"

    return ToolResponse(
        content=(
            f"Analyse de {produit}"
            + (f" à {marche}" if marche else "") + " (relevés bruts, faible confiance):\n"
            f"  Tendance: {tendance} ({variation:+.1f}%)\n"
            f"  Prix moyen: {sum(prix_list) / len(prix_list):.0f} FCFA/kg\n"
            f"  Min: {min(prix_list):.0f} | Max: {max(prix_list):.0f} FCFA/kg\n"
            f"  Données: {len(prix_list)} observations"
        ),
    )


async def prevoir_prix(
    produit: str,
    marche: str = "",
) -> ToolResponse:
    """Prévision du prix d'un produit pour les 4 prochaines semaines.

    À utiliser pour « quel sera le prix », « le prix va-t-il monter »,
    « faut-il attendre pour vendre ». Modèle évalué sur les données réelles :
    la réponse donne sa précision mesurée et sa confiance ; c'est une
    PRÉVISION, jamais un prix observé.

    Args:
        produit: Nom du produit (Maïs, Soja, Sorgho, Haricot, Riz, Mil...).
        marche: Zone : région (Kara), préfecture (Binah) ou canton (Kétao).
            Vide = Togo entier.

    Returns:
        Dernier prix observé, prévisions hebdomadaires avec fourchette à 80 %,
        sens attendu, précision mesurée contre « le prix ne bouge pas ».
    """
    try:
        from app.ml.price_forecast import run_price_forecast

        r = run_price_forecast(produit, marche or None)
    except Exception as exc:  # pragma: no cover - dépend de la base
        return ToolResponse(content=f"Prévision indisponible pour {produit} : {exc}")
    if not r.get("ok"):
        return ToolResponse(
            content=f"Pas de prévision fiable pour {produit}"
            + (f" à {marche}" if marche else "")
            + f" : {r.get('reason')}. Utilise analyser_tendance pour la tendance observée.",
        )
    v = r["validation"]
    lines = [
        f"PRÉVISION (modèle {r['modele']}) — {r['produit']} — {r['zone']}",
        f"  Dernier prix observé : {r['dernier_prix']} FCFA/kg (semaine du {r['derniere_semaine']}, "
        f"{r['semaines_observees']} semaines de relevés)",
    ]
    for p in r["previsions"]:
        lines.append(f"  Semaine du {p['semaine_du']} : {p['prix']} FCFA/kg (80 % : {p['bas']}–{p['haut']})")
    lines.append(f"  Sens attendu sur 4 semaines : {r['sens']} ({r['variation_4_semaines_pct']:+.1f} %)")
    if v.get("folds"):
        lines.append(
            f"  Précision mesurée à {v['horizon_semaines']} semaines sur {v['folds']} essais : erreur moyenne "
            f"{v['mape']} % (contre {v['mape_naive']} % pour « le prix ne bouge pas »)"
        )
    lines.append(f"  Confiance : {r['confiance']}")
    if r["confiance"] == "faible":
        lines.append("  ⚠️ Sur cette série, le modèle ne fait pas mieux que « le prix ne bouge pas » : ne pas fonder une décision dessus.")
    return ToolResponse(content="\n".join(lines))
