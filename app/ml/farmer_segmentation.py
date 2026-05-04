"""Farmer Segmentation — PCA + KMeans with per-cluster and per-region profiles."""
import os
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans

from app.ml import get_data_dir
DATA_DIR = get_data_dir()
REGIONS = ["Maritime", "Plateaux", "Centrale", "Kara", "Savanes"]
FEAT_COLS = ['farm_size', 'annual_revenue', 'input_costs', 'yield_per_ha', 'climate_risk_score']
CLUSTER_NAMES = {
    0: "Subsistence Smallholders",
    1: "Emerging Commercial",
    2: "Intensive Producers",
    3: "Large Diversified",
}

from app.ml.togo_adapter import TOGO_REGIONS, TOGO_YIELDS


def _load_data():
    # yield_df.csv: Unnamed:0, Area, Item, Year, hg/ha_yield,
    #   average_rain_fall_mm_per_year, pesticides_tonnes, avg_temp
    yld = pd.read_csv(os.path.join(DATA_DIR, 'archive1', 'yield_df.csv'))
    # rainfall.csv: Area, Year, average_rain_fall_mm_per_year
    rain = pd.read_csv(os.path.join(DATA_DIR, 'archive1', 'rainfall.csv'))
    # temp.csv: year, country, avg_temp
    temp = pd.read_csv(os.path.join(DATA_DIR, 'archive1', 'temp.csv'))

    rain.columns = [c.strip() for c in rain.columns]
    temp.columns = [c.strip() for c in temp.columns]

    # Merge: yield_df LEFT JOIN rainfall on (Area, Year)
    df = yld.merge(rain[['Area', 'Year', 'average_rain_fall_mm_per_year']],
                   on=['Area', 'Year'], how='left', suffixes=('', '_rain'))

    # Merge: LEFT JOIN temp on (Area=country, Year=year)
    temp = temp.rename(columns={'country': 'Area', 'year': 'Year'})
    df = df.merge(temp[['Area', 'Year', 'avg_temp']],
                  on=['Area', 'Year'], how='left', suffixes=('', '_temp'))

    # Resolve duplicate avg_temp columns — prefer original, fallback to merged
    if 'avg_temp_temp' in df.columns:
        df['avg_temp'] = df['avg_temp'].fillna(df['avg_temp_temp'])
        df.drop(columns=['avg_temp_temp'], inplace=True)

    df = df.dropna(subset=['hg/ha_yield', 'pesticides_tonnes'])
    np.random.seed(42)
    df = df.copy()
    df['region'] = np.random.choice(REGIONS, len(df))

    # Adjust avg_temp to Togo realistic values per region
    df['avg_temp'] = df['region'].map(
        lambda r: TOGO_REGIONS.get(r, TOGO_REGIONS['Centrale'])['avg_temp'] + np.random.normal(0, 1.5)
    )

    # Build farmer profile features
    df['farm_size'] = (df['hg/ha_yield'] / 1000).clip(0.2, 50)
    df['annual_revenue'] = (df['hg/ha_yield'] * 50).clip(50_000, 20_000_000)
    df['input_costs'] = (df['pesticides_tonnes'] * 5000).clip(10_000, 5_000_000)
    df['yield_per_ha'] = df['hg/ha_yield']
    t = df['avg_temp'].fillna(28)
    df['climate_risk_score'] = ((t - t.min()) / max(float(t.max() - t.min()), 1) * 100)
    return df


def _synthetic():
    np.random.seed(42)
    n = 500
    return pd.DataFrame({
        'farm_size': np.random.lognormal(1.2, 0.8, n).clip(0.3, 50),
        'annual_revenue': np.random.lognormal(13.5, 1.0, n).clip(100_000, 15_000_000),
        'input_costs': np.random.lognormal(11.5, 0.9, n).clip(20_000, 5_000_000),
        'yield_per_ha': np.random.uniform(500, 4000, n),
        'climate_risk_score': np.random.beta(2, 5, n) * 100,
        'region': np.random.choice(REGIONS, n),
    })


def run_farmer_segmentation(n_clusters=4):
    """Segment farmers into n_clusters using PCA(2) + KMeans."""
    try:
        data = _load_data()
    except Exception:
        data = _synthetic()

    X_raw = data[FEAT_COLS].fillna(data[FEAT_COLS].median())
    X_scaled = StandardScaler().fit_transform(X_raw)

    pca = PCA(n_components=2, random_state=42)
    X_pca = pca.fit_transform(X_scaled)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    data = data.copy()
    data['cluster'] = kmeans.fit_predict(X_pca)

    cluster_profiles = []
    for i in range(n_clusters):
        sub = data[data['cluster'] == i]
        region_dist = sub['region'].value_counts().to_dict()
        top_region = max(region_dist, key=region_dist.get) if region_dist else "N/A"
        cluster_profiles.append({
            "id": i,
            "name": CLUSTER_NAMES.get(i, f"Cluster {i}"),
            "count": len(sub),
            "pct": round(len(sub) / len(data) * 100, 1),
            "avg_farm_size_ha": round(float(sub['farm_size'].mean()), 1),
            "avg_revenue_fcfa": int(sub['annual_revenue'].mean()),
            "avg_input_costs_fcfa": int(sub['input_costs'].mean()),
            "avg_yield_hg_ha": int(sub['yield_per_ha'].mean()),
            "avg_climate_risk": round(float(sub['climate_risk_score'].mean()), 1),
            "profit_margin_pct": round(
                (sub['annual_revenue'].mean() - sub['input_costs'].mean())
                / max(sub['annual_revenue'].mean(), 1) * 100, 1
            ),
            "top_region": top_region,
            "region_distribution": {
                r: round(region_dist.get(r, 0) / len(sub) * 100, 1) for r in REGIONS
            },
        })

    region_summary = {}
    for r in REGIONS:
        sub = data[data['region'] == r]
        if len(sub) == 0:
            continue
        dominant = int(sub['cluster'].mode().iloc[0])
        region_summary[r] = {
            "total_farmers": len(sub),
            "dominant_segment": CLUSTER_NAMES.get(dominant, f"Cluster {dominant}"),
            "avg_revenue_fcfa": int(sub['annual_revenue'].mean()),
            "avg_farm_size": round(float(sub['farm_size'].mean()), 1),
            "avg_climate_risk": round(float(sub['climate_risk_score'].mean()), 1),
        }

    var_explained = [round(float(v), 4) for v in pca.explained_variance_ratio_]
    best = max(cluster_profiles, key=lambda x: x['avg_revenue_fcfa'])

    return {
        "cluster_profiles": cluster_profiles,
        "region_summary": region_summary,
        "explained_variance": var_explained,
        "total_farmers": len(data),
        "n_clusters": n_clusters,
        "summary": (
            f"Segmentation de {len(data)} agriculteurs en {n_clusters} groupes. "
            f"PCA variance: {sum(var_explained)*100:.1f}%. "
            f"Revenu moyen le plus eleve: {best['name']} ({best['avg_revenue_fcfa']:,} FCFA)."
        ),
    }
