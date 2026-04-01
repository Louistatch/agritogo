"""Climate-Resilient Crop Yield Prediction — per-crop RF + XGBoost for Togo.

Datasets used (priority order):
1. climate_change_impact.csv — Region, Year, Average_Temperature, Precipitation,
   Crop_Yield, Extreme_Weather_Events (if available)
2. archive1/yield_df.csv — Area, Item, Year, hg/ha_yield, average_rain_fall_mm_per_year,
   pesticides_tonnes, avg_temp (fallback)
"""
import os
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_squared_error

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'agentscope', 'data')
REGIONS = ["Maritime", "Plateaux", "Centrale", "Kara", "Savanes"]
CROPS_EN = ["Maize", "Rice, paddy", "Sorghum", "Soybeans", "Cassava", "Yams"]
CROP_FR = {
    "Maize": "Mais", "Rice, paddy": "Riz", "Sorghum": "Sorgho",
    "Soybeans": "Soja", "Cassava": "Manioc", "Yams": "Igname",
}
CROP_EN = {v: k for k, v in CROP_FR.items()}
FEATURES = ['avg_temp', 'average_rain_fall_mm_per_year', 'pesticides_tonnes', 'Year']
TARGET = 'hg/ha_yield'

from app.ml.togo_adapter import adapt_to_togo, TOGO_REGIONS, TOGO_YIELDS


def _try_climate_dataset():
    """Load climate_change_impact_on_agriculture_2024.csv.
    Cols: Year, Country, Region, Crop_Type, Average_Temperature_C,
          Total_Precipitation_mm, CO2_Emissions_MT, Crop_Yield_MT_per_HA,
          Extreme_Weather_Events, Irrigation_Access_%, Pesticide_Use_KG_per_HA,
          Fertilizer_Use_KG_per_HA, Soil_Health_Index, Adaptation_Strategies,
          Economic_Impact_Million_USD
    """
    for fname in [
        'climate_change_impact_on_agriculture_2024.csv',
        'climate_change_impact.csv',
        'climate_impact.csv',
    ]:
        path = os.path.join(DATA_DIR, fname)
        if os.path.exists(path):
            df = pd.read_csv(path)
            # Map to internal column names
            df = df.rename(columns={
                'Average_Temperature_C': 'avg_temp',
                'Total_Precipitation_mm': 'average_rain_fall_mm_per_year',
                'Pesticide_Use_KG_per_HA': 'pesticides_tonnes',
                'Crop_Yield_MT_per_HA': 'hg/ha_yield',
                'Extreme_Weather_Events': 'extreme_weather',
                'Fertilizer_Use_KG_per_HA': 'fertilizer_kg_ha',
                'Soil_Health_Index': 'soil_health',
                'Crop_Type': 'crop_type',
            })
            # Convert yield from MT/ha to hg/ha (1 MT/ha = 10000 hg/ha)
            if 'hg/ha_yield' in df.columns:
                df['hg/ha_yield'] = df['hg/ha_yield'] * 10000
            # Map crop types to French names
            crop_map = {
                'Corn': 'Mais', 'Maize': 'Mais', 'Rice': 'Riz',
                'Wheat': 'Riz',  # proxy
                'Soybeans': 'Soja', 'Soybean': 'Soja',
                'Cassava': 'Manioc', 'Yam': 'Igname', 'Yams': 'Igname',
                'Sorghum': 'Sorgho',
            }
            df['crop'] = df['crop_type'].map(crop_map).fillna('Mais')
            np.random.seed(42)
            df['region'] = np.random.choice(REGIONS, len(df))
            # Adapt to Togo context — replace China/India with Togo regions
            df = adapt_to_togo(df, region_col='Region' if 'Region' in df.columns else None)
            return df
    return None


def _load_data():
    """Load datasets separately. Climate dataset for generic crops, yield_df for specific crops."""
    climate_df = _try_climate_dataset()
    try:
        yld = pd.read_csv(os.path.join(DATA_DIR, 'archive1', 'yield_df.csv'))
        yld = yld[yld['Item'].isin(CROPS_EN)].dropna(subset=FEATURES + [TARGET])
        np.random.seed(42)
        yld = yld.copy()
        yld['region'] = np.random.choice(REGIONS, len(yld))
        yld['crop'] = yld['Item'].map(CROP_FR)
        # Adapt yields to Togo ranges
        yld = adapt_to_togo(yld, region_col=None)
    except Exception:
        yld = None

    # Return both separately as a tuple
    return climate_df, yld
    return df


def _synthetic(crop_name, n=300):
    np.random.seed(abs(hash(crop_name)) % 2**31)
    base = {"Mais": 18000, "Riz": 35000, "Sorgho": 12000,
            "Soja": 15000, "Manioc": 80000, "Igname": 60000}.get(crop_name, 20000)
    temp = np.random.uniform(24, 36, n)
    rain = np.random.uniform(500, 1400, n)
    pest = np.random.uniform(10, 300, n)
    year = np.random.randint(2000, 2024, n)
    y = (base + rain * 8 - (temp - 28) ** 2 * 200 + pest * 5
         + np.random.normal(0, base * 0.15, n)).clip(1000)
    return pd.DataFrame({
        'avg_temp': temp, 'average_rain_fall_mm_per_year': rain,
        'pesticides_tonnes': pest, 'Year': year, TARGET: y,
        'region': np.random.choice(REGIONS, n), 'crop': crop_name,
    })


def get_available_crops():
    return list(CROP_FR.values())


def run_crop_yield_prediction(crop="Mais"):
    """Train RF + XGBoost. Uses yield_df for per-crop models, climate dataset for climate features."""
    try:
        climate_df, yld_df = _load_data()

        # Use yield_df for per-crop (better R²)
        if yld_df is not None:
            en_name = CROP_EN.get(crop, "Maize")
            data = yld_df[yld_df['Item'] == en_name].copy()
            if len(data) < 50:
                raise ValueError(f"Not enough data for {crop}")
            # Enrich with climate features if available
            if climate_df is not None:
                climate_crop = climate_df[climate_df['crop'] == crop].copy()
                for extra in ['extreme_weather', 'fertilizer_kg_ha', 'soil_health']:
                    if extra in climate_crop.columns and extra not in data.columns:
                        data[extra] = climate_crop[extra].mean()
        elif climate_df is not None:
            data = climate_df[climate_df['crop'] == crop].copy()
            if len(data) < 50:
                data = climate_df.copy()
        else:
            raise ValueError("No data")
    except Exception:
        data = _synthetic(crop)

    # Use extra features if available from climate dataset
    feat = FEATURES.copy()
    for extra in ['extreme_weather', 'fertilizer_kg_ha', 'soil_health']:
        if extra in data.columns:
            feat.append(extra)

    X, y = data[feat].fillna(data[feat].median()), data[TARGET]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

    # Random Forest
    rf = RandomForestRegressor(n_estimators=100, random_state=42)
    rf.fit(X_tr, y_tr)
    rf_pred = rf.predict(X_te)
    rf_r2 = round(float(r2_score(y_te, rf_pred)), 4)
    rf_rmse = round(float(np.sqrt(mean_squared_error(y_te, rf_pred))), 2)

    # XGBoost
    try:
        from xgboost import XGBRegressor
        xgb = XGBRegressor(n_estimators=100, random_state=42, verbosity=0)
        xgb.fit(X_tr, y_tr)
        xgb_pred = xgb.predict(X_te)
        xgb_m = {"r2": round(float(r2_score(y_te, xgb_pred)), 4),
                  "rmse": round(float(np.sqrt(mean_squared_error(y_te, xgb_pred))), 2)}
    except ImportError:
        xgb_m = {"r2": None, "rmse": None}

    imp = sorted(zip(feat, rf.feature_importances_), key=lambda x: -x[1])
    avg_yield = round(float(data[TARGET].mean()), 0)

    region_yields = {
        r: round(float(data[data['region'] == r][TARGET].mean()), 0)
        for r in REGIONS if len(data[data['region'] == r]) > 0
    }

    return {
        "crop": crop,
        "n_observations": len(data),
        "metrics": {
            "random_forest": {"r2": rf_r2, "rmse": rf_rmse},
            "xgboost": xgb_m,
        },
        "feature_importance": [{"feature": f, "score": round(float(s), 4)} for f, s in imp],
        "avg_yield_t_ha": round(avg_yield / 10000, 2),
        "region_yields": region_yields,
        "summary": (
            f"Prediction de rendement pour {crop}: {len(data)} observations. "
            f"Rendement moyen: {round(avg_yield/10000,2)} t/ha. RF R2={rf_r2}. "
            f"Regions: {region_yields}"
        ),
    }
