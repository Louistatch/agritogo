"""Agricultural Financial Risk Assessment — RF classifier with region/size breakdowns."""
import os
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'agentscope', 'data')

# AgriRiskFin_Dataset.csv cols: Enterprise_ID, Region, Enterprise_Size, Revenue,
#   Expenses, Loan_Amount, Debt_to_Equity, Avg_Temperature, Rainfall, Drought_Index,
#   Flood_Risk_Score, Commodity_Price_Index, Input_Cost_Index, Policy_Support_Score,
#   Quarter, Net_Profit, Financial_Risk_Level
REGION_MAP = {"East": "Maritime", "West": "Plateaux", "North": "Kara",
              "South": "Centrale", "Central": "Savanes"}
FEATURES = ['Loan_Amount', 'Debt_to_Equity', 'Avg_Temperature',
            'Rainfall', 'Drought_Index', 'Flood_Risk_Score']


def _load_data():
    df = pd.read_csv(os.path.join(DATA_DIR, 'AgriRiskFin_Dataset.csv'))
    df['Region'] = df['Region'].map(REGION_MAP).fillna('Maritime')
    # Target: Financial_Risk_Level == 'High' → 1, else 0
    df['default'] = (df['Financial_Risk_Level'] == 'High').astype(int)
    # Convert monetary cols to FCFA (*1000)
    for col in ['Revenue', 'Expenses', 'Loan_Amount']:
        if col in df.columns:
            df[col] = df[col] * 1000
    return df


def _synthetic():
    np.random.seed(42)
    n = 1000
    regions = list(REGION_MAP.values())
    df = pd.DataFrame({
        'Loan_Amount': np.random.uniform(50_000, 2_000_000, n),
        'Debt_to_Equity': np.random.uniform(0.1, 3.0, n),
        'Avg_Temperature': np.random.uniform(20, 42, n),
        'Rainfall': np.random.uniform(50, 400, n),
        'Drought_Index': np.random.uniform(0, 1, n),
        'Flood_Risk_Score': np.random.uniform(0, 1, n),
        'Region': np.random.choice(regions, n),
        'Enterprise_Size': np.random.choice(['Small', 'Medium', 'Large'], n),
        'Revenue': np.random.uniform(100_000, 1_000_000, n),
        'Expenses': np.random.uniform(80_000, 800_000, n),
        'Net_Profit': np.random.uniform(-50_000, 200_000, n),
        'Commodity_Price_Index': np.random.uniform(80, 120, n),
    })
    risk = (df['Loan_Amount'] / 2e6 * 2 + df['Drought_Index']
            - df['Rainfall'] / 400 + np.random.normal(0, 0.3, n))
    df['default'] = (risk > np.percentile(risk, 80)).astype(int)
    df['Financial_Risk_Level'] = np.where(
        df['default'] == 1, 'High',
        np.where(risk > np.percentile(risk, 50), 'Medium', 'Low')
    )
    return df


def run_risk_assessment():
    """Train RF classifier; return metrics, feature importance, region/size breakdowns."""
    np.random.seed(42)
    try:
        data = _load_data()
    except Exception:
        data = _synthetic()

    X, y = data[FEATURES], data['default']

    # Oversample minority class
    minority_X, minority_y = X[y == 1], y[y == 1]
    n_need = len(y[y == 0]) - len(minority_y)
    if n_need > 0 and len(minority_X) > 0:
        idx = np.random.choice(len(minority_X), size=n_need, replace=True)
        X_bal = pd.concat([X, minority_X.iloc[idx]], ignore_index=True)
        y_bal = pd.concat([y, minority_y.iloc[idx]], ignore_index=True)
    else:
        X_bal, y_bal = X, y

    X_tr, X_te, y_tr, y_te = train_test_split(X_bal, y_bal, test_size=0.2, random_state=42)
    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X_tr, y_tr)
    y_pred = clf.predict(X_te)

    metrics = {
        "accuracy": round(float(accuracy_score(y_te, y_pred)), 4),
        "precision": round(float(precision_score(y_te, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_te, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_te, y_pred, zero_division=0)), 4),
    }

    imp = sorted(zip(FEATURES, clf.feature_importances_), key=lambda x: -x[1])

    # Score original data
    proba = clf.predict_proba(data[FEATURES])[:, 1]
    data = data.copy()
    data['risk_score'] = proba
    data['risk_level'] = np.where(proba < 0.3, 'low', np.where(proba < 0.6, 'medium', 'high'))

    risk_distribution = data['risk_level'].value_counts().to_dict()

    # Breakdown by region
    risk_by_region = {}
    for region in sorted(data['Region'].unique()):
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

    # Breakdown by enterprise size
    risk_by_size = {}
    if 'Enterprise_Size' in data.columns:
        for size in sorted(data['Enterprise_Size'].unique()):
            sub = data[data['Enterprise_Size'] == size]
            dist = sub['risk_level'].value_counts().to_dict()
            risk_by_size[size] = {
                "total": len(sub),
                "high_pct": round(dist.get('high', 0) / len(sub) * 100, 1),
                "avg_loan_fcfa": int(sub['Loan_Amount'].mean()),
                "avg_risk_score": round(float(sub['risk_score'].mean()), 3),
            }

    riskiest = max(risk_by_region.items(), key=lambda x: x[1]['high_pct'])
    safest = min(risk_by_region.items(), key=lambda x: x[1]['high_pct'])

    return {
        "metrics": metrics,
        "feature_importance": [{"feature": f, "score": round(float(s), 4)} for f, s in imp],
        "risk_distribution": risk_distribution,
        "risk_by_region": risk_by_region,
        "risk_by_size": risk_by_size,
        "riskiest_region": riskiest[0],
        "safest_region": safest[0],
        "total_dossiers": len(data),
        "summary": (
            f"Analyse de risque sur {len(data)} dossiers. F1={metrics['f1']}. "
            f"Region la plus risquee: {riskiest[0]} ({riskiest[1]['high_pct']}% haut risque). "
            f"Region la plus sure: {safest[0]} ({safest[1]['high_pct']}% haut risque). "
            f"Facteur principal: {imp[0][0]} (importance {imp[0][1]:.3f})."
        ),
    }
