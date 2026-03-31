"""Outils AgentScope pour l'intégration KoboCollect terrain."""

from agentscope.tool import ToolResponse
from app.kobo import (
    KoboClient,
    generate_price_survey_xlsform,
    generate_farmer_survey_xlsform,
    load_kobo_config,
)


def _get_client() -> KoboClient | None:
    """Crée un KoboClient depuis la config sauvegardée."""
    cfg = load_kobo_config()
    if not cfg:
        return None
    return KoboClient(cfg["base_url"], cfg["token"])


async def consulter_donnees_terrain(form_name: str = "") -> ToolResponse:
    """Consulte les données de collecte terrain via KoboCollect.

    Args:
        form_name: Nom (ou partie du nom) du formulaire à consulter.
                   Vide = premier formulaire trouvé.

    Returns:
        Résumé des soumissions du formulaire.
    """
    try:
        client = _get_client()
        if not client:
            return ToolResponse(
                content="⚠️ KoboCollect non configuré. "
                "Utilisez la page admin pour saisir l'URL et le token.",
            )
        forms = client.get_forms()
        if not forms:
            return ToolResponse(content="Aucun formulaire trouvé sur KoboCollect.")

        target = None
        if form_name:
            for f in forms:
                if form_name.lower() in f["name"].lower():
                    target = f
                    break
        if not target:
            target = forms[0]

        subs = client.get_submissions(target["uid"])
        lines = [
            f"📋 Formulaire: {target['name']}",
            f"   Statut: {target['deployment_status']}",
            f"   Soumissions: {len(subs)}",
        ]
        if subs:
            lines.append("\nDernières entrées:")
            for s in subs[:5]:
                preview = {k: v for k, v in list(s.items())[:4]
                           if not k.startswith("_")}
                lines.append(f"  • {preview}")
        return ToolResponse(content="\n".join(lines))
    except Exception as e:
        return ToolResponse(content=f"Erreur KoboCollect: {e}")


async def analyser_collecte_terrain() -> ToolResponse:
    """Analyse l'ensemble des formulaires et collectes terrain KoboCollect.

    Returns:
        Vue d'ensemble de tous les formulaires et nombre de soumissions.
    """
    try:
        client = _get_client()
        if not client:
            return ToolResponse(
                content="⚠️ KoboCollect non configuré. "
                "Utilisez la page admin pour saisir l'URL et le token.",
            )
        forms = client.get_forms()
        if not forms:
            return ToolResponse(content="Aucun formulaire trouvé.")

        lines = [f"📊 KoboCollect — {len(forms)} formulaire(s):\n"]
        total = 0
        for f in forms:
            subs = client.get_submissions(f["uid"])
            count = len(subs)
            total += count
            status = f["deployment_status"] or "non déployé"
            lines.append(f"  • {f['name']} [{status}] — {count} soumission(s)")
        lines.append(f"\nTotal soumissions: {total}")
        return ToolResponse(content="\n".join(lines))
    except Exception as e:
        return ToolResponse(content=f"Erreur KoboCollect: {e}")


async def generer_formulaire_prix() -> ToolResponse:
    """Génère un formulaire XLSForm pour la collecte de prix sur les marchés.

    Returns:
        Structure du formulaire de collecte de prix.
    """
    try:
        form = generate_price_survey_xlsform()
        fields = [f"{r['name']} ({r['type']})" for r in form["survey"]]
        markets = [c["name"] for c in form["choices"]
                   if c["list_name"] == "market"]
        products = [c["name"] for c in form["choices"]
                    if c["list_name"] == "product"]
        lines = [
            "📝 Formulaire de collecte de prix généré:",
            f"   Champs ({len(form['survey'])}): {', '.join(fields)}",
            f"   Marchés: {', '.join(markets)}",
            f"   Produits: {', '.join(products)}",
            "\nPrêt à déployer sur KoboCollect.",
        ]
        return ToolResponse(content="\n".join(lines))
    except Exception as e:
        return ToolResponse(content=f"Erreur génération formulaire: {e}")


async def generer_formulaire_agriculteur() -> ToolResponse:
    """Génère un formulaire XLSForm pour le profilage des agriculteurs.

    Returns:
        Structure du formulaire de profilage agriculteur.
    """
    try:
        form = generate_farmer_survey_xlsform()
        fields = [f"{r['name']} ({r['type']})" for r in form["survey"]]
        regions = [c["name"] for c in form["choices"]
                   if c["list_name"] == "region"]
        lines = [
            "👨‍🌾 Formulaire de profilage agriculteur généré:",
            f"   Champs ({len(form['survey'])}): {', '.join(fields)}",
            f"   Régions: {', '.join(regions)}",
            "\nPrêt à déployer sur KoboCollect.",
        ]
        return ToolResponse(content="\n".join(lines))
    except Exception as e:
        return ToolResponse(content=f"Erreur génération formulaire: {e}")
