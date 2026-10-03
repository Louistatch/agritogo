"""
Normales climatiques 30 ans via NASA POWER Climatology.
ETP Penman-Monteith FAO-56 calculée depuis T, RH, Vent, Rayonnement
(community=ag : rayonnement en MJ/m²/j, pluie en mm/j).

Endpoint : https://power.larc.nasa.gov/api/temporal/climatology/point
(différent du endpoint daily utilisé dans app/climate.py)
"""
import math
import logging
import requests

log = logging.getLogger(__name__)

_NASA_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
_JOURS_MOIS  = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# Fallbacks par région Togo (si NASA POWER indisponible)
_FALLBACKS = {
    "Maritime": {
        "etp":   [4.8, 5.2, 5.4, 5.0, 4.5, 4.2, 4.0, 4.3, 4.5, 4.8, 4.9, 4.7],
        "pluie": [27, 50, 93, 117, 239, 341, 128, 46, 3, 3, 23, 45],
        "temp":  [27.5, 28.4, 28.8, 28.4, 27.2, 25.8, 25.0, 24.8, 25.2, 26.4, 27.5, 27.8],
    },
    "Plateaux": {
        "etp":   [5.0, 5.3, 5.2, 4.8, 4.3, 4.0, 4.2, 4.5, 4.8, 5.0, 5.1, 5.0],
        "pluie": [18, 40, 82, 129, 212, 235, 164, 68, 5, 4, 12, 28],
        "temp":  [26.2, 27.5, 27.8, 27.2, 26.0, 24.5, 24.0, 24.2, 24.8, 25.8, 26.5, 26.0],
    },
    "Centrale": {
        "etp":   [5.5, 5.8, 5.6, 5.2, 4.7, 4.5, 4.5, 4.8, 5.0, 5.3, 5.5, 5.5],
        "pluie": [5, 15, 55, 107, 155, 175, 188, 238, 180, 78, 5, 2],
        "temp":  [27.8, 29.5, 29.8, 28.8, 27.5, 25.8, 25.0, 24.8, 25.2, 26.8, 27.5, 27.2],
    },
    "Kara": {
        "etp":   [5.8, 6.0, 5.8, 5.4, 4.8, 4.5, 4.5, 4.8, 5.0, 5.5, 5.8, 5.8],
        "pluie": [2, 8, 52, 95, 158, 175, 205, 262, 185, 68, 4, 1],
        "temp":  [27.2, 29.8, 30.5, 29.5, 27.8, 26.0, 25.2, 24.8, 25.5, 27.2, 27.8, 27.0],
    },
    "Savanes": {
        "etp":   [6.5, 7.0, 6.8, 6.2, 5.5, 5.0, 5.0, 5.2, 5.5, 6.2, 6.8, 6.8],
        "pluie": [1, 4, 25, 65, 120, 148, 188, 275, 175, 52, 2, 1],
        "temp":  [27.5, 30.5, 32.0, 31.0, 29.2, 27.5, 26.5, 25.8, 26.5, 28.2, 28.5, 27.5],
    },
}

# Coords de référence pour chaque région
REGION_COORDS = {
    "Maritime":  (6.20,  1.20),
    "Plateaux":  (7.00,  1.15),
    "Centrale":  (8.55,  1.10),
    "Kara":      (9.55,  1.18),
    "Savanes":   (10.65, 0.20),
}


_MID_MONTH_DOY = [15, 46, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349]


def _ra(lat_deg: float, doy: int) -> float:
    """Rayonnement extraterrestre Ra (MJ m⁻² j⁻¹), FAO-56 éq. 21–25."""
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)
    delta = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta))))
    return (24 * 60 / math.pi) * 0.0820 * dr * (
        ws * math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.sin(ws)
    )


def _es(t: float) -> float:
    return 0.6108 * math.exp(17.27 * t / (t + 237.3))


def _penman_monteith(tmax, tmin, tmean, rh, ws, rs, lat=8.5, doy=166, g=0.0, z=200.0):
    """ETo Penman-Monteith FAO-56 (mm/jour), pas mensuel.

    Corrections de l'audit (oct. 2026) :
      - es = moyenne de e°(Tmax) et e°(Tmin) (éq. 12), et non e°(Tmoy) ;
      - Rso = (0,75 + 2e-5 z) Ra avec Ra calculé (latitude, jour) — l'ancien
        code dérivait Rso de Rs lui-même, ce qui faussait Rnl ;
      - Rs/Rso plafonné à 1 ; flux de chaleur du sol mensuel G (éq. 43).
    """
    es = (_es(tmax) + _es(tmin)) / 2
    ea = es * rh / 100.0
    delta = 4098 * _es(tmean) / (tmean + 237.3) ** 2
    pressure = 101.3 * ((293 - 0.0065 * z) / 293) ** 5.26
    gamma = 0.000665 * pressure
    rso = (0.75 + 2e-5 * z) * _ra(lat, doy)
    ratio = min(rs / rso, 1.0) if rso > 0 else 0.7
    rns = 0.77 * rs
    sigma = 4.903e-9
    rnl = (sigma * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2
           * (0.34 - 0.14 * math.sqrt(max(ea, 0)))
           * (1.35 * ratio - 0.35))
    rn = rns - rnl
    eto = (0.408 * delta * (rn - g) + gamma * (900 / (tmean + 273)) * ws * (es - ea)) / \
          (delta + gamma * (1 + 0.34 * ws))
    return max(0.0, round(eto, 2))


def get_nasa_climatology(lat: float, lon: float) -> dict:
    """
    Normales climatiques 30 ans pour une localisation GPS.
    Retourne ETP (mm/j), précipitations (mm/mois) et temp (°C) Jan→Déc.
    """
    try:
        r = requests.get(
            "https://power.larc.nasa.gov/api/temporal/climatology/point",
            params={
                "latitude":   round(lat, 4),
                "longitude":  round(lon, 4),
                "parameters": "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M,WS2M,ALLSKY_SFC_SW_DWN",
                "format":     "JSON",
                "community":  "ag",
            },
            timeout=20,
        )
        r.raise_for_status()
        d = r.json()["properties"]["parameter"]

        etp_list, pluie_list, temp_list = [], [], []
        temps = [d["T2M"][m] for m in _NASA_MONTHS]
        for i, m in enumerate(_NASA_MONTHS):
            g = 0.07 * (temps[(i + 1) % 12] - temps[i - 1])   # FAO-56 éq. 43
            eto = _penman_monteith(
                d["T2M_MAX"][m], d["T2M_MIN"][m], d["T2M"][m],
                d["RH2M"][m], d["WS2M"][m], d["ALLSKY_SFC_SW_DWN"][m],
                lat=lat, doy=_MID_MONTH_DOY[i], g=g,
            )
            pluie = round(d["PRECTOTCORR"][m] * _JOURS_MOIS[i], 1)
            etp_list.append(eto)
            pluie_list.append(pluie)
            temp_list.append(round(d["T2M"][m], 1))

        return {
            "source":          "NASA POWER Climatology (30 ans)",
            "etp_mensuelle":   etp_list,
            "pluie_mensuelle": pluie_list,
            "temp_mensuelle":  temp_list,
            "total_precip":    round(sum(pluie_list), 0),
            "avg_temp":        round(sum(temp_list) / 12, 1),
        }

    except Exception as e:
        log.warning(f"NASA POWER climatology failed for ({lat},{lon}): {e} — using fallback")
        return _get_fallback(lat, lon)


def _get_fallback(lat: float, lon: float) -> dict:
    """Retourne les données de la région Togo la plus proche."""
    best = "Centrale"
    best_dist = float("inf")
    for region, (rlat, rlon) in REGION_COORDS.items():
        dist = (lat - rlat) ** 2 + (lon - rlon) ** 2
        if dist < best_dist:
            best_dist, best = dist, region

    fb = _FALLBACKS[best]
    return {
        "source":          f"Défaut ({best})",
        "etp_mensuelle":   fb["etp"],
        "pluie_mensuelle": fb["pluie"],
        "temp_mensuelle":  fb["temp"],
        "total_precip":    round(sum(fb["pluie"]), 0),
        "avg_temp":        round(sum(fb["temp"]) / 12, 1),
    }


def get_region_climatology(region: str) -> dict:
    """Normales climatiques pour une région Togo nommée."""
    coords = REGION_COORDS.get(region)
    if coords:
        return get_nasa_climatology(*coords)
    return _get_fallback(8.55, 1.10)
