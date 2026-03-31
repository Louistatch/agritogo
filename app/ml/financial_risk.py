"""Agricultural Financial Risk Assessment — detailed by region, size, factors."""
import os, numpy as np, pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'agentscope', 'data')
REGION_MAP = {"East": "Maritime", "West": "Plateaux", "North": "Kara",
              "South": "Centrale", "Central": "Savanes"}
FEATURES = ['Loan_Amount', 'Debt_to_Equity', 'Avg_Temperature',
            'Rainfall', 'Drought_Index', 'Flood_Risk_Score']


def _load_real_data():
    df = pd.read_csv(os.path.join(DATA_DIR, 'AgriRiskFin_Dataset.csv'))
    df['Region'] = df['Region'].map(REGION_MAP).fillna('Maritime')
    df['default'] = (df['Financial_Risk_Level'] == 'High').astype(int)
    for col in ['Revenue', 'Expenses', 'Loan_Amount']:
        df[col] = df[col] * 1000
    return df


def _synthetic_fallback():
    np.random.seed(42)
    n = 1000
    regions = list(REGION_MAP.values())
    sizes = ['Small', 'Medium', 'Large']
    df = pd.DataFrame({
        'Loan_Amount': np.random.uniform(50_000, 2_000_000, n),
        'Debt_to_Equity': np.random.uniform(0.1, 3.0, n),
        'Avg_Temperature': np.random.uniform(20, 42, n),
        'Rainfall': np.random.uniform(50, 400, n),
        'Drought_Index': np.random.uniform(0, 1, n),
        'Flood_Risk_Score': np.random.uniform(0, 1, n),
        'Region': np.random.choice(regions, n),
        'Enterprise_Size': np.random.choice(sizes, n),
        'Revenue': np.random.uniform(100_000, 1_000_000, n),
        'Expenses': np.random.uniform(80_000, 800_000, n),
    })
    risk = (df['Loan_Amount'] / 2e6 * 2 + df['Drought_Index']
            - df['Rainfall'] / 400 + np.random.normal(0, 0.3, n))
    df['default'] = (risk > np.percentile(risk, 80)).astype(int)
    return df


def run_risk_assessment():
    """Train RF classifier with detailed breakdowns by region and size."""
    np.random.seed(42)
    try:
        data = _load_real_data()
    except Exception:
        data = _synthetic_fallback()

    X, y = data[FEATURES], data['default']

    # Oversample minority
    minority = X[y == 1]
    minority_y = y[y == 1]
    n_need = len(y[y == 0]) - len(minority_y)
    if n_need > 0 and len(minority) > 0:
        idx = np.random.choice(len(minority), size=n_need, replace=True)
        X_bal = pd.concat([X, minority.iloc[idx]], ignore_index=True)
        y_bal = pd.concat([y, minority_y.iloc[idx]], ignore_index=True)
    else:
        X_bal, y_bal = X, y

    X_train, X_test, y_train, y_test = train_test_split(X_bal, y_bal, test_size=0.2, random_state=42)
    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)

    # Global metrics
    f1 = round(float(f1_score(y_test, y_pred)), 4)
    metrics = {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
        "f1": f1,
    }

    # Feature importance
    imp = sorted(zip(FEATURES, clf.feature_importances_), key=lambda x: -x[1])

    # Risk scoring on ORIGINAL data
    proba = clf.predict_proba(data[FEATURES])[:, 1]
    data['risk_score'] = proba
    data['risk_level'] = np.where(proba < 0.3, "low", np.where(proba < 0.6, "medium", "high"))

    # Global distribution
    risk_dist = data['risk_level'].value_counts().to_dict()

    # BREAKDOWN BY REGION
    risk_by_region = {}
    for region in data['Region'].unique():
        sub = data[data['Region'] == region]
        dist = sub['risk_level'].value_counts().to_dict()
        risk_by_region[region] = {
            "total": len(sub),
            "high_pct": round(dist.get('high', 0) / len(sub) * 100, 1),
            "medium_pct": round(dist.get('medium', 0) / len(sub) * 100, 1),
            "low_pct": round(dist.get('low', 0) / len(sub) * 100, 1),
            "avg_loan_fcfa": int(sub['Loan_Amount'].mean()),
            "avg_risk_score": round(float(sub['risk_score'].mean()), 3),
        }

    # BREAKDOWN BY ENTERPRISE SIZE
    risk_by_size = {}
    if 'Enterprise_Size' in data.columns:
        for size in data['Enterprise_Size'].unique():
            sub = data[data['Enterprise_Size'] == size]
            dist = sub['risk_level'].value_counts().to_dict()
            risk_by_size[size] = {
                "total": len(sub),
                "high_pct": round(dist.get('high', 0) / len(sub) * 100, 1),
                "avg_loan_fcfa": int(sub['Loan_Amount'].mean()),
                "avg_risk_score": round(float(sub['risk_score'].mean()), 3),
            }

    # TOP RISK FACTORS per region
    top_risk_region = max(risk_by_region.items(), key=lambda x: x[1]['high_pct'])
    safest_region = min(risk_by_region.items(), key=lambda x: x[1]['high_pct'])

    summary = (
        f"Analyse de risque sur {len(data)} dossiers. F1={f1}. "
        f"Region la plus risquee: {top_risk_region[0]} ({top_risk_region[1]['high_pct']}% haut risque). "
        f"Region la plus sure: {safest_region[0]} ({safest_region[1]['high_pct']}% haut risque). "
        f"Facteur principal: {imp[0][0]} (importance {imp[0][1]:.3f})."
    )

    return {
        "metrics": metrics,
        "feature_importance": [{"feature": f, "score": round(float(s), 4)} for f, s in imp],
        "risk_distribution": risk_dist,
        "risk_by_region": risk_by_region,
        "risk_by_size": risk_by_size,
        "riskiest_region": top_risk_region[0],
        "safest_region": safest_region[0],
        "total_dossiers": len(data),
        "summary": summary,
    }
