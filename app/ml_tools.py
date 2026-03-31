"""Outils AgentScope pour les 5 modules ML."""

from agentscope.tool import ToolResponse
from app.ml.crop_yield import run_crop_yield_prediction
from app.ml.garch_volatility import run_garch_forecast
from app.ml.financial_risk import run_risk_assessment
from app.ml.farmer_segmentation import run_farmer_segmentation
from app.ml.kpi_dashboard import get_kpi_data
import json


async def predire_rendement_cultures() -> ToolResponse:
    """Lance la prédiction de rendement agricole avec Random Forest et XGBoost.
    Analyse l'impact du climat sur les cultures au Togo.

    Returns:
        Résultats du modèle avec métriques et feature importance.
    """
    result = run_crop_yield_prediction()
    lines = [f"🌾 {result['summary']}", ""]
    lines.append("Métriques:")
    for model, m in result["metrics"].items():
        lines.append(f"  {model}: R²={m.get('r2')} | RMSE={m.get('rmse')}")
    lines.append("\nFeatures les plus importantes:")
    for f in result["feature_importance"]:
        lines.append(f"  {f['feature']}: {f['score']}")
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
    lines = [f"📈 {result['summary']}", ""]
    lines.append(f"Dernier prix: {result['last_price_fcfa']} FCFA/kg")
    stats = result["historical_volatility_stats"]
    lines.append(f"Volatilité annualisée: {stats['current']:.2%}")
    lines.append(f"\nPrévision {jours} jours (5 premiers):")
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
    for key, desc in result["cluster_descriptions"].items():
        lines.append(f"  {key}: {desc}")
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
