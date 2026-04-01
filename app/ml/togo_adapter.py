"""Togo Data Adapter — transforms global datasets to Togo context.

Maps foreign countries/regions to Togo's 5 regions with realistic
climate and agricultural parameters for each region.
"""
import numpy as np
import pandas as pd

# ── Togo Regions with realistic parameters ────────────────
REGIONS = ["Maritime", "Plateaux", "Centrale", "Kara", "Savanes"]

TOGO_REGIONS = {
    "Maritime": {
        "avg_temp": 27.5,       # Coastal, humid
        "rainfall_mm": 1200,    # High rainfall
        "climate_risk": 35,
        "drought_prob": 0.12,
        "flood_prob": 0.28,
        "main_crops": ["Mais", "Manioc", "Tomate", "Piment"],
        "soil_health": 72,
        "irrigation_pct": 18,
    },
    "Plateaux": {
        "avg_temp": 26.8,       # Moderate, two rainy seasons
        "rainfall_mm": 1100,
        "climate_risk": 30,
        "drought_prob": 0.10,
        "flood_prob": 0.22,
        "main_crops": ["Mais", "Igname", "Manioc", "Soja"],
        "soil_health": 78,
        "irrigation_pct": 14,
    },
    "Centrale": {
        "avg_temp": 28.2,       # Transition zone
        "rainfall_mm": 950,
        "climate_risk": 48,
        "drought_prob": 0.22,
        "flood_prob": 0.15,
        "main_crops": ["Mais", "Sorgho", "Igname", "Arachide"],
        "soil_health": 65,
        "irrigation_pct": 10,
    },
    "Kara": {
        "avg_temp": 29.1,       # Sub-Saharan, one rainy season
        "rainfall_mm": 1050,
        "climate_risk": 55,
        "drought_prob": 0.28,
        "flood_prob": 0.12,
        "main_crops": ["Mais", "Sorgho", "Mil", "Soja"],
        "soil_health": 60,
        "irrigation_pct": 8,
    },
    "Savanes": {
        "avg_temp": 31.5,       # Sahel-influenced, dry
        "rainfall_mm": 750,
        "climate_risk": 72,
        "drought_prob": 0.45,
        "flood_prob": 0.08,
        "main_crops": ["Sorgho", "Mil", "Arachide", "Mais"],
        "soil_health": 48,
        "irrigation_pct": 5,
    },
}

# ── Togo crop yield ranges (hg/ha) ───────────────────────
TOGO_YIELDS = {
    "Mais":    {"min": 8000,  "max": 45000, "mean": 18000},
    "Riz":     {"min": 15000, "max": 60000, "mean": 32000},
    "Sorgho":  {"min": 5000,  "max": 25000, "mean": 12000},
    "Mil":     {"min": 4000,  "max": 20000, "mean": 10000},
    "Igname":  {"min": 40000, "max": 120000,"mean": 70000},
    "Manioc":  {"min": 50000, "max": 150000,"mean": 85000},
    "Soja":    {"min": 8000,  "max": 30000, "mean": 15000},
    "Arachide":{"min": 6000,  "max": 25000, "mean": 12000},
}

# ── Togo market prices (FCFA/kg) ─────────────────────────
TOGO_PRICES = {
    "Mais": 220, "Riz local": 450, "Sorgho": 200, "Mil": 250,
    "Haricot": 500, "Soja": 350, "Arachide": 400, "Igname": 300,
    "Manioc": 150, "Tomate": 600, "Piment": 800, "Oignon": 350,
}


def adapt_to_togo(df, region_col=None, n_per_region=None, seed=42):
    """Remap any dataset to Togo's 5 regions with realistic parameters.

    Args:
        df: Input DataFrame
        region_col: Column to replace with Togo regions (if None, adds 'region')
        n_per_region: If set, sample n rows per region
        seed: Random seed

    Returns:
        DataFrame with Togo region mapping and adjusted climate parameters
    """
    np.random.seed(seed)
    df = df.copy()

    # Assign Togo regions
    if region_col and region_col in df.columns:
        # Map existing regions to Togo regions
        unique_regions = df[region_col].unique()
        region_mapping = {}
        for i, r in enumerate(sorted(unique_regions)):
            region_mapping[r] = REGIONS[i % len(REGIONS)]
        df['region'] = df[region_col].map(region_mapping)
    else:
        # Distribute evenly across 5 regions
        df['region'] = np.random.choice(REGIONS, len(df))

    # Adjust climate parameters per region
    for col, param in [
        ('avg_temp', 'avg_temp'),
        ('Average_Temperature_C', 'avg_temp'),
        ('average_rain_fall_mm_per_year', 'rainfall_mm'),
        ('Total_Precipitation_mm', 'rainfall_mm'),
        ('Soil_Health_Index', 'soil_health'),
        ('soil_health', 'soil_health'),
    ]:
        if col in df.columns:
            df[col] = df['region'].map(
                lambda r: TOGO_REGIONS[r][param] + np.random.normal(0, TOGO_REGIONS[r][param] * 0.08)
            )

    # Adjust yield to Togo ranges if crop column exists
    for crop_col in ['crop', 'Crop_Type', 'Item']:
        if crop_col in df.columns and 'hg/ha_yield' in df.columns:
            def adjust_yield(row):
                crop = row.get('crop', row.get('Crop_Type', row.get('Item', 'Mais')))
                region = row.get('region', 'Centrale')
                togo_crop = crop if crop in TOGO_YIELDS else 'Mais'
                base = TOGO_YIELDS[togo_crop]['mean']
                # Climate adjustment
                r_params = TOGO_REGIONS.get(region, TOGO_REGIONS['Centrale'])
                rain_factor = r_params['rainfall_mm'] / 1000
                temp_factor = max(0.5, 1 - abs(r_params['avg_temp'] - 27) * 0.03)
                return base * rain_factor * temp_factor * np.random.uniform(0.8, 1.2)
            df['hg/ha_yield'] = df.apply(adjust_yield, axis=1)
            break

    return df


def get_region_profile(region):
    """Get full profile for a Togo region."""
    return TOGO_REGIONS.get(region, TOGO_REGIONS['Centrale'])


def get_togo_crop_yield(crop, region):
    """Get expected yield range for a crop in a Togo region."""
    base = TOGO_YIELDS.get(crop, TOGO_YIELDS['Mais'])
    r = TOGO_REGIONS.get(region, TOGO_REGIONS['Centrale'])
    factor = r['rainfall_mm'] / 1000 * max(0.5, 1 - abs(r['avg_temp'] - 27) * 0.03)
    return {
        "min": round(base['min'] * factor),
        "max": round(base['max'] * factor),
        "expected": round(base['mean'] * factor),
    }
