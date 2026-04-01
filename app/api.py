# B2B REST API for AgriTogo Decision Intelligence Engine

from flask import Blueprint, jsonify, request

from app.database import get_prix_historiques, get_produits, get_marches, get_db_stats
from app.ml.garch_volatility import run_garch_forecast
from app.ml.financial_risk import run_risk_assessment
from app.ml.farmer_segmentation import run_farmer_segmentation
from app.ml.kpi_dashboard import get_kpi_data

api_bp = Blueprint("api_bp", __name__, url_prefix="/api/v1")


@api_bp.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "version": "2.0",
        "agents": 6,
        "models": ["gemini", "qwen", "claude"],
    })


@api_bp.route("/prix/<produit>")
def prix(produit):
    marche = request.args.get("marche")
    # Normalize product name — handle accent variants
    from app.database import get_produits
    all_prods = {p['nom'].lower().replace('ï','i').replace('é','e').replace('è','e'): p['nom']
                 for p in get_produits()}
    normalized = produit.lower().replace('ï','i').replace('é','e').replace('è','e')
    real_name = all_prods.get(normalized, produit)
    data = get_prix_historiques(real_name, marche, 60)
    # Aggregate by date (average across markets) if no specific market
    if not marche and data:
        import pandas as pd
        df = pd.DataFrame(data)
        agg = df.groupby('date')['prix'].mean().round(0).reset_index()
        agg['marche'] = 'Moyenne'
        agg['produit'] = real_name
        data = agg.to_dict(orient='records')
    return jsonify(data)


@api_bp.route("/produits")
def produits():
    return jsonify(get_produits())


@api_bp.route("/marches")
def marches():
    return jsonify(get_marches())


@api_bp.route("/forecast", methods=["POST"])
def forecast():
    body = request.get_json(force=True)
    produit = body.get("produit", "Maïs")
    periods = body.get("periods", 30)
    result = run_garch_forecast(product=produit, periods=periods)
    return jsonify(result)


@api_bp.route("/risk", methods=["POST"])
def risk():
    result = run_risk_assessment()
    return jsonify(result)


@api_bp.route("/segmentation", methods=["POST"])
def segmentation():
    body = request.get_json(silent=True) or {}
    n_clusters = body.get("n_clusters", 4)
    result = run_farmer_segmentation(n_clusters=n_clusters)
    if isinstance(result, dict):
        result.pop("pca_components", None)
    return jsonify(result)


@api_bp.route("/kpi")
def kpi():
    return jsonify(get_kpi_data())


@api_bp.route("/stats")
def stats():
    return jsonify(get_db_stats())
