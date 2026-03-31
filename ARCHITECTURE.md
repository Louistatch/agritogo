# AgriTogo — Decision Intelligence Engine
## Architecture Système v2.0

```
┌─────────────────────────────────────────────────────────────┐
│                    🌾 AgriTogo Platform                      │
│              "AI-Powered Agricultural Market                 │
│           Intelligence for Emerging Markets"                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ 🧑‍🌾 Farmer   │    │ 🤝 Coop/NGO  │    │ 🏛️ Gov/B2B   │   │
│  │   Mobile     │    │  Dashboard   │    │   API/Reports│   │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘   │
│         │                   │                   │           │
│  ┌──────▼───────────────────▼───────────────────▼───────┐   │
│  │              HTMX Interface Layer                     │   │
│  │   Chat │ Decision Engine │ Prix │ ML │ Admin          │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │           🧠 DECISION INTELLIGENCE ENGINE             │   │
│  │                                                       │   │
│  │  ┌─────────────────────────────────────────────────┐  │   │
│  │  │            COORDINATOR AGENT                     │  │   │
│  │  │   • Query routing (keyword + intent)             │  │   │
│  │  │   • Multi-agent orchestration                    │  │   │
│  │  │   • Debate arbitration                           │  │   │
│  │  │   • Model selection (Gemini vs Qwen)             │  │   │
│  │  └────────┬────────┬────────┬────────┬─────────────┘  │   │
│  │           │        │        │        │                 │   │
│  │  ┌────────▼──┐ ┌───▼────┐ ┌▼───────┐ ┌▼──────────┐   │   │
│  │  │ Market    │ │ Quant  │ │ Risk & │ │ Decision  │   │   │
│  │  │ Intel     │ │Forecast│ │Volatil.│ │  Agent    │   │   │
│  │  │ Agent     │ │ Agent  │ │ Agent  │ │           │   │   │
│  │  │ (Gemini)  │ │ (Qwen) │ │ (Qwen) │ │ (Gemini)  │   │   │
│  │  └───────────┘ └────────┘ └────────┘ └───────────┘   │   │
│  │           │        │        │        │                 │   │
│  │  ┌────────▼────────▼────────▼────────▼─────────────┐  │   │
│  │  │              UX AGENT (Gemini)                   │  │   │
│  │  │   Adapts output: Farmer│Coop│NGO│Government      │  │   │
│  │  └─────────────────────────────────────────────────┘  │   │
│  └───────────────────────────────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              ML MODELS LAYER                          │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │   │
│  │  │ Crop     │ │ GARCH    │ │Financial │ │ Farmer  │ │   │
│  │  │ Yield    │ │Volatility│ │  Risk    │ │Segment. │ │   │
│  │  │ RF+XGB   │ │ Forecast │ │ RF+SMOTE │ │KMeans+  │ │   │
│  │  │          │ │          │ │          │ │PCA      │ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │   │
│  │  ┌──────────────────────────────────────────────────┐│   │
│  │  │              KPI Dashboard Engine                 ││   │
│  │  └──────────────────────────────────────────────────┘│   │
│  └───────────────────────────────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              DATA LAYER                               │   │
│  │  SQLite: prix │ produits │ prévisions │ conversations │   │
│  │  Memory: décisions │ feedback │ outcomes               │   │
│  │  CSV Import/Export │ Admin CRUD                        │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐   │
│  │              FEEDBACK LOOP                            │   │
│  │  Real outcomes → Memory → Model retraining            │   │
│  │  Decision accuracy tracking → Agent improvement       │   │
│  └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Multi-Model Debate Mechanism

```
User: "Dois-je vendre mon maïs maintenant?"

    ┌──────────────┐
    │  COORDINATOR  │ → Détecte "vendre" → HIGH STAKES → Trigger Debate
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │   GEMINI      │ → Propose: "Vendez 60% maintenant, gardez 40%"
    │  (Strategy)   │   Raison: prix saisonnier haut, risque stockage
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │    QWEN       │ → Critique: "GARCH montre volatilité en baisse,
    │  (Quant)      │   RF prédit +8% dans 3 semaines. Risque: 15%"
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │  COORDINATOR  │ → Arbitre: "VENDRE 50% maintenant (confiance 72%)
    │  (Arbitrage)  │   ATTENDRE 50% pendant 2-3 semaines"
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │   UX AGENT    │ → "💰 Vendez la moitié de votre maïs cette
    │  (Format)     │   semaine. Gardez le reste 2 semaines."
    └──────────────┘
```

## Model Selection Logic

| Agent Type      | Default Model | Reason                          |
|----------------|---------------|----------------------------------|
| Coordinator    | Gemini        | Strategic reasoning, orchestration|
| Market Intel   | Gemini        | Contextual analysis, synthesis   |
| Quant Forecast | Qwen          | Numerical computation, ML        |
| Risk/Volatility| Qwen          | Statistical modeling             |
| Decision       | Gemini        | Strategic synthesis              |
| UX Agent       | Gemini        | Natural language, empathy        |

## Data Flow: Maize Price Decision (Example)

```
1. Farmer asks: "Dois-je vendre mon maïs à Kara?"
2. Router → "decision" agent (keyword: "vendre")
3. should_debate() → True (high stakes)
4. DEBATE:
   a. Gemini/Decision: calls consulter_prix("Maïs", "Kara")
      → Gets 12 months history, sees seasonal peak
   b. Gemini/Decision: calls analyser_tendance("Maïs", "Kara")
      → Trend: HAUSSE +7.2%
   c. Gemini proposes: "VENDRE 70% maintenant"
   d. Qwen/Risk: calls prevoir_volatilite("Maïs", 30)
      → Volatility forecast shows declining vol
   e. Qwen critiques: "Data shows potential +5-8% in 2 weeks"
   f. Coordinator arbitrates with both inputs
5. UX Agent formats for farmer audience
6. Result stored in memory with timestamp
7. Farmer can give feedback later (actual price)
8. Feedback improves future decisions
```

## Monetization Strategy

| Tier          | Target           | Price        | Features                    |
|--------------|------------------|--------------|------------------------------|
| Free         | Smallholder      | 0 FCFA       | Basic prices, 5 queries/day  |
| Pro          | Cooperatives     | 25,000/month | Full ML, unlimited queries   |
| Enterprise   | NGOs/Government  | Custom       | API, bulk data, white-label  |
| Finance      | Agri-lenders     | Revenue share| Risk scoring, portfolio mgmt |

## Roadmap

### Phase 1 (Current) — MVP
- ✅ Multi-agent system with AgentScope
- ✅ Gemini + Qwen dual model
- ✅ 5 ML modules (Yield, GARCH, Risk, Segmentation, KPI)
- ✅ HTMX interface with admin
- ✅ Decision Intelligence Engine with debate
- ✅ Memory + feedback loop

### Phase 2 (Q2 2026) — Scale
- Real-time price data API (WFP VAM, FAO GIEWS)
- SMS/USSD interface for farmers without smartphones
- WhatsApp bot integration
- PostgreSQL migration
- User authentication + multi-tenant

### Phase 3 (Q3 2026) — Expand
- Satellite imagery integration (NDVI, rainfall)
- Cross-border markets (Ghana, Benin, Burkina, Nigeria)
- Mobile app (React Native)
- Model fine-tuning with real outcome data

### Phase 4 (Q4 2026) — Monetize
- B2B API for agri-finance companies
- Government dashboard for food security monitoring
- Partnership with ECOWAS agricultural programs
- Series A fundraising

## Tech Stack

| Layer        | Technology                              |
|-------------|------------------------------------------|
| Frontend    | HTMX + Jinja2 (no JS framework needed)  |
| Backend     | Flask (Python)                           |
| AI Agents   | AgentScope (multi-agent framework)       |
| LLMs        | Gemini 2.5 Flash + Qwen Max             |
| ML          | scikit-learn, XGBoost, arch (GARCH)      |
| Database    | SQLite → PostgreSQL (Phase 2)            |
| Deployment  | Render/Railway → K8s (Phase 3)           |


## B2B REST API

Base URL: `http://localhost:5000/api/v1`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | System status |
| `/prix/<produit>?marche=Kara` | GET | Historical prices |
| `/produits` | GET | All products |
| `/marches` | GET | All markets |
| `/forecast` | POST | GARCH volatility forecast |
| `/risk` | POST | Financial risk assessment |
| `/segmentation` | POST | Farmer segmentation |
| `/kpi` | GET | Agriculture KPIs |
| `/stats` | GET | Database statistics |

## Sample Use Case: Maize in Kara, Togo

**Scenario:** A maize farmer in Kara has 2 tonnes ready. Should they sell now or wait?

**Agent Flow:**
```
1. Farmer asks: "Dois-je vendre mon maïs maintenant à Kara?"

2. ROUTER detects "vendre" → agent_type="decision" + should_debate=True

3. DEBATE TRIGGERED:
   ┌─ GEMINI (Decision Agent):
   │  → Calls consulter_prix("Maïs", "Kara") → 235 FCFA/kg
   │  → Calls analyser_tendance("Maïs", "Kara") → HAUSSE +7.2%
   │  → Proposes: "VENDRE 60% maintenant à 235 FCFA/kg,
   │    garder 40% pour 2-3 semaines"
   │
   ├─ QWEN (Risk Agent):
   │  → Calls prevoir_volatilite("Maïs", 30) → vol 12.3%
   │  → Critique: "Volatilité en baisse, modèle RF prédit
   │    +5-8% dans 14 jours. Risque stockage: 15% pertes"
   │
   └─ COORDINATOR arbitrates:
      → "VENDRE 50% maintenant (confiance 74%).
         ATTENDRE 50% pendant 2 semaines max."

4. UX AGENT formats for farmer:
   "💰 Vendez la moitié de votre maïs cette semaine à 235 FCFA/kg.
    📦 Gardez l'autre moitié 2 semaines — le prix devrait monter.
    ⚠️ Ne dépassez pas 2 semaines (risque de pertes au stockage)."
```

**Sample JSON Output (API):**
```json
{
  "decision": "SELL_PARTIAL",
  "sell_percentage": 50,
  "current_price_fcfa": 235,
  "expected_price_14d": 252,
  "confidence": 74,
  "risk_level": "MEDIUM",
  "risk_explanation": "Volatilité en baisse mais pertes stockage possibles",
  "horizon_days": 14,
  "agents_used": ["decision", "risk_volatility", "coordinator"],
  "debate_used": true,
  "model_primary": "gemini",
  "model_critique": "qwen"
}
```

## Investor-Ready Metrics

| Metric | Value |
|--------|-------|
| Specialized AI Agents | 6 |
| ML Models | 5 (RF, XGBoost, GARCH, K-Means, PCA) |
| LLM Providers | 3 (Gemini, Qwen, Claude) |
| API Keys with rotation | 3 Gemini + 1 DashScope |
| Markets covered | 5 (Togo) → 50+ (West Africa roadmap) |
| Products tracked | 12 → 100+ |
| Decision types | 4 (Sell/Wait/Store/Diversify) |
| Audience types | 4 (Farmer/Coop/NGO/Government) |
| API endpoints | 9 (B2B ready) |
| Feedback loop | Active (memory + outcomes) |

## Competitive Advantage

1. **Multi-agent debate** — No other agri-AI platform uses adversarial model debate for decisions
2. **Dual-model architecture** — Gemini for strategy + Qwen for computation = best of both
3. **Africa-first design** — Built for data gaps, FCFA, seasonal patterns, smallholder constraints
4. **Zero-cost AI layer** — Puter.js Claude fallback means the platform works even with zero API budget
5. **AgentScope foundation** — Production-ready agent framework, not a toy prototype

## File Structure (Final)

```
agentscope/
├── .env                          # API keys (3 Gemini + DashScope)
├── ARCHITECTURE.md               # This document
├── app/
│   ├── __init__.py
│   ├── server.py                 # Flask app + routes
│   ├── agent.py                  # Main agent with key rotation
│   ├── database.py               # SQLite + admin CRUD
│   ├── tools.py                  # AgentScope tools (prix, tendances)
│   ├── ml_tools.py               # AgentScope ML tools (5 modules)
│   ├── key_rotation.py           # Gemini API key rotation
│   ├── admin.py                  # Admin blueprint
│   ├── api.py                    # B2B REST API blueprint
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── prompts.py            # 6 specialized agent prompts
│   │   ├── router.py             # Query routing + model selection
│   │   └── engine.py             # Decision Intelligence Engine
│   ├── ml/
│   │   ├── __init__.py
│   │   ├── crop_yield.py         # RF + XGBoost yield prediction
│   │   ├── garch_volatility.py   # GARCH price volatility
│   │   ├── financial_risk.py     # Loan risk assessment
│   │   ├── farmer_segmentation.py # K-Means + PCA clustering
│   │   └── kpi_dashboard.py      # Agriculture KPIs
│   ├── static/
│   │   └── style.css
│   └── templates/
│       ├── index.html            # Main UI (4 tabs + Puter.js)
│       ├── admin.html            # Admin panel
│       └── partials/             # HTMX partials (8 files)
```
