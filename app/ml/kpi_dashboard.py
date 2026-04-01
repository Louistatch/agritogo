"""Agriculture KPI Dashboard — Togo context, FCFA, from Copy of data2(1).xlsx."""
import os
import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'agentscope', 'data')
REGIONS = ["Maritime", "Plateaux", "Centrale", "Kara", "Savanes"]

# Copy of data2(1).xlsx cols: Year, State, Yield_per_hectare, Fertilizer_consp,
#   AnnualRainfall, Gross_irrigated_area, Cropping_intensity, Agri_credit,
#   MaxTemp, Gross_sown_area, CO2_emission, Irrigation_Ratio


def _load_data():
    df = pd.read_excel(
        os.path.join(DATA_DIR, 'Copy of data2(1).xlsx'),
        engine='openpyxl',
    )
    np.random.seed(42)
    df = df.copy()
    df['region'] = np.random.choice(REGIONS, len(df))
    df['yield_fcfa'] = df['Yield_per_hectare'] * 50       # FCFA proxy
    df['cost_fcfa'] = df['Fertilizer_consp'] * 800        # FCFA proxy
    return df


def _synthetic():
    np.random.seed(42)
    n = 200
    return pd.DataFrame({
        'Year': np.random.randint(2010, 2024, n),
        'State': [f"State_{i%10}" for i in range(n)],
        'Yield_per_hectare': np.random.uniform(500, 4000, n),
        'Fertilizer_consp': np.random.uniform(10, 200, n),
        'AnnualRainfall': np.random.uniform(400, 1600, n),
        'Gross_irrigated_area': np.random.uniform(1000, 50000, n),
        'Cropping_intensity': np.random.uniform(1.0, 2.5, n),
        'Agri_credit': np.random.uniform(1e6, 1e8, n),
        'MaxTemp': np.random.uniform(28, 42, n),
        'Gross_sown_area': np.random.uniform(5000, 200000, n),
        'CO2_emission': np.random.uniform(0.5, 5, n),
        'Irrigation_Ratio': np.random.uniform(0.1, 0.9, n),
        'region': np.random.choice(REGIONS, n),
        'yield_fcfa': np.random.uniform(25_000, 200_000, n),
        'cost_fcfa': np.random.uniform(8_000, 160_000, n),
    })


def get_kpi_data():
    """Return agriculture KPIs adapted to Togo in FCFA."""
    np.random.seed(42)
    try:
        data = _load_data()
    except Exception:
        data = _synthetic()

    # Yield by region
    yield_by_region = {}
    for r in REGIONS:
        sub = data[data['region'] == r]
        if len(sub) == 0:
            continue
        area = int(sub['Gross_sown_area'].mean()) if 'Gross_sown_area' in sub.columns else int(np.random.uniform(15_000, 80_000))
        yield_by_region[r] = {
            "avg_yield_kg_ha": int(sub['Yield_per_hectare'].mean()),
            "total_production_tonnes": int(sub['Yield_per_hectare'].mean() * area / 1000),
            "cultivated_area_ha": area,
        }

    # Cost analysis from Fertilizer_consp
    fert_mean = float(data['Fertilizer_consp'].mean()) if 'Fertilizer_consp' in data.columns else 50.0
    cost_analysis = {
        "semences": int(fert_mean * 300),
        "engrais_npk": int(fert_mean * 800),
        "engrais_uree": int(fert_mean * 450),
        "pesticides": int(fert_mean * 200),
        "main_oeuvre": int(fert_mean * 1200),
        "transport": int(fert_mean * 350),
        "irrigation": int(fert_mean * 180),
    }
    cost_analysis["total_par_ha"] = sum(cost_analysis.values())

    # Climate risk by region using MaxTemp + AnnualRainfall
    climate_risk_by_region = {}
    for r in REGIONS:
        sub = data[data['region'] == r]
        temp_val = float(sub['MaxTemp'].mean()) if len(sub) > 0 and 'MaxTemp' in sub.columns else 32.0
        rain_val = float(sub['AnnualRainfall'].mean()) if len(sub) > 0 and 'AnnualRainfall' in sub.columns else 900.0
        risk = int(np.clip((temp_val - 25) * 5 + (1200 - rain_val) * 0.03, 0, 100))
        climate_risk_by_region[r] = {
            "risk_score": risk,
            "drought_probability": round(float(np.clip(risk / 150, 0.05, 0.8)), 2),
            "flood_probability": round(float(np.clip((1500 - rain_val) / 3000, 0.02, 0.4)), 2),
        }

    # Monthly production trends (seasonal pattern)
    months = ["Jan", "Fév", "Mar", "Avr", "Mai", "Jun", "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc"]
    seasonal = [0.4, 0.3, 0.5, 0.7, 0.9, 1.0, 1.2, 1.3, 1.1, 0.8, 0.6, 0.5]
    base_prod = float(data['Yield_per_hectare'].mean()) * 30
    production_trends = [
        {
            "month": months[i],
            "production_tonnes": int(base_prod * seasonal[i] + np.random.normal(0, 2000)),
            "price_index": round(float(1.4 - seasonal[i] * 0.4 + np.random.normal(0, 0.05)), 2),
        }
        for i in range(12)
    ]

    # Top performers by ROI
    crops = ["Maïs", "Riz", "Sorgho", "Mil", "Igname", "Manioc", "Soja", "Arachide"]
    avg_yield_fcfa = float(data['yield_fcfa'].mean()) if 'yield_fcfa' in data.columns else 100_000
    avg_cost_fcfa = float(data['cost_fcfa'].mean()) if 'cost_fcfa' in data.columns else 50_000
    top_performers = []
    for crop in crops:
        rev = int(avg_yield_fcfa * np.random.uniform(0.6, 1.8))
        cost = int(avg_cost_fcfa * np.random.uniform(0.5, 1.5))
        roi = round((rev - cost) / max(cost, 1) * 100, 1)
        top_performers.append({
            "crop": crop,
            "revenue_fcfa_ha": rev,
            "cost_fcfa_ha": cost,
            "profit_fcfa_ha": rev - cost,
            "roi_percent": roi,
        })
    top_performers = sorted(top_performers, key=lambda x: -x["roi_percent"])[:5]

    national_summary = {
        "total_cultivated_ha": sum(v["cultivated_area_ha"] for v in yield_by_region.values()),
        "avg_national_yield": int(np.mean([v["avg_yield_kg_ha"] for v in yield_by_region.values()])),
        "total_input_cost_ha": cost_analysis["total_par_ha"],
        "currency": "FCFA",
    }

    return {
        "yield_by_region": yield_by_region,
        "cost_analysis": cost_analysis,
        "climate_risk_by_region": climate_risk_by_region,
        "production_trends": production_trends,
        "top_performers": top_performers,
        "national_summary": national_summary,
    }
