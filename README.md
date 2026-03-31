# AgriTogo — Decision Intelligence Engine

**AI-powered agricultural market intelligence for Togo and West Africa.**

Built for smallholder farmers, cooperatives, NGOs, and agri-finance institutions operating in low-bandwidth, high-volatility environments.

---

## What it does

AgriTogo combines multi-agent AI, machine learning, and field data collection to deliver actionable decisions for agricultural stakeholders in Togo.

- **Price forecasting** — Historical and real-time commodity prices across 5 Togolese markets
- **Yield prediction** — Per-crop Random Forest + XGBoost models (R² > 0.95)
- **Volatility analysis** — GARCH(1,1) models for commodity price risk
- **Financial risk scoring** — Loan default prediction by region and enterprise size
- **Farmer segmentation** — K-Means + PCA clustering of 186,000+ farmer profiles
- **KPI dashboard** — Yield, cost, and ROI analysis by region and crop
- **KoboCollect integration** — Field data collection with XLSForm generation
- **Decision Engine** — Multi-agent debate (Gemini vs quantitative critique) producing structured recommendations

---

## Architecture

```
AgriTogo/
├── app/
│   ├── agents/          # 6 specialized AI agents (Coordinator, Market Intel, Quant, Risk, Decision, UX)
│   ├── ml/              # 5 ML modules (crop yield, GARCH, financial risk, segmentation, KPIs)
│   ├── templates/       # HTMX-powered UI (dark mode, Bloomberg-style)
│   ├── static/          # CSS + JS (animations, chatbot)
│   ├── agent.py         # Main agent with 3-key Gemini rotation + Claude fallback
│   ├── server.py        # Flask application
│   ├── database.py      # SQLite with 12 products × 5 markets × 12 months
│   ├── kobo.py          # KoboCollect API client + XLSForm generator
│   └── api.py           # B2B REST API (9 endpoints)
└── ARCHITECTURE.md      # Full system design
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Agents | AgentScope (multi-agent framework) |
| LLMs | Gemini 2.5 Flash (3-key rotation) + Claude via Puter.js |
| ML | scikit-learn, XGBoost, arch (GARCH), pandas |
| Backend | Flask + HTMX |
| Database | SQLite |
| Field Data | KoboToolbox API v2 |

---

## Quick Start

```bash
git clone https://github.com/Louistatch/agritogo.git
cd agritogo
python -m venv venv
venv\Scripts\activate  # Windows
pip install -e .
pip install flask scikit-learn xgboost arch pandas plotly openpyxl requests
```

Create `.env`:
```
GEMINI_API_KEY_1=your_key_1
GEMINI_API_KEY_2=your_key_2
GEMINI_API_KEY_3=your_key_3
DASHSCOPE_API_KEY=your_dashscope_key
```

Run:
```bash
cd agritogo
python -m app.server
```

Open http://localhost:5000

---

## Key Features

### Decision Engine
Multi-agent debate mechanism: Gemini proposes a strategy, a quantitative agent critiques it, the coordinator arbitrates. Output: structured recommendation with confidence score and risk explanation.

### Per-Crop Yield Models
Separate Random Forest + XGBoost model per crop (Maize, Rice, Sorghum, Soybean, Cassava, Yam). R² = 0.95+ vs R² = -0.34 when all crops are mixed.

### KoboCollect Integration
Connect your KoboToolbox account to pull field survey data directly into the platform. Download ready-to-deploy XLSForm templates for price collection and farmer profiling.

### Multilingual
Full FR/EN interface with no language mixing. Agent responses follow the selected language.

---

## API

Base URL: `http://localhost:5000/api/v1`

| Endpoint | Description |
|----------|-------------|
| `GET /health` | System status |
| `GET /prix/<produit>` | Historical prices |
| `POST /forecast` | GARCH volatility forecast |
| `POST /risk` | Financial risk assessment |
| `POST /segmentation` | Farmer segmentation |
| `GET /kpi` | Agriculture KPIs |

---

## Context

This platform was designed for the Togolese agricultural context:
- 5 regions: Maritime, Plateaux, Centrale, Kara, Savanes
- 12 commodities: Maize, Rice, Sorghum, Millet, Beans, Soy, Groundnut, Yam, Cassava, Tomato, Pepper, Onion
- 5 markets: Lomé-Adawlato, Kara, Sokodé, Atakpamé, Dapaong
- Currency: FCFA

---

## License

Apache 2.0

---

*AgriTogo uses [AgentScope](https://github.com/agentscope-ai/agentscope) as its multi-agent framework foundation.*
