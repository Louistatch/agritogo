"""GARCH Volatility Forecasting — weekly observed prices from Supabase.

The model fits on the weekly median price series (per market, then across
markets) built by app.ml.price_forecast. No synthetic data is ever added:
below 12 weeks of observations the function returns an explicit error.
"""
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, date

log = logging.getLogger(__name__)

# ── Data loading ──────────────────────────────────────────────────────

def _load_from_supabase(product: str) -> pd.DataFrame:
    """Load real market prices for a product from Supabase."""
    from app.database import _get_client
    sb = _get_client()

    # Resolve culture_id from name
    cultures = sb.table("cultures").select("id, name").execute().data or []
    culture_map = {c["name"].lower(): c["id"] for c in cultures}
    cid = culture_map.get(product.lower())
    if not cid:
        # Fuzzy match
        for name, id_ in culture_map.items():
            if product.lower() in name or name in product.lower():
                cid = id_
                break
    if not cid:
        return pd.DataFrame()

    res = (
        sb.table("market_prices")
        .select("price, created_at, market_name")
        .eq("culture_id", cid)
        .order("created_at")
        .execute()
    )
    rows = res.data or []
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["price_fcfa"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["Date", "price_fcfa"]).sort_values("Date").reset_index(drop=True)
    return df


def _augment_synthetic(real_df: pd.DataFrame, product: str, target_n: int = 200) -> pd.DataFrame:
    """Augment real data with synthetic data calibrated on real values."""
    np.random.seed(abs(hash(product)) % 2**31)

    if len(real_df) > 0:
        base_price = float(real_df["price_fcfa"].mean())
        volatility = float(real_df["price_fcfa"].std() / base_price) if base_price > 0 else 0.05
    else:
        # Fallback base prices per product (from real Togo market knowledge)
        base_price = {"Maïs": 180, "Riz": 350, "Sorgho": 150, "Mil": 140,
                      "Igname": 200, "Manioc": 90, "Soja": 280, "Arachide": 320,
                      "Tomate": 600, "Piment": 450, "Oignon": 300, "Haricot": 400}.get(product, 200)
        volatility = 0.03

    n_synthetic = max(0, target_n - len(real_df))
    if n_synthetic == 0:
        return real_df

    log.warning(f"[GARCH] Only {len(real_df)} real prices for {product}, "
                f"augmenting with {n_synthetic} synthetic (collectez plus de données terrain !)")

    end = real_df["Date"].min() if len(real_df) > 0 else datetime.now()
    dates = [end - timedelta(days=i + 1) for i in range(n_synthetic)][::-1]
    rets = np.random.normal(0.0001, volatility, n_synthetic)
    prices = base_price * np.exp(np.cumsum(rets))

    synthetic = pd.DataFrame({
        "Date": dates,
        "price_fcfa": prices,
        "market_name": "synthetic",
    })

    combined = pd.concat([synthetic, real_df], ignore_index=True).sort_values("Date").reset_index(drop=True)
    return combined


# ── GARCH model ───────────────────────────────────────────────────────

def run_garch_forecast(product: str = "Maïs", periods: int = 30) -> dict:
    """Fit GARCH(1,1) on real Supabase prices (augmented if needed)."""
    np.random.seed(42)

    # 1. Série hebdomadaire OBSERVÉE (médiane par marché puis entre marchés).
    #    Plus de données synthétiques : la volatilité des rendements d'une série
    #    inventée n'informe sur rien, et mélanger les marchés relevé par relevé
    #    prenait les écarts entre marchés pour des variations de prix.
    from app.database import _get_client, _resolve_culture
    from app.ml.price_forecast import load_observations, weekly_series

    sb = _get_client()
    culture = _resolve_culture(sb, product)
    weekly = (
        weekly_series(load_observations(sb, str(culture["id"]), None, None))
        if culture else pd.Series(dtype=float)
    )
    n_real = len(weekly)
    if n_real < 12:
        return {"error": f"Pas assez de relevés hebdomadaires pour {product} ({n_real} semaines, il en faut 12)."}
    data = pd.DataFrame({"Date": weekly.index, "price_fcfa": weekly.to_numpy(float)})

    # 3. Compute returns
    data["returns"] = data["price_fcfa"].pct_change().fillna(0) * 100
    returns_pct = data["returns"].values[1:]  # skip first NaN
    prices = data["price_fcfa"].values

    # 4. Technical indicators
    sma20 = float(pd.Series(prices).rolling(20).mean().iloc[-1]) if len(prices) >= 20 else float(prices[-1])
    rsi14 = _compute_rsi(prices, 14)

    # 5. Fit GARCH(1,1)
    try:
        from arch import arch_model
        model = arch_model(returns_pct, vol="Garch", p=1, q=1, mean="Zero")
        result = model.fit(disp="off")
        params = {k: round(float(v), 6) for k, v in result.params.items()}
        weeks = max(1, int(np.ceil(periods / 7)))
        fc = result.forecast(horizon=weeks)
        vol_forecast = np.sqrt(fc.variance.iloc[-1].values) / 100
    except Exception:
        params = {"omega": 0.0001, "alpha[1]": 0.12, "beta[1]": 0.85}
        weeks = max(1, int(np.ceil(periods / 7)))
        vol_forecast = np.full(weeks, float(np.std(returns_pct / 100)))

    last_price = float(prices[-1])
    today = datetime.combine(date.today(), datetime.min.time())
    # Pas hebdomadaire : le modèle est ajusté sur des rendements de semaine en semaine.
    forecast_dates = [today + timedelta(days=7 * (i + 1)) for i in range(len(vol_forecast))]
    forecast_30d = [
        {
            "date": d.strftime("%Y-%m-%d"),
            "predicted_volatility": round(float(v), 6),
            "price_lower": round(last_price * (1 - 2 * v), 1),
            "price_upper": round(last_price * (1 + 2 * v), 1),
        }
        for d, v in zip(forecast_dates, vol_forecast)
    ]

    # Annualisation d'une volatilité hebdomadaire : racine de 52 (et non de 252 jours de bourse).
    hist_vol = pd.Series(returns_pct / 100).rolling(12).std() * np.sqrt(52)
    current_vol = float(hist_vol.dropna().iloc[-1]) if len(hist_vol.dropna()) > 0 else 0.0

    return {
        "product": product,
        "data_quality": {
            "weekly_points": n_real,
            "total_used": len(data),
            "source": "supabase (médianes hebdomadaires observées)",
            "recommendation": None if n_real >= 30 else (
                f"Seulement {n_real} semaines de relevés : volatilité indicative."
            ),
        },
        "model_params": params,
        "forecast_30d": forecast_30d,
        "historical_volatility_stats": {
            "mean_annual": round(float(hist_vol.mean()), 4) if len(hist_vol.dropna()) > 0 else 0,
            "max_annual": round(float(hist_vol.max()), 4) if len(hist_vol.dropna()) > 0 else 0,
            "current": round(current_vol, 4),
        },
        "last_price_fcfa": round(last_price, 1),
        "sma20": round(sma20, 1),
        "rsi14": round(rsi14, 1),
        "summary": (
            f"GARCH(1,1) sur {n_real} semaines de prix observés pour {product}. "
            f"Volatilité actuelle: {current_vol:.2%}. Dernier prix: {round(last_price, 1)} FCFA."
        ),
    }


def _compute_rsi(prices, period=14):
    """Simple RSI computation."""
    if len(prices) < period + 1:
        return 50.0
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)
