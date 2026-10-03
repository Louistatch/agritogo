"""Outils AgentScope pour les 5 modules ML."""

from agentscope.tool import ToolResponse
from app.ml.garch_volatility import run_garch_forecast
from app.ml.financial_risk import run_risk_assessment
from app.ml.farmer_segmentation import run_farmer_segmentation
from app.ml.kpi_dashboard import get_kpi_data
import json


async def predire_rendement_cultures(
    culture: str = "Maïs", region: str = "Kara", irrigation: str = "pluviale", sol: str = "limoneux"
) -> ToolResponse:
    """Rendement attendu d'une culture dans une région du Togo (méthode FAO-33).

    Part du rendement moyen national observé (sourcé) et le corrige selon la
    satisfaction des besoins en eau de la région (bilan FAO-56). Renvoie une
    fourchette, la source et les limites — à citer telles quelles.

    Args:
        culture: Maïs, Sorgho, Mil, Soja, Arachide, Niébé, Tomate, Oignon, Piment, Gombo
        region: Maritime, Plateaux, Centrale, Kara ou Savanes
        irrigation: « pluviale » ou un système d'irrigation
        sol: sableux, sableux-limoneux, limoneux, argilo-limoneux, argileux

    Returns:
        Rendement attendu (t/ha) année normale / sèche, fourchette, sources, limites.
    """
    from app.agrismart.yield_estimate import estimate

    r = estimate(culture, region=region, soil_type=sol, irrigation=irrigation)
    if not r.get("ok"):
        return ToolResponse(content=f"Estimation impossible : {r.get('reason')}")
    y, m = r["yield_t_ha"], r["method"]
    lines = [
        f"🌾 {r['crop']} — {r['region'] or 'GPS'} ({'irrigué' if r['irrigated'] else 'pluvial'}, semis {r['planting_month']})",
        f"Rendement attendu : {y['annee_normale']} t/ha (année normale), {y['annee_seche']} t/ha (année sèche)",
        f"Fourchette : {y['fourchette'][0]} – {y['fourchette'][1]} t/ha",
        f"Référence : {m['yref_t_ha']} t/ha ({m['yref_status']}) — {m['yref_source']}",
        f"Méthode : FAO-33, Ky = {m['ky']} ({m['ky_source']})",
        "Limites : " + " ; ".join(m["limits"]),
    ]
    return ToolResponse(content="\n".join(lines))


async def prevoir_volatilite(produit: str = "Maïs", jours: int = 30) -> ToolResponse:
    """Prévision de volatilité GARCH pour un produit agricole.

    Args:
        produit: Nom du produit (Maïs, Riz, Sorgho, Mil, Igname, etc.)
        jours: Nombre de jours de prévision (défaut: 30)

    Returns:
        Prévision de volatilité et paramètres du modèle GARCH.
    """
    result = run_garch_forecast(product=produit, periods=jours)
    if result.get("error"):
        return ToolResponse(content=result["error"])
    lines = [f"📈 {result['summary']}", ""]
    lines.append(f"Dernier prix: {result['last_price_fcfa']} FCFA/kg")
    stats = result["historical_volatility_stats"]
    lines.append(f"Volatilité annualisée: {stats['current']:.2%}")
    lines.append(f"\nPrévision par semaine ({len(result['forecast_30d'])} semaines):")
    for f in result["forecast_30d"][:5]:
        lines.append(f"  {f['date']}: vol={f['predicted_volatility']:.4f} "
                     f"[{f['price_lower']}-{f['price_upper']} FCFA]")
    return ToolResponse(content="\n".join(lines))


async def evaluer_risque_financier() -> ToolResponse:
    """Évalue le risque financier des prêts agricoles au Togo.

    Returns:
        Métriques du modèle, distribution des risques et features importantes.
    """
    result = run_risk_assessment()
    m = result["metrics"]
    lines = [f"⚠️ {result['summary']}", ""]
    lines.append(f"Accuracy: {m['accuracy']} | Precision: {m['precision']}")
    lines.append(f"Recall: {m['recall']} | F1: {m['f1']}")
    lines.append(f"\nDistribution des risques:")
    for level, count in result["risk_distribution"].items():
        lines.append(f"  {level}: {count} agriculteurs")
    lines.append(f"\nFacteurs de risque principaux:")
    for f in result["feature_importance"][:5]:
        lines.append(f"  {f['feature']}: {f['score']}")
    return ToolResponse(content="\n".join(lines))


async def segmenter_agriculteurs(n_groupes: int = 4) -> ToolResponse:
    """Segmente les agriculteurs togolais par K-Means + PCA.

    Args:
        n_groupes: Nombre de segments (défaut: 4)

    Returns:
        Description des segments et statistiques.
    """
    result = run_farmer_segmentation(n_clusters=n_groupes)
    lines = [f"👥 {result['summary']}", ""]
    for profile in result["cluster_profiles"]:
        lines.append(
            f"  {profile['name']}: {profile['count']} agriculteurs "
            f"({profile['pct']}%) — Région: {profile['top_region']} "
            f"— Revenu moy: {profile['avg_revenue_fcfa']:,} FCFA"
        )
    lines.append(f"\nVariance expliquée PCA: {result['explained_variance']}")
    return ToolResponse(content="\n".join(lines))


async def obtenir_kpi_agriculture() -> ToolResponse:
    """Obtient les KPIs agricoles du Togo: rendements, coûts, risques.

    Returns:
        Tableau de bord complet des indicateurs agricoles.
    """
    result = get_kpi_data()
    ns = result["national_summary"]
    lines = [f"📊 Dashboard Agricole Togo", ""]
    lines.append(f"Surface cultivée: {ns['total_cultivated_ha']:,} ha")
    lines.append(f"Rendement moyen national: {ns['avg_national_yield']} kg/ha")
    lines.append(f"Coût total intrants/ha: {ns['total_input_cost_ha']:,} FCFA")
    lines.append(f"\nTop 5 cultures par ROI:")
    for c in result["top_performers"]:
        lines.append(f"  {c['crop']}: ROI {c['roi_percent']}% "
                     f"(profit {c['profit_fcfa_ha']:,} FCFA/ha)")
    return ToolResponse(content="\n".join(lines))


async def consulter_meteo_region(region: str = "Centrale") -> ToolResponse:
    """Consulte les données météo réelles d'une région du Togo.

    Sources: NASA POWER (historique) + Open-Meteo (prévisions).
    Données: température, précipitations, humidité, radiation solaire, vent.

    Args:
        region: Nom de la région (Maritime, Plateaux, Centrale, Kara, Savanes)

    Returns:
        Conditions météo actuelles et tendances sur les 30 derniers jours.
    """
    from app.climate import TOGO_REGION_COORDS, get_climate_for_location
    coords = TOGO_REGION_COORDS.get(region, TOGO_REGION_COORDS["Centrale"])
    data = get_climate_for_location(coords["lat"], coords["lon"], days=30)

    lines = [f"🌦️ Météo {region} (derniers 30 jours)", ""]
    lines.append(f"Source: {data.get('source', 'inconnu')}")
    lines.append(f"Température moyenne: {data.get('avg_temp', '?')}°C")
    if data.get('temp_max'):
        lines.append(f"Température max: {data['temp_max']}°C | min: {data['temp_min']}°C")
    lines.append(f"Précipitations totales: {data.get('total_rainfall_mm', '?')} mm")
    lines.append(f"Pluie moyenne/jour: {data.get('avg_daily_rain_mm', '?')} mm")
    lines.append(f"Jours secs: {data.get('dry_days', '?')}")
    lines.append(f"Indice sécheresse: {data.get('drought_index', '?')}")
    if data.get('avg_humidity'):
        lines.append(f"Humidité moyenne: {data['avg_humidity']}%")
    lines.append(f"Points de données: {data.get('data_points', 0)}")
    return ToolResponse(content="\n".join(lines))


async def rafraichir_donnees_climat() -> ToolResponse:
    """Rafraîchit les données climatiques pour toutes les régions du Togo.

    Appelle NASA POWER (historique 90j) + Open-Meteo (prévisions 16j).
    Les données sont stockées dans Supabase pour les modèles ML.

    Returns:
        Nombre d'enregistrements mis à jour.
    """
    from app.climate import refresh_climate_data
    total = refresh_climate_data(days_back=90)
    return ToolResponse(content=f"✅ Données climatiques rafraîchies: {total} enregistrements stockés dans Supabase.\n"
                                f"Sources: NASA POWER (90 jours historiques) + Open-Meteo (16 jours prévisions).\n"
                                f"Régions: Maritime, Plateaux, Centrale, Kara, Savanes.")
