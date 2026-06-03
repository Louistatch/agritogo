"""Togo Data Adapter — uses REAL climate data from Supabase when available.

Falls back to hardcoded values only if no climate data has been fetched yet.
Real data comes from NASA POWER + Open-Meteo via app.climate module.
"""
import logging
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Togo Regions — STATIC fallback (used only when Supabase has no data) ──
REGIONS = ["Maritime", "Plateaux", "Centrale", "Kara", "Savanes"]

TOGO_REGIONS = {
    "Maritime":  {"avg_temp": 27.5, "rainfall_mm": 1200, "climate_risk": 35, "drought_prob": 0.12, "flood_prob": 0.28, "main_crops": ["Mais","Manioc","Tomate","Piment"], "soil_health": 72, "irrigation_pct": 18},
    "Plateaux":  {"avg_temp": 26.8, "rainfall_mm": 1100, "climate_risk": 30, "drought_prob": 0.10, "flood_prob": 0.22, "main_crops": ["Mais","Igname","Manioc","Soja"], "soil_health": 78, "irrigation_pct": 14},
    "Centrale":  {"avg_temp": 28.2, "rainfall_mm": 950,  "climate_risk": 48, "drought_prob": 0.22, "flood_prob": 0.15, "main_crops": ["Mais","Sorgho","Igname","Arachide"], "soil_health": 65, "irrigation_pct": 10},
    "Kara":      {"avg_temp": 29.1, "rainfall_mm": 1050, "climate_risk": 55, "drought_prob": 0.28, "flood_prob": 0.12, "main_crops": ["Mais","Sorgho","Mil","Soja"], "soil_health": 60, "irrigation_pct": 8},
    "Savanes":   {"avg_temp": 31.5, "rainfall_mm": 750,  "climate_risk": 72, "drought_prob": 0.45, "flood_prob": 0.08, "main_crops": ["Sorgho","Mil","Arachide","Mais"], "soil_health": 48, "irrigation_pct": 5},
}

TOGO_YIELDS = {
    "Mais":     {"min": 8000,  "max": 45000,  "mean": 18000},
    "Riz":      {"min": 15000, "max": 60000,  "mean": 32000},
    "Sorgho":   {"min": 5000,  "max": 25000,  "mean": 12000},
    "Mil":      {"min": 4000,  "max": 20000,  "mean": 10000},
    "Igname":   {"min": 40000, "max": 120000, "mean": 70000},
    "Manioc":   {"min": 50000, "max": 150000, "mean": 85000},
    "Soja":     {"min": 8000,  "max": 30000,  "mean": 15000},
    "Arachide": {"min": 6000,  "max": 25000,  "mean": 12000},
}

TOGO_PRICES = {
    "Mais": 220, "Riz local": 450, "Sorgho": 200, "Mil": 250,
    "Haricot": 500, "Soja": 350, "Arachide": 400, "Igname": 300,
    "Manioc": 150, "Tomate": 600, "Piment": 800, "Oignon": 350,
}


def get_region_profile(region: str, use_real: bool = True) -> dict:
    """Get climate profile for a region — real data from Supabase if available."""
    static = TOGO_REGIONS.get(region, TOGO_REGIONS["Centrale"]).copy()

    if not use_real:
        return static

    try:
        from app.climate import get_climate_for_location, TOGO_REGION_COORDS
        coords = TOGO_REGION_COORDS.get(region)
        if coords:
            real = get_climate_for_location(coords["lat"], coords["lon"], days=90)
            if real.get("data_points", 0) > 5:
                static["avg_temp"] = real["avg_temp"]
                static["rainfall_mm"] = real["total_rainfall_mm"]
                static["drought_prob"] = real["drought_index"]
                static["_source"] = real["source"]
                static["_data_points"] = real["data_points"]
                log.info(f"Region {region}: using REAL climate ({real['data_points']} points)")
            else:
                static["_source"] = "hardcoded_fallback"
                log.warning(f"Region {region}: not enough real data ({real.get('data_points', 0)}), using hardcoded")
    except Exception as e:
        static["_source"] = "hardcoded_fallback"
        log.warning(f"Region {region}: climate fetch failed ({e}), using hardcoded")

    return static


def get_parcelle_climate(lat: float, lon: float, days: int = 30) -> dict:
    """Get climate data for a specific parcelle GPS — real data."""
    try:
        from app.climate import get_climate_for_location
        return get_climate_for_location(lat, lon, days)
    except Exception as e:
        log.warning(f"Parcelle climate failed for ({lat},{lon}): {e}")
        region = _guess_region(lat)
        static = TOGO_REGIONS.get(region, TOGO_REGIONS["Centrale"])
        return {
            "source": "hardcoded_fallback",
            "avg_temp": static["avg_temp"],
            "total_rainfall_mm": static["rainfall_mm"],
            "drought_index": static["drought_prob"],
            "data_points": 0,
            "region": region,
        }


def _guess_region(lat: float) -> str:
    """Rough region assignment based on latitude."""
    if lat < 6.5: return "Maritime"
    if lat < 7.5: return "Plateaux"
    if lat < 9.0: return "Centrale"
    if lat < 10.0: return "Kara"
    return "Savanes"


def get_togo_crop_yield(crop: str, region: str) -> dict:
    """Get expected yield range for a crop in a Togo region."""
    base = TOGO_YIELDS.get(crop, TOGO_YIELDS["Mais"])
    profile = get_region_profile(region)
    factor = profile["rainfall_mm"] / 1000 * max(0.5, 1 - abs(profile["avg_temp"] - 27) * 0.03)
    return {
        "min": round(base["min"] * factor),
        "max": round(base["max"] * factor),
        "expected": round(base["mean"] * factor),
    }


def adapt_to_togo(df, region_col=None, n_per_region=None, seed=42):
    """Remap any dataset to Togo's 5 regions with REAL climate parameters."""
    np.random.seed(seed)
    df = df.copy()
    if region_col and region_col in df.columns:
        unique_regions = df[region_col].unique()
        mapping = {r: REGIONS[i % len(REGIONS)] for i, r in enumerate(sorted(unique_regions))}
        df["region"] = df[region_col].map(mapping)
    else:
        df["region"] = np.random.choice(REGIONS, len(df))

    for col, param in [("avg_temp", "avg_temp"), ("Average_Temperature_C", "avg_temp"),
                        ("average_rain_fall_mm_per_year", "rainfall_mm"), ("Soil_Health_Index", "soil_health")]:
        if col in df.columns:
            df[col] = df["region"].map(lambda r: get_region_profile(r).get(param, 28) + np.random.normal(0, 1.5))
    return df
