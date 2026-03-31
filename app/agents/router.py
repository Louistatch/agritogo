"""Routage des requêtes vers les agents spécialisés du Decision Intelligence Engine."""

import re


def route_query(query: str) -> str:
    """Détermine l'agent approprié en fonction des mots-clés de la requête.

    Args:
        query: La requête utilisateur en français.

    Returns:
        Le type d'agent à solliciter.
    """
    q = query.lower()

    routing_rules: list[tuple[list[str], str]] = [
        (["prix", "marché", "tendance"], "market_intel"),
        (["prévision", "prédiction", "forecast", "modèle"], "quant_forecast"),
        (["risque", "volatilité", "crédit"], "risk_volatility"),
        (["décision", "vendre", "acheter", "stocker", "conseil"], "decision"),
        (["résumé", "rapport", "simple"], "ux_agent"),
    ]

    for keywords, agent_type in routing_rules:
        if any(kw in q for kw in keywords):
            return agent_type

    return "coordinator"


def should_debate(query: str) -> bool:
    """Détermine si la requête nécessite un débat multi-modèle.

    Retourne True pour les décisions à fort enjeu : vente, achat,
    gros montants, ou engagements financiers importants.

    Args:
        query: La requête utilisateur.

    Returns:
        True si un débat Gemini vs Qwen est recommandé.
    """
    q = query.lower()

    high_stakes_keywords = [
        "vendre", "acheter", "investir", "emprunter",
        "crédit", "prêt", "contrat", "engagement",
    ]

    has_large_amount = bool(re.search(r"\d{6,}", q))  # >= 100 000 FCFA
    has_high_stakes = any(kw in q for kw in high_stakes_keywords)

    return has_high_stakes or has_large_amount


def select_model(agent_type: str) -> str:
    """Sélectionne le modèle LLM optimal pour chaque type d'agent.

    Gemini : raisonnement stratégique, synthèse, communication.
    Qwen : calculs quantitatifs, modélisation statistique.

    Args:
        agent_type: Le type d'agent (ex: "market_intel", "quant_forecast").

    Returns:
        "gemini" ou "qwen".
    """
    # All agents use Gemini (Qwen disabled until activated)
    return "gemini"
