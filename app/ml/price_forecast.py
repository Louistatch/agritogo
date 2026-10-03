"""Prévision des prix — séries hebdomadaires observées, modèle évalué avant usage.

Principes (audit méthodologique d'octobre 2026, voir docs/PRICE_FORECAST_AUDIT.md) :
- Données OBSERVÉES et DATÉES uniquement : relevés `data_kind = observation`
  portant une date d'observation et exprimés en FCFA/kg. Les saisies sans date
  de relevé ni protocole (source « manual ») sont exclues : mêlées au SIM, elles
  créaient des sauts de niveau (maïs : +58 % par rapport aux relevés CPC).
- Indice de zone par EFFETS FIXES marché (log p = niveau du marché + effet de la
  semaine, estimés par médianes itérées). La médiane des marchés présents
  variait selon les marchés qui rapportaient chaque semaine (biais de
  composition) ; l'indice à effets fixes réduit ce bruit d'environ 20 %.
- Modèle : moyenne de trois prévisions sur le log du prix — naïve, lissage
  exponentiel simple, Holt à tendance amortie (famille du benchmark « Comb » de
  la compétition M4). Validé en origine glissante sur TOUTES les origines
  possibles : sur les données réelles, aucun modèle ne bat nettement « le prix
  ne bouge pas » à 1–4 semaines, ce qui est conforme à la littérature. La
  confiance annoncée en découle : elle n'est « moyenne » ou « élevée » que si la
  série montre un gain mesuré sur le naïf.
- Erreur mesurée en MASE (Hyndman & Koehler 2006) et en MAPE ; les semaines
  reportées (trou de 1–2 semaines) ne servent jamais de cible de validation.
- Intervalle à 80 % : quantiles EMPIRIQUES des erreurs hors échantillon à h
  semaines (repli paramétrique élargi si trop peu d'erreurs) ; la couverture
  observée est publiée.
- Pas de saisonnalité estimée : il faudrait au moins 2 à 3 années complètes.
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

MODEL_NAME = "comb-naif-ses-holt-ef"
MODEL_VERSION = "2"
MIN_WEEKS = 8
HORIZON_WEEKS = 4
Z80 = 1.2816
# Quantiles des erreurs passées pour viser 80 % de couverture : avec 12 à 30
# erreurs, les quantiles 10/90 % sous-couvrent (72,9 % mesurés hors échantillon
# sur les séries CPC) ; 5/95 % donnent 78,7 %. Correction de petit échantillon.
Q_LOW, Q_HIGH = 0.05, 0.95


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
            .select("market_name, price, unit, observed_at, data_kind")
            .eq("culture_id", culture_id)
            .gt("price", 0)
            .not_.is_("observed_at", "null")
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
    df = df[df["unit"].fillna("kg").str.lower() == "kg"]
    df["day"] = pd.to_datetime(df["observed_at"], errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.rename(columns={"market_name": "market"})[["market", "day", "price"]].dropna()
    return df.drop_duplicates(subset=["market", "day", "price"])


def weekly_series(obs: pd.DataFrame) -> pd.Series:
    """Indice hebdomadaire de zone, robuste au changement des marchés relevés.

    Médiane par marché et par semaine, puis modèle à effets fixes
    log p[m,t] = a[m] + b[t] estimé par médianes itérées (robuste aux valeurs
    aberrantes). L'indice vaut exp(b[t] + médiane des a[m]) : le niveau d'un
    marché typique de la zone. Un marché cher qui manque une semaine ne fait
    plus baisser artificiellement la zone.
    """
    if obs.empty:
        return pd.Series(dtype=float)
    obs = obs.copy()
    obs["week"] = obs["day"] - pd.to_timedelta(obs["day"].dt.weekday, unit="D")
    pm = obs.groupby(["week", "market"])["price"].median().apply(np.log).reset_index()
    a = pm.groupby("market")["price"].median()
    b = pd.Series(dtype=float)
    for _ in range(20):
        b_new = (pm["price"] - pm["market"].map(a)).groupby(pm["week"]).median()
        a = (pm["price"] - pm["week"].map(b_new)).groupby(pm["market"]).median()
        if len(b) and np.allclose(b_new.reindex(b.index), b, atol=1e-6):
            b = b_new
            break
        b = b_new
    series = np.exp(b + float(np.median(a))).sort_index()
    full = pd.date_range(series.index.min(), series.index.max(), freq="7D")
    # Une ou deux semaines sans relevé : on reporte le dernier prix connu.
    # Au-delà, la série est coupée là (une longue absence n'est pas un prix stable).
    raw = series.reindex(full)
    series = raw.ffill(limit=2)
    last_gap = series[series.isna()].index.max() if series.isna().any() else None
    if last_gap is not None:
        series = series[series.index > last_gap]
        raw = raw[raw.index > last_gap]
    series = series.dropna()
    # Semaines reportées : jamais utilisées comme cible de validation.
    series.attrs["imputed"] = raw.reindex(series.index).isna().to_numpy()
    return series


# ── Modèle ────────────────────────────────────────────────────────────

def _fit_forecast(values: np.ndarray, horizon: int) -> tuple[np.ndarray, float]:
    """Prévision en log (moyenne naïf + SES + Holt amorti) et écart-type des
    variations hebdomadaires. Repli naïf si le lissage échoue."""
    logs = np.log(values)
    naive = np.full(horizon, logs[-1])
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing, SimpleExpSmoothing

        holt = ExponentialSmoothing(logs, trend="add", damped_trend=True, initialization_method="estimated").fit(optimized=True)
        ses = SimpleExpSmoothing(logs, initialization_method="estimated").fit(optimized=True)
        fc = (naive + np.asarray(holt.forecast(horizon)) + np.asarray(ses.forecast(horizon))) / 3
    except Exception:
        fc = naive
    diffs = np.diff(logs)
    sigma = float(np.std(diffs, ddof=1)) if len(diffs) > 2 else 0.05
    return fc, max(sigma, 0.01)


MIN_TRAIN = 8


def backtest(values: np.ndarray, imputed: np.ndarray | None = None, horizon: int = HORIZON_WEEKS) -> dict[str, Any]:
    """Validation en origine glissante sur toutes les origines possibles.

    Renvoie, par horizon, les erreurs log hors échantillon du modèle et du naïf.
    Une semaine reportée (imputée) n'est jamais une cible.
    """
    n = len(values)
    imputed = np.zeros(n, dtype=bool) if imputed is None else imputed
    errs: dict[int, list[float]] = {h: [] for h in range(1, horizon + 1)}
    naive_errs: dict[int, list[float]] = {h: [] for h in range(1, horizon + 1)}
    for t in range(MIN_TRAIN, n):
        fc, _ = _fit_forecast(values[:t], horizon)
        for h in range(1, horizon + 1):
            k = t + h - 1
            if k >= n or imputed[k]:
                continue
            actual = math.log(values[k])
            errs[h].append(actual - fc[h - 1])
            naive_errs[h].append(actual - math.log(values[t - 1]))
    e, en = np.asarray(errs[horizon]), np.asarray(naive_errs[horizon])
    if len(e) < 4:
        return {"folds": int(len(e)), "errors": errs}
    # MASE : MAE du modèle / MAE du naïf à 1 semaine dans l'échantillon.
    scale = float(np.mean(np.abs(np.diff(np.log(values))))) or 1e-9
    mae_m, mae_n = float(np.mean(np.abs(e))), float(np.mean(np.abs(en)))
    return {
        "folds": int(len(e)),
        "horizon_semaines": horizon,
        "mape": round(float(np.mean(np.abs(np.expm1(-e)))) * 100, 1),
        "mape_naive": round(float(np.mean(np.abs(np.expm1(-en)))) * 100, 1),
        "mase": round(mae_m / scale, 2),
        "mase_naive": round(mae_n / scale, 2),
        "skill": round(1 - mae_m / mae_n, 2) if mae_n > 0 else 0.0,
        "errors": errs,
    }


def _band(errors: list[float], fc_h: float, sigma: float, h: int) -> tuple[float, float, str]:
    """Bornes log à 80 % : quantiles empiriques des erreurs hors échantillon,
    ou repli paramétrique élargi (+25 %) s'il y a moins de 12 erreurs."""
    if len(errors) >= 12:
        lo, hi = np.quantile(errors, [Q_LOW, Q_HIGH])
        return fc_h + float(lo), fc_h + float(hi), "empirique"
    band = 1.25 * Z80 * sigma * math.sqrt(h)
    return fc_h - band, fc_h + band, "parametrique"


def forecast_price(series: pd.Series, horizon: int = HORIZON_WEEKS) -> dict[str, Any]:
    n = len(series)
    if n < MIN_WEEKS:
        return {"ok": False, "reason": f"seulement {n} semaine(s) de relevés continus (il en faut {MIN_WEEKS})"}
    values = series.to_numpy(dtype=float)
    imputed = series.attrs.get("imputed")
    fc, sigma = _fit_forecast(values, horizon)
    bt = backtest(values, imputed, horizon)
    errors = bt.pop("errors", {})
    last_week = series.index[-1]
    points, methods = [], set()
    lo_prev, hi_prev = -math.inf, -math.inf
    for h in range(1, horizon + 1):
        lo, hi, how = _band(errors.get(h, []), float(fc[h - 1]), sigma, h)
        methods.add(how)
        # L'incertitude ne diminue pas avec l'horizon.
        width = max(hi - lo, hi_prev - lo_prev)
        mid_log = float(fc[h - 1])
        if hi - lo < width:
            lo, hi = mid_log - width / 2, mid_log + width / 2
        lo_prev, hi_prev = lo, hi
        points.append({
            "semaine_du": (last_week + timedelta(days=7 * h)).date().isoformat(),
            "prix": round(math.exp(mid_log)),
            "bas": round(min(math.exp(lo), math.exp(mid_log))),
            "haut": round(max(math.exp(hi), math.exp(mid_log))),
        })
    # Couverture HORS ÉCHANTILLON de l'intervalle à l'horizon final : chaque
    # erreur est jugée avec l'intervalle bâti sur les seules erreurs antérieures.
    e = list(errors.get(horizon, []))
    hits = []
    for i in range(12, len(e)):
        lo_q, hi_q = np.quantile(e[:i], [Q_LOW, Q_HIGH])
        hits.append(lo_q <= e[i] <= hi_q)
    if len(hits) >= 5:
        bt["couverture_80"] = round(float(np.mean(hits)) * 100)
        bt["couverture_tests"] = len(hits)
    bt["intervalle"] = "empirique" if methods == {"empirique"} else "parametrique"
    last = float(values[-1])
    change = (points[-1]["prix"] - last) / last * 100
    skill = float(bt.get("skill", 0) or 0)
    folds = int(bt.get("folds", 0))
    # Confiance = gain MESURÉ sur « le prix ne bouge pas », pas un avis.
    if folds >= 20 and skill >= 0.15:
        confidence = "élevée"
    elif folds >= 10 and skill >= 0.05:
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
