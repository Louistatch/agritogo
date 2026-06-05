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


# ─── AgriSmart — Irrigation Expert System ────────────────────────────

@api_bp.route("/agrismart/crops")
def agrismart_crops():
    """Liste des cultures avec Kc mensuel et profondeur racinaire."""
    from app.agrismart.kc_values import KC_VALUES, MOIS, IRRIGATION_SYSTEMS
    crops = [
        {
            "id": name.lower().replace("è", "e").replace("â", "a"),
            "name": name,
            "emoji": data["emoji"],
            "kc": data["kc"],
            "z": data["z"],
            "mois": MOIS,
        }
        for name, data in KC_VALUES.items()
    ]
    systems = [
        {"id": k, "label": k, "efficiency": v["efficiency"], "emoji": v["emoji"]}
        for k, v in IRRIGATION_SYSTEMS.items()
    ]
    return jsonify({"crops": crops, "irrigation_systems": systems, "mois": MOIS})


@api_bp.route("/agrismart/soil-types")
def agrismart_soil_types():
    """5 types de sol avec propriétés hydrauliques ROSETTA v3."""
    from app.agrismart.soil import SOIL_PROFILES
    types = [
        {
            "id": k.lower().replace(" ", "_").replace("-", "_"),
            "name": k,
            "emoji": v["emoji"],
            "desc": v["desc"],
            "RU": v["RU"],
            "RFU": v["RFU"],
            "fc_pct": v["fc_pct"],
            "wp_pct": v["wp_pct"],
            "clay_pct": v["clay_pct"],
            "sand_pct": v["sand_pct"],
            "silt_pct": v["silt_pct"],
        }
        for k, v in SOIL_PROFILES.items()
    ]
    return jsonify({"soil_types": types})


@api_bp.route("/agrismart/calculate", methods=["POST"])
def agrismart_calculate():
    """
    Calcul complet des besoins en irrigation FAO-56 — multi-culture.

    Body JSON:
      crops       : list[{name: str, area_m2: float}]  — cultures + surfaces en m²
      soil_type   : str   — texture du sol (partagée par toutes les cultures)
      system      : str   — système d'irrigation
      lat         : float (optionnel) — GPS → NASA POWER climatologie exacte
      lon         : float (optionnel)
      region      : str   (optionnel) — région Togo fallback

    Retourne :
      results[]   : par culture → monthly (12 mois) + kpis + boost rendement
      combined    : totaux agrégés toutes cultures confondues
    """
    try:
        from app.agrismart.kc_values import KC_VALUES, IRRIGATION_SYSTEMS
        from app.agrismart.soil import SOIL_PROFILES
        from app.agrismart.climate_normals import get_nasa_climatology, get_region_climatology
        from app.agrismart.irrigation import compute_monthly_needs, compute_kpis

        body = request.get_json(force=True, silent=True) or {}

        crops_input = body.get("crops", [{"name": "Tomate", "area_m2": 1000}])
        soil_name   = body.get("soil_type", "Limoneux")
        system_name = body.get("system", "Goutte à goutte")
        lat         = body.get("lat")
        lon         = body.get("lon")
        region      = body.get("region")

        # Validations
        if soil_name not in SOIL_PROFILES:
            return jsonify({"error": f"Sol inconnu: {soil_name}"}), 400
        if system_name not in IRRIGATION_SYSTEMS:
            return jsonify({"error": f"Système inconnu: {system_name}"}), 400
        for c in crops_input:
            if c["name"] not in KC_VALUES:
                return jsonify({"error": f"Culture inconnue: {c['name']}"}), 400

        # Données climatiques (une seule requête pour toutes les cultures)
        if lat is not None and lon is not None:
            climate = get_nasa_climatology(float(lat), float(lon))
        elif region:
            climate = get_region_climatology(region)
        else:
            climate = get_region_climatology("Centrale")

        soil_ru = SOIL_PROFILES[soil_name]["RU"]

        # Calcul par culture
        results = []
        for c in crops_input:
            crop_name = c["name"]
            area_m2   = max(float(c.get("area_m2", 1000)), 1.0)
            monthly   = compute_monthly_needs(crop_name, area_m2, soil_ru, system_name, climate)
            kpis      = compute_kpis(monthly, area_m2, system_name, crop_name)
            results.append({
                "crop":    crop_name,
                "area_m2": area_m2,
                "monthly": monthly,
                "kpis":    kpis,
            })

        # Agrégation combinée (12 mois, toutes cultures)
        from app.agrismart.kc_values import MOIS
        combined_monthly = []
        for i, mois in enumerate(MOIS):
            vol_total     = sum(r["monthly"][i]["volume_total"]    for r in results)
            boost_total   = sum(r["monthly"][i]["boost_vol_total"] for r in results)
            combined_monthly.append({
                "mois":            mois,
                "volume_total":    round(vol_total, 2),
                "boost_vol_total": round(boost_total, 2),
                "optimal_total":   round(vol_total + boost_total, 2),
            })

        total_area_m2    = sum(c.get("area_m2", 1000) for c in crops_input)
        total_survival   = sum(r["kpis"]["total_m3"]        for r in results)
        total_boost      = sum(r["kpis"]["total_boost_m3"]  for r in results)
        total_optimal    = sum(r["kpis"]["total_optimal_m3"] for r in results)
        pic_m            = max(combined_monthly, key=lambda m: m["optimal_total"])
        debit_pompe      = (pic_m["optimal_total"] / 30 / 12) * 0.277

        return jsonify({
            "soil":             soil_name,
            "system":           system_name,
            "climate_source":   climate["source"],
            "avg_temp":         climate.get("avg_temp"),
            "total_precip":     climate.get("total_precip"),
            "results":          results,
            "combined_monthly": combined_monthly,
            "combined_kpis": {
                "total_area_m2":      total_area_m2,
                "total_survival_m3":  round(total_survival, 1),
                "total_boost_m3":     round(total_boost, 1),
                "total_optimal_m3":   round(total_optimal, 1),
                "pic_mois":           pic_m["mois"],
                "pic_optimal_m3":     round(pic_m["optimal_total"], 1),
                "debit_pompe_ls":     round(debit_pompe, 3),
            },
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─── Agent Chat Endpoint (multi-agent Decision Intelligence Engine) ────

@api_bp.route("/agent/chat", methods=["POST"])
def agent_chat():
    """Full multi-agent chat endpoint.

    POST /api/v1/agent/chat
    Body: {"message": str, "card_number": str (optional), "audience": str (optional)}

    Uses the Decision Intelligence Engine with:
    - Intelligent routing (market_intel / quant_forecast / risk / decision)
    - Multi-model debate for high-stakes decisions
    - 14 tools (market data, ML models, KoboCollect)
    - UX reformulation for the target audience
    """
    import asyncio
    from app.agents.engine import process_query, _AGENTSCOPE_AVAILABLE

    body = request.get_json(force=True, silent=True) or {}
    message = (body.get("message") or "").strip()
    card_number = (body.get("card_number") or "").strip()
    audience = body.get("audience", "farmer")

    if not message:
        return jsonify({"error": "message requis"}), 400

    if not _AGENTSCOPE_AVAILABLE:
        return jsonify({
            "error": "Le moteur multi-agent n'est pas disponible (agentscope non installé).",
            "agentscope_available": False,
        }), 503

    try:
        # Enrich the question with producer context if card_number provided
        enriched = message
        if card_number:
            try:
                from app.database import get_prix_historiques, get_latest_prices
                # Add local context
                latest = get_latest_prices()
                if latest:
                    price_ctx = "; ".join(
                        f"{p.get('nom', p.get('produit', '?'))}={p.get('prix', 0)}FCFA à {p.get('marche', '?')}"
                        for p in latest[:8]
                    )
                    enriched = (
                        f"[Carte: {card_number}] "
                        f"[Prix récents: {price_ctx}] "
                        f"{message}"
                    )
            except Exception as ctx_err:
                import logging
                logging.warning(f"[agent_chat] Price context failed: {ctx_err}")
                enriched = f"[Carte: {card_number}] {message}"

        # Run the multi-agent engine
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(process_query(enriched, audience))
        finally:
            loop.close()

        # Save conversation
        if card_number:
            from app.database import save_conversation
            save_conversation("user", message, card_number)
            save_conversation("assistant", result.get("formatted_response", ""), card_number)

        return jsonify({
            "response": result.get("formatted_response", ""),
            "agent_type": result.get("agent_type"),
            "model_used": result.get("model_used"),
            "debate_used": result.get("debate_used", False),
            "agentscope_available": True,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "type": type(e).__name__,
            "agentscope_available": _AGENTSCOPE_AVAILABLE,
        }), 500
