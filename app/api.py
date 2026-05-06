# B2B REST API for AgriTogo Decision Intelligence Engine

from flask import Blueprint, jsonify, request

from app.database import get_prix_historiques, get_produits, get_marches, get_db_stats

api_bp = Blueprint("api_bp", __name__, url_prefix="/api/v1")


def _safe(fn, *args, **kwargs):
    """Wrap ML calls — return error JSON instead of 500."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}


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
    try:
        marche = request.args.get("marche")
        all_prods = {p['nom'].lower().replace('ï', 'i').replace('é', 'e').replace('è', 'e'): p['nom']
                     for p in get_produits()}
        normalized = produit.lower().replace('ï', 'i').replace('é', 'e').replace('è', 'e')
        real_name = all_prods.get(normalized, produit)
        data = get_prix_historiques(real_name, marche, 60)
        if not marche and data:
            import pandas as pd
            df = pd.DataFrame(data)
            agg = df.groupby('date')['prix'].mean().round(0).reset_index()
            agg['marche'] = 'Moyenne'
            agg['produit'] = real_name
            data = agg.to_dict(orient='records')
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/produits")
def produits():
    return jsonify(get_produits())


@api_bp.route("/marches")
def marches():
    return jsonify(get_marches())


@api_bp.route("/forecast", methods=["POST"])
def forecast():
    try:
        from app.ml.garch_volatility import run_garch_forecast
        body = request.get_json(force=True, silent=True) or {}
        produit = body.get("produit", "Maïs")
        periods = int(body.get("periods", 30))
        result = _safe(run_garch_forecast, product=produit, periods=periods)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/risk", methods=["POST"])
def risk():
    try:
        from app.ml.financial_risk import run_risk_assessment
        result = _safe(run_risk_assessment)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/segmentation", methods=["POST"])
def segmentation():
    try:
        from app.ml.farmer_segmentation import run_farmer_segmentation
        body = request.get_json(silent=True) or {}
        n_clusters = int(body.get("n_clusters", 4))
        result = _safe(run_farmer_segmentation, n_clusters=n_clusters)
        if isinstance(result, dict):
            result.pop("pca_components", None)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/kpi")
def kpi():
    try:
        from app.ml.kpi_dashboard import get_kpi_data
        return jsonify(_safe(get_kpi_data))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/stats")
def stats():
    return jsonify(get_db_stats())
