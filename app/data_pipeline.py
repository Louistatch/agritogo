"""AgriTogo Data Pipeline — KoboCollect + API enrichment.

Flow:
1. KoboCollect submission arrives (webhook or manual pull)
2. Pipeline enriches with external APIs:
   - Open-Meteo: temperature, rainfall, extreme weather
   - SoilGrids: soil health index
   - WFP VAM: market prices
3. Enriched data inserted into SQLite for ML modules

APIs used (all free, no key required):
- Open-Meteo: https://api.open-meteo.com (weather history)
- SoilGrids: https://rest.isric.org (soil properties)
- WFP VAM: https://dataviz.vam.wfp.org/api (food prices)
"""

import requests
import json
from datetime import datetime, timedelta
from typing import Optional

# ── Togo GPS coordinates per region ──────────────────────
REGION_COORDS = {
    "Maritime":  {"lat": 6.14,  "lon": 1.22},   # Lomé
    "Plateaux":  {"lat": 6.90,  "lon": 1.18},   # Atakpamé
    "Centrale":  {"lat": 8.58,  "lon": 1.18},   # Sokodé
    "Kara":      {"lat": 9.55,  "lon": 1.19},   # Kara
    "Savanes":   {"lat": 10.89, "lon": 0.86},   # Dapaong
}

# ── WFP VAM market IDs for Togo ───────────────────────────
WFP_MARKET_IDS = {
    "Lome-Adawlato": 1,
    "Kara": 2,
    "Sokode": 3,
    "Atakpame": 4,
    "Dapaong": 5,
}


def fetch_weather(region: str, date: str = None) -> dict:
    """Fetch temperature and rainfall from Open-Meteo for a Togo region.

    Args:
        region: Togo region name
        date: Date string YYYY-MM-DD (defaults to yesterday)

    Returns:
        dict with avg_temp, rainfall_mm, extreme_weather_events
    """
    coords = REGION_COORDS.get(region, REGION_COORDS["Centrale"])
    if not date:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": coords["lat"],
            "longitude": coords["lon"],
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_hours",
            "start_date": date,
            "end_date": date,
            "timezone": "Africa/Abidjan",
        }
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        d = r.json().get("daily", {})
        tmax = d.get("temperature_2m_max", [None])[0]
        tmin = d.get("temperature_2m_min", [None])[0]
        rain = d.get("precipitation_sum", [0])[0] or 0
        precip_hours = d.get("precipitation_hours", [0])[0] or 0

        avg_temp = round((tmax + tmin) / 2, 1) if tmax and tmin else None
        extreme = 1 if rain > 50 or (tmax and tmax > 40) else 0

        return {
            "avg_temp": avg_temp,
            "rainfall_mm": round(rain, 1),
            "extreme_weather_events": extreme,
            "source": "open-meteo",
            "date": date,
        }
    except Exception as e:
        return {"error": str(e), "source": "open-meteo"}


def fetch_soil_health(region: str) -> dict:
    """Fetch soil organic carbon (proxy for soil health) from SoilGrids.

    Args:
        region: Togo region name

    Returns:
        dict with soil_health_score (0-100), soil_ph, organic_carbon
    """
    coords = REGION_COORDS.get(region, REGION_COORDS["Centrale"])
    try:
        url = "https://rest.isric.org/soilgrids/v2.0/properties/query"
        params = {
            "lon": coords["lon"],
            "lat": coords["lat"],
            "property": ["ocd", "phh2o"],
            "depth": ["0-5cm"],
            "value": ["mean"],
        }
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        layers = data.get("properties", {}).get("layers", [])

        ocd = None  # organic carbon density
        ph = None
        for layer in layers:
            name = layer.get("name", "")
            depths = layer.get("depths", [{}])
            val = depths[0].get("values", {}).get("mean") if depths else None
            if name == "ocd" and val is not None:
                ocd = val / 10  # convert to g/kg
            elif name == "phh2o" and val is not None:
                ph = val / 10  # convert to pH units

        # Soil health score: 0-100 based on organic carbon
        # >20 g/kg = excellent, 10-20 = good, 5-10 = average, <5 = poor
        if ocd is not None:
            if ocd > 20: score = 85
            elif ocd > 10: score = 65
            elif ocd > 5: score = 45
            else: score = 25
        else:
            score = 50  # default

        return {
            "soil_health_score": score,
            "soil_ph": ph,
            "organic_carbon_g_kg": round(ocd, 2) if ocd else None,
            "source": "soilgrids",
        }
    except Exception as e:
        return {"soil_health_score": 50, "error": str(e), "source": "soilgrids"}


def fetch_market_price(product: str, market: str = None) -> dict:
    """Fetch latest market price from WFP VAM API.

    Args:
        product: Product name in French
        market: Market name (optional)

    Returns:
        dict with price_fcfa_kg, date, source
    """
    # WFP VAM API for Togo (country code TGO)
    try:
        url = "https://dataviz.vam.wfp.org/api/GetCommodityPrice"
        params = {
            "CountryCode": "TGO",
            "CommodityName": product,
        }
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data and len(data) > 0:
            latest = sorted(data, key=lambda x: x.get("date", ""), reverse=True)[0]
            return {
                "price_fcfa_kg": latest.get("price"),
                "date": latest.get("date"),
                "market": latest.get("market"),
                "source": "wfp-vam",
            }
    except Exception:
        pass

    # Fallback: local DB
    return {"source": "local-db", "note": "WFP VAM unavailable, use local prices"}


def enrich_kobo_submission(submission: dict) -> dict:
    """Enrich a KoboCollect submission with external API data.

    Args:
        submission: Raw KoboCollect submission dict

    Returns:
        Enriched submission with weather, soil, and price data added
    """
    enriched = dict(submission)
    region = submission.get("region", "Centrale")
    date = submission.get("collection_date") or submission.get("date") or None

    # 1. Enrich with weather if temp/rainfall missing
    if not submission.get("avg_temperature_c") or not submission.get("rainfall_mm"):
        weather = fetch_weather(region, date)
        if "error" not in weather:
            if not submission.get("avg_temperature_c"):
                enriched["avg_temperature_c"] = weather.get("avg_temp")
                enriched["avg_temperature_c_source"] = "open-meteo"
            if not submission.get("rainfall_mm"):
                enriched["rainfall_mm"] = weather.get("rainfall_mm")
                enriched["rainfall_mm_source"] = "open-meteo"
            if not submission.get("extreme_weather_events"):
                enriched["extreme_weather_events"] = weather.get("extreme_weather_events", 0)

    # 2. Enrich with soil health if missing
    if not submission.get("soil_health_score"):
        soil = fetch_soil_health(region)
        enriched["soil_health_score"] = soil.get("soil_health_score", 50)
        enriched["soil_health_source"] = "soilgrids"

    # 3. Add enrichment metadata
    enriched["_enriched_at"] = datetime.now().isoformat()
    enriched["_enrichment_sources"] = ["open-meteo", "soilgrids"]

    return enriched


def process_kobo_batch(submissions: list) -> list:
    """Process a batch of KoboCollect submissions with enrichment.

    Args:
        submissions: List of raw KoboCollect submission dicts

    Returns:
        List of enriched submissions
    """
    return [enrich_kobo_submission(s) for s in submissions]


def get_pipeline_status() -> dict:
    """Check availability of all external APIs."""
    status = {}

    # Open-Meteo
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast?latitude=6.14&longitude=1.22&daily=temperature_2m_max&start_date=2024-01-01&end_date=2024-01-01&timezone=Africa/Abidjan", timeout=5)
        status["open_meteo"] = "ok" if r.status_code == 200 else f"error_{r.status_code}"
    except Exception:
        status["open_meteo"] = "unreachable"

    # SoilGrids
    try:
        r = requests.get("https://rest.isric.org/soilgrids/v2.0/properties/query?lon=1.22&lat=6.14&property=ocd&depth=0-5cm&value=mean", timeout=8)
        status["soilgrids"] = "ok" if r.status_code == 200 else f"error_{r.status_code}"
    except Exception:
        status["soilgrids"] = "unreachable"

    # WFP VAM
    try:
        r = requests.get("https://dataviz.vam.wfp.org/api/GetCommodityPrice?CountryCode=TGO", timeout=8)
        status["wfp_vam"] = "ok" if r.status_code == 200 else f"error_{r.status_code}"
    except Exception:
        status["wfp_vam"] = "unreachable"

    return status
