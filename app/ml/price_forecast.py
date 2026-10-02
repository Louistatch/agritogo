"""Prévision des prix — séries hebdomadaires observées, modèle évalué avant usage.

Principes :
- Données OBSERVÉES uniquement (market_prices, data_kind = observation). Jamais
  de données synthétiques : une prévision bâtie sur des prix inventés n'est pas
  une prévision.
- Même construction que l'écran Marché : relevés dédupliqués, médiane par
  marché et par semaine, puis médiane des marchés de la zone. Un marché très
  enquêté ne pèse pas plus qu'un autre, et les écarts entre marchés ne sont pas
  pris pour des variations de prix.
- Modèle : moyenne de deux lissages exponentiels sur le logarithme du prix
  (variations relatives, prix toujours positifs) : simple, et de Holt à tendance
  amortie. Choisi sur les données réelles (6 cultures × régions, 38 semaines,
  validation glissante) : erreur moyenne à 4 semaines de 8,6 % contre 10,0 %
  pour « le prix ne bouge pas », et 6,8 % contre 7,1 % à 1 semaine. Chaque
  prévision est de nouveau comparée à cette référence naïve sur sa propre
  série : la confiance annoncée vient de cette comparaison.
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

MODEL_NAME = "lissage-ses-holt-hebdo"
MODEL_VERSION = "1"
MIN_WEEKS = 8
HORIZON_WEEKS = 4
Z80 = 1.2816


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", "" if value is None else str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


# ── Données ───────────────────────────────────────────────────────────

def resolve_zone(sb, zone: str | None) -> tuple[str | None, str | None, str]:
    """(colonne, id, libellé) d'une zone donnée par son nom ; national si vide."""
    if not zone:
        return None, None, "Togo"
    key = _norm(zone)
    for table, column in (("cantons", "canton_id"), ("prefectures", "prefecture_id"), ("regions", "region_id")):
        rows = sb.table(table).select("id,name").execute().data or []
        exact = [r for r in rows if _norm(r["name"]) == key]
        if exact:
            return column, str(exact[0]["id"]), exact[0]["name"]
    return None, None, zone


def load_observations(sb, culture_id: str, column: str | None, zone_id: str | None) -> pd.DataFrame:
    """Relevés observés d'une culture, par tranches (PostgREST plafonne à 1000)."""
    rows: list[dict] = []
    for page in range(20):
        q = (
            sb.table("market_prices")
            .select("market_name, price, observed_at, created_at, data_kind")
            .eq("culture_id", culture_id)
            .gt("price", 0)
            .order("created_at")
            .range(page * 1000, page * 1000 + 999)
        )
        if column and zone_id:
            q = q.eq(column, zone_id)
        chunk = q.execute().data or []
        rows.extend(chunk)
        if len(chunk) < 1000:
            break
    if not rows:
        return pd.DataFrame(columns=["market", "day", "price"])
    df = pd.DataFrame(rows)
    df = df[(df["data_kind"].fillna("observation")) == "observation"]
    df["day"] = pd.to_datetime(df["observed_at"].fillna(df["created_at"]), errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.rename(columns={"market_name": "market"})[["market", "day", "price"]].dropna()
    return df.drop_duplicates(subset=["market", "day", "price"])


def weekly_series(obs: pd.DataFrame) -> pd.Series:
    """Médiane par marché et par semaine, puis médiane des marchés."""
    if obs.empty:
        return pd.Series(dtype=float)
    obs = obs.copy()
    obs["week"] = obs["day"] - pd.to_timedelta(obs["day"].dt.weekday, unit="D")
    per_market = obs.groupby(["week", "market"])["price"].median()
    series = per_market.groupby(level="week").median().sort_index()
    full = pd.date_range(series.index.min(), series.index.max(), freq="7D")
    # Une ou deux semaines sans relevé : on reporte le dernier prix connu.
    # Au-delà, la série est coupée là (une longue absence n'est pas un prix stable).
    series = series.reindex(full).ffill(limit=2)
    last_gap = series[series.isna()].index.max() if series.isna().any() else None
    if last_gap is not None:
        series = series[series.index > last_gap]
    return series.dropna()


# ── Modèle ────────────────────────────────────────────────────────────

def _fit_forecast(values: np.ndarray, horizon: int) -> tuple[np.ndarray, float]:
    """Prévision en log + écart-type des résidus. Repli naïf si le modèle échoue."""
    logs = np.log(values)
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing, SimpleExpSmoothing

        holt = ExponentialSmoothing(logs, trend="add", damped_trend=True, initialization_method="estimated").fit(optimized=True)
        ses = SimpleExpSmoothing(logs, initialization_method="estimated").fit(optimized=True)
        fc = (np.asarray(holt.forecast(horizon)) + np.asarray(ses.forecast(horizon))) / 2
        fitted = (np.asarray(holt.fittedvalues) + np.asarray(ses.fittedvalues)) / 2
        resid = logs[1:] - fitted[1:]
        sigma = float(np.std(resid, ddof=1)) if len(resid) > 2 else 0.05
    except Exception:
        fc = np.full(horizon, logs[-1])
        diffs = np.diff(logs)
        sigma = float(np.std(diffs, ddof=1)) if len(diffs) > 2 else 0.05
    return fc, max(sigma, 0.01)


def backtest(values: np.ndarray, folds: int = 8, horizon: int = HORIZON_WEEKS) -> dict[str, float | int]:
    """Validation glissante à `horizon` semaines : erreur du modèle contre la prévision naïve."""
    n = len(values)
    folds = min(folds, n - MIN_WEEKS - horizon + 2)
    if folds < 2:
        return {"folds": 0}
    err_m, err_n = [], []
    for t in range(n - folds - horizon + 1, n - horizon + 1):
        train = values[:t]
        fc, _ = _fit_forecast(train, horizon)
        pred = math.exp(fc[-1])
        actual = values[t + horizon - 1]
        err_m.append(abs(pred - actual) / actual)
        err_n.append(abs(train[-1] - actual) / actual)
    mape_m = float(np.mean(err_m))
    mape_n = float(np.mean(err_n))
    skill = 1 - mape_m / mape_n if mape_n > 0 else 0.0
    return {
        "folds": folds,
        "horizon_semaines": horizon,
        "mape": round(mape_m * 100, 1),
        "mape_naive": round(mape_n * 100, 1),
        "skill": round(skill, 2),
    }


def forecast_price(series: pd.Series, horizon: int = HORIZON_WEEKS) -> dict[str, Any]:
    n = len(series)
    if n < MIN_WEEKS:
        return {"ok": False, "reason": f"seulement {n} semaine(s) de relevés continus (il en faut {MIN_WEEKS})"}
    values = series.to_numpy(dtype=float)
    fc, sigma = _fit_forecast(values, horizon)
    bt = backtest(values)
    last_week = series.index[-1]
    points = []
    for h in range(1, horizon + 1):
        mid = math.exp(fc[h - 1])
        band = Z80 * sigma * math.sqrt(h)
        points.append({
            "semaine_du": (last_week + timedelta(days=7 * h)).date().isoformat(),
            "prix": round(mid),
            "bas": round(mid * math.exp(-band)),
            "haut": round(mid * math.exp(band)),
        })
    last = float(values[-1])
    change = (points[-1]["prix"] - last) / last * 100
    skill = float(bt.get("skill", 0) or 0)
    if n >= 20 and skill > 0.15 and bt.get("mape", 99) < 10:
        confidence = "élevée"
    elif n >= 12 and skill > 0:
        confidence = "moyenne"
    else:
        confidence = "faible"
    return {
        "ok": True,
        "semaines_observees": n,
        "derniere_semaine": last_week.date().isoformat(),
        "dernier_prix": round(last),
        "previsions": points,
        "variation_4_semaines_pct": round(change, 1),
        "sens": "hausse" if change >= 3 else "baisse" if change <= -3 else "stable",
        "validation": bt,
        "confiance": confidence,
        "modele": f"{MODEL_NAME} v{MODEL_VERSION}",
    }


# ── Point d'entrée ────────────────────────────────────────────────────

def run_price_forecast(product: str, zone: str | None = None, save: bool = True) -> dict[str, Any]:
    from app.database import _get_client, _resolve_culture

    sb = _get_client()
    culture = _resolve_culture(sb, product)
    if not culture:
        return {"ok": False, "reason": f"culture inconnue : {product}"}
    column, zone_id, zone_label = resolve_zone(sb, zone)
    if zone and not zone_id:
        return {"ok": False, "reason": f"zone inconnue : {zone}"}
    series = weekly_series(load_observations(sb, str(culture["id"]), column, zone_id))
    result = forecast_price(series)
    result.update({"produit": culture["name"], "zone": zone_label})

    if save and result.get("ok"):
        region_id = zone_id if column == "region_id" else None
        if column in ("prefecture_id", "canton_id"):
            table = "prefectures" if column == "prefecture_id" else "cantons"
            try:
                row = sb.table(table).select("*").eq("id", zone_id).limit(1).execute().data or []
                if row and column == "prefecture_id":
                    region_id = row[0].get("region_id")
                elif row:
                    pref = sb.table("prefectures").select("region_id").eq("id", row[0]["prefecture_id"]).limit(1).execute().data or []
                    region_id = pref[0]["region_id"] if pref else None
            except Exception:
                region_id = None
        try:
            sb.table("market_price_forecasts").insert([
                {
                    "culture_id": culture["id"],
                    "region_id": region_id,
                    "market_name": zone_label,
                    "forecast_price": p["prix"],
                    "target_date": p["semaine_du"],
                    "confidence": {"élevée": 0.8, "moyenne": 0.6, "faible": 0.4}[result["confiance"]],
                    "unit": "kg",
                    "currency": "FCFA",
                    "model": MODEL_NAME,
                    "model_version": MODEL_VERSION,
                }
                for p in result["previsions"]
            ]).execute()
        except Exception:
            pass
    return result
