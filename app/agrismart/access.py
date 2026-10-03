"""Réponse AgriSmart réduite au bilan global (détail réservé, voir api.py)."""


def summary_only(payload: dict) -> dict:
    """Bilan global seul : totaux et débit de pompe, sans le détail."""
    out = dict(payload)
    out["results"] = [
        {
            "crop": r["crop"],
            "area_m2": r["area_m2"],
            "planting_month": r.get("planting_month"),
            "monthly": [],
            "kpis": {k: r["kpis"][k] for k in ("total_m3", "total_boost_m3", "total_optimal_m3")},
        }
        for r in payload.get("results", [])
    ]
    out["combined_monthly"] = []
    out["details_locked"] = True
    return out
