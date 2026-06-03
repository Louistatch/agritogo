"""Climate data integration — NASA POWER (historical) + Open-Meteo (forecast).

Fetches real climate data for Togo's agricultural regions and stores it in
Supabase. Replaces the hardcoded values in togo_adapter.py.

APIs used (both FREE, no API key):
  - NASA POWER: https://power.larc.nasa.gov/api/
  - Open-Meteo: https://open-meteo.com/en/docs

Usage:
  from app.climate import refresh_climate_data, get_climate_for_location
  refresh_climate_data()  # fetch + store for all Togo regions
  data = get_climate_for_location(6.13, 1.22, days=30)  # for a specific GPS
"""

import logging
import requests
from datetime import datetime, timedelta, date
from typing import Optional

log = logging.getLogger(__name__)

# ── Togo reference points (center of each region) ────────
TOGO_REGION_COORDS = {
    "Maritime":  {"lat": 6.20, "lon": 1.20, "name": "Maritime (Lomé)"},
    "Plateaux":  {"lat": 7.00, "lon": 1.15, "name": "Plateaux (Atakpamé)"},
    "Centrale":  {"lat": 8.55, "lon": 1.10, "name": "Centrale (Sokodé)"},
    "Kara":      {"lat": 9.55, "lon": 1.18, "name": "Kara"},
    "Savanes":   {"lat": 10.65, "lon": 0.20, "name": "Savanes (Dapaong)"},
}


# ═══════════════════════════════════════════════════════════
# NASA POWER — Historical daily climate data
# ═══════════════════════════════════════════════════════════

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
NASA_PARAMS = "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,ALLSKY_SFC_SW_DWN,RH2M,WS2M"


def fetch_nasa_power(lat: float, lon: float, start: date, end: date) -> list[dict]:
    """Fetch daily climate data from NASA POWER for a GPS point."""
    try:
        resp = requests.get(NASA_POWER_URL, params={
            "parameters": NASA_PARAMS,
            "community": "AG",
            "longitude": round(lon, 4),
            "latitude": round(lat, 4),
            "start": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "format": "JSON",
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        params = data.get("properties", {}).get("parameter", {})

        if not params or "T2M" not in params:
            log.warning(f"NASA POWER returned no data for ({lat}, {lon})")
            return []

        dates = list(params["T2M"].keys())
        rows = []
        for d in dates:
            t2m = params["T2M"].get(d)
            if t2m is None or t2m == -999:
                continue
            rows.append({
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "date": f"{d[:4]}-{d[4:6]}-{d[6:8]}",
                "temperature_mean": round(params["T2M"].get(d, 0), 2),
                "temperature_max": round(params.get("T2M_MAX", {}).get(d, 0), 2),
                "temperature_min": round(params.get("T2M_MIN", {}).get(d, 0), 2),
                "precipitation_mm": round(max(0, params.get("PRECTOTCORR", {}).get(d, 0)), 2),
                "solar_radiation_mj": round(max(0, params.get("ALLSKY_SFC_SW_DWN", {}).get(d, 0)), 3),
                "humidity_pct": round(params.get("RH2M", {}).get(d, 0), 2),
                "wind_speed_ms": round(max(0, params.get("WS2M", {}).get(d, 0)), 2),
                "source": "nasa_power",
            })
        log.info(f"NASA POWER: {len(rows)} jours pour ({lat}, {lon})")
        return rows

    except Exception as e:
        log.error(f"NASA POWER error for ({lat}, {lon}): {e}")
        return []


# ═══════════════════════════════════════════════════════════
# Open-Meteo — Forecast + recent actuals
# ═══════════════════════════════════════════════════════════

OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_open_meteo(lat: float, lon: float, forecast_days: int = 16) -> list[dict]:
    """Fetch weather forecast + recent data from Open-Meteo."""
    try:
        resp = requests.get(OPENMETEO_URL, params={
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                     "et0_fao_evapotranspiration,wind_speed_10m_max,shortwave_radiation_sum",
            "timezone": "Africa/Lome",
            "forecast_days": forecast_days,
            "past_days": 7,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        dates = daily.get("time", [])

        rows = []
        for i, d in enumerate(dates):
            t_max = daily.get("temperature_2m_max", [None])[i]
            t_min = daily.get("temperature_2m_min", [None])[i]
            if t_max is None:
                continue
            rows.append({
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "date": d,
                "temperature_max": round(t_max, 2),
                "temperature_min": round(t_min, 2),
                "temperature_mean": round((t_max + t_min) / 2, 2),
                "precipitation_mm": round(daily.get("precipitation_sum", [0])[i] or 0, 2),
                "solar_radiation_mj": round((daily.get("shortwave_radiation_sum", [0])[i] or 0) / 1000, 3),
                "et0_mm": round(daily.get("et0_fao_evapotranspiration", [0])[i] or 0, 2),
                "wind_speed_ms": round((daily.get("wind_speed_10m_max", [0])[i] or 0) / 3.6, 2),
                "source": "open_meteo",
            })
        log.info(f"Open-Meteo: {len(rows)} jours pour ({lat}, {lon})")
        return rows

    except Exception as e:
        log.error(f"Open-Meteo error for ({lat}, {lon}): {e}")
        return []


# ═══════════════════════════════════════════════════════════
# Store in Supabase
# ═══════════════════════════════════════════════════════════

def _store_weather(rows: list[dict], region: Optional[str] = None):
    """Upsert weather data into Supabase."""
    if not rows:
        return 0
    from app.database import _get_client
    sb = _get_client()

    for r in rows:
        if region:
            r["region"] = region

    # Upsert (on conflict latitude+longitude+date+source)
    try:
        sb.table("weather_data").upsert(
            rows,
            on_conflict="latitude,longitude,date,source",
        ).execute()
        return len(rows)
    except Exception as e:
        log.error(f"Supabase weather upsert error: {e}")
        # Fallback: insert one by one, skip duplicates
        count = 0
        for r in rows:
            try:
                sb.table("weather_data").insert(r).execute()
                count += 1
            except Exception:
                pass
        return count


# ═══════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════

def refresh_climate_data(days_back: int = 90):
    """Fetch + store climate data for all 5 Togo regions.

    Call this daily via cron or on startup.
    - NASA POWER: last `days_back` days (historical, ~1-2 day lag)
    - Open-Meteo: last 7 days + 16 days forecast
    """
    end = date.today() - timedelta(days=1)  # NASA has 1-2 day lag
    start = end - timedelta(days=days_back)
    total = 0

    for region, coords in TOGO_REGION_COORDS.items():
        lat, lon = coords["lat"], coords["lon"]
        log.info(f"Fetching climate for {region} ({lat}, {lon})...")

        # NASA POWER (historical)
        nasa_rows = fetch_nasa_power(lat, lon, start, end)
        total += _store_weather(nasa_rows, region)

        # Open-Meteo (recent + forecast)
        meteo_rows = fetch_open_meteo(lat, lon)
        total += _store_weather(meteo_rows, region)

    log.info(f"Climate refresh complete: {total} records stored/updated")
    return total


def refresh_for_parcelle(lat: float, lon: float, region: Optional[str] = None, days_back: int = 30):
    """Fetch climate data for a specific parcelle GPS.

    Call this when a new parcelle is registered or on demand.
    """
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days_back)

    nasa_rows = fetch_nasa_power(lat, lon, start, end)
    meteo_rows = fetch_open_meteo(lat, lon)

    total = _store_weather(nasa_rows, region) + _store_weather(meteo_rows, region)
    log.info(f"Parcelle climate: {total} records for ({lat}, {lon})")
    return total


def get_climate_for_location(lat: float, lon: float, days: int = 30) -> dict:
    """Get aggregated climate stats for a location from Supabase.

    Returns real data if available, falls back to closest region.
    """
    from app.database import _get_client
    sb = _get_client()

    since = (date.today() - timedelta(days=days)).isoformat()

    # Try exact location first (within ~0.1 degree ≈ 11km)
    res = sb.table("weather_data").select("*").gte("date", since) \
        .gte("latitude", lat - 0.1).lte("latitude", lat + 0.1) \
        .gte("longitude", lon - 0.1).lte("longitude", lon + 0.1) \
        .order("date", desc=True).limit(100).execute()

    rows = res.data or []

    # Fallback: find closest region
    if len(rows) < 5:
        closest_region = _find_closest_region(lat, lon)
        res2 = sb.table("weather_data").select("*") \
            .eq("region", closest_region).gte("date", since) \
            .order("date", desc=True).limit(100).execute()
        rows = (res2.data or []) + rows

    if not rows:
        # Ultimate fallback: return hardcoded values (old behavior)
        from app.ml.togo_adapter import TOGO_REGIONS
        region = _find_closest_region(lat, lon)
        static = TOGO_REGIONS.get(region, TOGO_REGIONS["Centrale"])
        return {
            "source": "hardcoded_fallback",
            "avg_temp": static["avg_temp"],
            "total_rainfall_mm": static["rainfall_mm"],
            "drought_index": static["drought_prob"],
            "data_points": 0,
            "region": region,
        }

    import statistics
    temps = [r["temperature_mean"] for r in rows if r.get("temperature_mean")]
    precips = [r["precipitation_mm"] for r in rows if r.get("precipitation_mm") is not None]
    humidities = [r["humidity_pct"] for r in rows if r.get("humidity_pct")]

    total_rain = sum(precips)
    avg_temp = statistics.mean(temps) if temps else 28.0
    dry_days = sum(1 for p in precips if p < 1.0)
    drought_index = dry_days / max(len(precips), 1)

    return {
        "source": "nasa_power+open_meteo",
        "avg_temp": round(avg_temp, 2),
        "temp_max": round(max(temps), 2) if temps else None,
        "temp_min": round(min(temps), 2) if temps else None,
        "total_rainfall_mm": round(total_rain, 1),
        "avg_daily_rain_mm": round(total_rain / max(len(precips), 1), 2),
        "dry_days": dry_days,
        "drought_index": round(drought_index, 3),
        "avg_humidity": round(statistics.mean(humidities), 1) if humidities else None,
        "data_points": len(rows),
        "period_days": days,
        "region": rows[0].get("region", _find_closest_region(lat, lon)),
    }


def _find_closest_region(lat: float, lon: float) -> str:
    """Find the closest Togo region to a GPS point."""
    best = "Centrale"
    best_dist = float("inf")
    for region, coords in TOGO_REGION_COORDS.items():
        dist = (lat - coords["lat"]) ** 2 + (lon - coords["lon"]) ** 2
        if dist < best_dist:
            best_dist = dist
            best = region
    return best
