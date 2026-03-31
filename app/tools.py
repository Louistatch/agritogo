"""Outils custom pour l'agent de forecasting agricole au Togo."""

from agentscope.tool import ToolResponse
from app.database import (
    get_prix_historiques,
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


async def analyser_tendance(
    produit: str,
    marche: str = "",
) -> ToolResponse:
    """Analyse la tendance des prix d'un produit sur les derniers mois.

    Args:
        produit: Nom du produit agricole.
        marche: Nom du marché. Vide = tous les marchés.

    Returns:
        Analyse statistique de la tendance.
    """
    data = get_prix_historiques(produit, marche or None, 60)
    if len(data) < 2:
        return ToolResponse(
            content=f"Pas assez de données pour analyser {produit}.",
        )

    prix_list = [r["prix"] for r in data]
    prix_recent = prix_list[:3]
    prix_ancien = prix_list[-3:]

    moy_recent = sum(prix_recent) / len(prix_recent)
    moy_ancien = sum(prix_ancien) / len(prix_ancien)
    variation = ((moy_recent - moy_ancien) / moy_ancien) * 100

    prix_min = min(prix_list)
    prix_max = max(prix_list)
    prix_moy = sum(prix_list) / len(prix_list)

    if variation > 5:
        tendance = "📈 HAUSSE"
    elif variation < -5:
        tendance = "📉 BAISSE"
    else:
        tendance = "➡️ STABLE"

    return ToolResponse(
        content=(
            f"Analyse de {produit}"
            + (f" à {marche}" if marche else "") + ":\n"
            f"  Tendance: {tendance} ({variation:+.1f}%)\n"
            f"  Prix moyen: {prix_moy:.0f} FCFA/kg\n"
            f"  Min: {prix_min:.0f} | Max: {prix_max:.0f} FCFA/kg\n"
            f"  Données: {len(prix_list)} observations"
        ),
    )
