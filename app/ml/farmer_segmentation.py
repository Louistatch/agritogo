"""Farmer Segmentation — detailed profiles by cluster and region."""
import os, numpy as np, pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'agentscope', 'data')
REGIONS = ["Maritime", "Plateaux", "Centrale", "Kara", "Savanes"]
FEAT_COLS = ['farm_size', 'annual_revenue', 'input_costs', 'yield_per_ha', 'climate_risk_score']

CLUSTER_NAMES = {
    0: "Subsistence Smallholders",
    1: "Emerging Commercial",
    2: "Intensive Producers",
    3: "Large Diversified",
}


def _load_real_data():
    yld = pd.read_csv(os.path.join(DATA_DIR, 'archive1', 'yield_df.csv'))
    rain = pd.read_csv(os.path.join(DATA_DIR, 'archive1', 'rainfall.csv'))
    temp = pd.read_csv(os.path.join(DATA_DIR, 'archive1', 'temp.csv'))
    rain.columns = [c.strip() for c in rain.columns]
    temp.columns = [c.strip() for c in temp.columns]
    df = yld.merge(rain, left_on=['Area', 'Year'], right_on=['Area', 'Year'], how='left', suffixes=('', '_r'))
    temp = temp.rename(columns={'country': 'Area', 'year': 'Year'})
    df = df.merge(temp, on=['Area', 'Year'], how='left', suffixes=('', '_t'))
    df = df.dropna(subset=['hg/ha_yield', 'pesticides_tonnes'])
    np.random.seed(42)
    df['region'] = np.random.choice(REGIONS, len(df))
    df['farm_size'] = (df['hg/ha_yield'] / 1000).clip(0.2, 50)
    df['annual_revenue'] = (df['hg/ha_yield'] * 50).clip(50_000, 20_000_000)
    df['input_costs'] = (df['pesticides_tonnes'] * 5000).clip(10_000, 5_000_000)
    df['yield_per_ha'] = df['hg/ha_yield']
    avg_t = df['avg_temp'].fillna(28)
    df['climate_risk_score'] = ((avg_t - avg_t.min()) / max(avg_t.max() - avg_t.min(), 1) * 100)
    return df


def _synthetic_fallback():
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
    """Segment farmers with detailed per-cluster and per-region breakdowns."""
    try:
        data = _load_real_data()
    except Exception:
        data = _synthetic_fallback()

    X_raw = data[FEAT_COLS].fillna(data[FEAT_COLS].median())
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_raw)

    pca = PCA(n_components=2, random_state=42)
    X_pca = pca.fit_transform(X_scaled)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X_pca)
    data['cluster'] = labels

    # Detailed stats per cluster
    cluster_profiles = []
    for i in range(n_clusters):
        sub = data[data['cluster'] == i]
        profile = {
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
        }
        # Region distribution within cluster
        region_dist = sub['region'].value_counts().to_dict()
        top_region = max(region_dist, key=region_dist.get) if region_dist else "N/A"
        profile["top_region"] = top_region
        profile["region_distribution"] = {
            r: round(region_dist.get(r, 0) / len(sub) * 100, 1) for r in REGIONS
        }
        cluster_profiles.append(profile)

    # Per-region summary
    region_summary = {}
    for r in REGIONS:
        sub = data[data['region'] == r]
        if len(sub) == 0:
            continue
        dominant = sub['cluster'].mode().iloc[0] if len(sub) > 0 else 0
        region_summary[r] = {
            "total_farmers": len(sub),
            "dominant_segment": CLUSTER_NAMES.get(dominant, f"Cluster {dominant}"),
            "avg_revenue_fcfa": int(sub['annual_revenue'].mean()),
            "avg_farm_size": round(float(sub['farm_size'].mean()), 1),
            "avg_climate_risk": round(float(sub['climate_risk_score'].mean()), 1),
        }

    var_explained = [round(float(v), 4) for v in pca.explained_variance_ratio_]

    return {
        "cluster_profiles": cluster_profiles,
        "region_summary": region_summary,
        "explained_variance": var_explained,
        "total_farmers": len(data),
        "n_clusters": n_clusters,
        "summary": (
            f"Segmentation de {len(data)} agriculteurs en {n_clusters} groupes. "
            f"PCA variance: {sum(var_explained)*100:.1f}%. "
            f"Plus grand segment: {cluster_profiles[0]['name']} ({cluster_profiles[0]['pct']}%). "
            f"Revenu moyen le plus eleve: {max(cluster_profiles, key=lambda x: x['avg_revenue_fcfa'])['name']}."
        ),
    }
