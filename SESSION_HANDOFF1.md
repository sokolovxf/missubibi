# Missubibi — Session Handoff

> **Purpose:** This document summarizes what has been completed, the current architecture, key decisions, and the recommended next steps — so the team can continue development without repeating previous work or re-deriving decisions already made.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [What's Actually Been Wired In](#2-whats-actually-been-wired-in)
3. [GitHub & Local Setup](#3-github--local-setup)
4. [Project Structure](#4-project-structure)
5. [Backend](#5-backend)
6. [API Endpoints](#6-api-endpoints)
7. [Mock Data Layer](#7-mock-data-layer)
8. [Analytics Service (Rule-Based)](#8-analytics-service-rule-based)
9. [Frontend](#9-frontend)
10. [Frontend ↔ Backend Data Flow](#10-frontend--backend-data-flow)
11. [Current "AI" ≠ Machine Learning Yet](#11-current-ai--machine-learning-yet)
12. [Git History & Workflow](#12-git-history--workflow)
13. [Current Status Checklist](#13-current-status-checklist)
14. [What's Next: Forecasting Model](#14-whats-next-forecasting-model)
15. [Forecasting Methodology & Rules](#15-forecasting-methodology--rules)
16. [Recommended Development Order](#16-recommended-development-order)
17. [Big Picture / Target Architecture](#17-big-picture--target-architecture)

---

## 1. Project Overview

| | |
|---|---|
| **Project** | Missubibi |
| **Type** | University project |
| **Concept** | AI-based Sales Order Forecasting Dashboard for Mitsubishi Electric / MELFT-type sales data |

**Intended end-to-end system:**
```
Sales Data
    ↓
Data Processing
    ↓
Forecasting / Analytics
    ↓
FastAPI Backend
    ↓
REST API
    ↓
React Frontend
    ↓
Interactive Dashboard
```

**Planned dashboard sections:**
- Executive / Overview
- Sales Forecast
- Revenue
- Inventory Risk
- Product Analysis
- Customer Analysis
- Forecast Accuracy / AI Model Performance
- Insights / Recommendations

The final system will run on **MySQL**. Development currently uses **mock data** so frontend and backend work can proceed before everyone has database access.

---

## 2. What's Actually Been Wired In

This is the key update from this session — the project has moved past a static frontend into a genuine, connected full-stack application:

```
React + TypeScript + Vite  (localhost:5174)
            ↓
        fetch()
            ↓
     FastAPI REST API  (127.0.0.1:8100)
            ↓
      Python analytics (routes.py → analytics.py)
            ↓
        Pandas DataFrame
            ↓
          Mock Data
```

**Confirmed working end-to-end:**
- ✅ FastAPI backend running on port `8100`, with CORS enabled for the frontend origin
- ✅ Five live REST endpoints (`/api/health`, `/api/dashboard`, `/api/sales`, `/api/products`, `/api/insights`) — see [§6](#6-api-endpoints)
- ✅ React frontend running on port `5174`, calling all five endpoints via `useEffect` + `fetch()` on load
- ✅ Dashboard KPIs, monthly sales chart, revenue visualization, product table, and AI-insights panel are all **rendered from live API responses**, not hardcoded JSX
- ✅ Verified with a direct hit on `http://127.0.0.1:8100/api/insights`

**What this means:** the React frontend does not need to be rewritten as the data source changes later — it already talks to the API, not to hardcoded values. Swapping mock data for MySQL later should be an invisible change to the frontend (see [§10](#10-frontend--backend-data-flow)).

---

## 3. GitHub & Local Setup

| | |
|---|---|
| **Local path** | `/Users/mac/Documents/Missubibi` |
| **GitHub repo** | `https://github.com/sokolovxf/missubibi.git` |
| **Visibility** | Private |

> **Important:** Missubibi is a completely separate project from **Localhost-One / LH-1**, with its own `.git` repository. Do not modify LH-1 while working on Missubibi.

---

## 4. Project Structure

```
Missubibi/
│
├── database/
│   ├── schema.sql
│   ├── seed.sql
│   └── README.md
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py
│   │   │
│   │   ├── data/
│   │   │   └── mock_data.py
│   │   │
│   │   ├── services/
│   │   │   └── analytics.py
│   │   │
│   │   └── main.py
│   │
│   ├── pyproject.toml
│   ├── uv.lock
│   └── .venv/                # not committed
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── App.css
│   │   └── ...
│   │
│   ├── package.json
│   └── ...
│
├── docs/
│
├── .gitignore
└── README.md
```

> The current Python setup does **not** require `__init__.py` files in the `app` directories.

---

## 5. Backend

**Stack:** Python 3.12 · FastAPI · Uvicorn · Pandas · SQLAlchemy · python-dotenv, managed via `uv`.

**Initialized with:**
```bash
cd /Users/mac/Documents/Missubibi/backend
uv init --python 3.12
uv add fastapi uvicorn pandas python-dotenv sqlalchemy
```

**Port:** `8100` — intentionally different from LH-1's `8000`.

**Run it:**
```bash
cd /Users/mac/Documents/Missubibi/backend
uv run uvicorn app.main:app --reload --port 8100
```
- Backend: `http://127.0.0.1:8100`
- Swagger: `http://127.0.0.1:8100/docs`

**`backend/app/main.py`** creates the FastAPI app, enables CORS, and includes the API router.

**CORS currently allows:**
- `http://localhost:5174`
- `http://127.0.0.1:5174`

This was necessary because the frontend (`5174`) and backend (`8100`) run on different ports — without it, browser requests from React to FastAPI are blocked. **Tested and confirmed working.**

---

## 6. API Endpoints

Defined in `backend/app/api/routes.py`, all under a shared prefix:
```python
router = APIRouter(prefix="/api")
```

| Endpoint | Backing function | Returns |
|---|---|---|
| `GET /api/health` | — | `{"status": "ok"}` — basic liveness check |
| `GET /api/dashboard` | `get_dashboard_summary()` | Total units, total revenue, forecast accuracy, top product |
| `GET /api/sales` | `get_monthly_sales()` | Monthly actual units, forecast units, revenue |
| `GET /api/products` | `get_product_summary()` | Product-level actual/forecast units and revenue, sorted by revenue |
| `GET /api/insights` | `get_ai_insights()` | Auto-generated, rule-based business insights |

**Example — `/api/dashboard` flow:**
```
React → GET /api/dashboard → FastAPI → routes.py → get_dashboard_summary()
      → mock_data.py → Pandas → JSON response → React
```

**Example — `/api/sales` flow:**
```
Raw Data → Pandas groupby(month) → Monthly Data → JSON → React chart
```

**Example — `/api/products` flow:**
```
Mock Data → Pandas → groupby(product) → Product Summary → JSON → React table
```

All confirmed reachable, including a direct test of `http://127.0.0.1:8100/api/insights`.

---

## 7. Mock Data Layer

**File:** `backend/app/data/mock_data.py`
**Function:** `get_sales_data()` → returns a Pandas DataFrame.

**Fields:**
```
month, product, customer, actual_units, forecast_units, revenue
```

**Example products:** MELSEC iQ-R, MELSEC iQ-F, Servo Motor, Inverter
**Example customers:** Customer A, Customer B, Customer C
**Current span:** ~12 months

**Why mock data:** a teammate has already extracted/loaded data into MySQL via MySQL Workbench, but not everyone has database access yet. Waiting on that would block API, React, chart, and analytics development — so mock data lets the whole application architecture get built first. `mock_data.py` is designed to be swapped out later without changing the API surface (see [§10](#10-frontend--backend-data-flow)).

---

## 8. Analytics Service (Rule-Based)

**File:** `backend/app/services/analytics.py`

| Function | What it does |
|---|---|
| `get_dashboard_summary()` | Total actual units, total revenue, forecast accuracy, top product |
| `get_monthly_sales()` | Groups sales by month |
| `get_product_summary()` | Groups sales by product, sorted by revenue |
| `get_ai_insights()` | Generates rule-based insights (see below) |

**`get_ai_insights()` logic, conceptually:**

- **Demand trend** — compares the first available month to the last:
  → *"Demand increasing" / "Demand declining" / "Demand stable"*
- **Forecast risk by product** — computes `(Forecast − Actual) ÷ Actual × 100` per product, flags the largest absolute error:
  → *"Forecast risk" / "Forecast stable"*
- **Overall forecast accuracy** — from the actual-vs-forecast units gap:
  → *"Forecast performing well" / "Forecast performance acceptable" / "Forecast needs attention"*

---

## 9. Frontend

**Stack:** React · TypeScript · Vite · CSS (ESLint enabled).

**Initialized with:**
```bash
cd /Users/mac/Documents/Missubibi/frontend
npm create vite@latest . -- --template react-ts
```

**Port:** `5174` — configured via the npm script itself, **not** `vite.config.ts`:
```bash
npm pkg set scripts.dev="vite --port 5174"
```
Intentionally different from LH-1's `5173` — don't change it.

**Run it:**
```bash
cd /Users/mac/Documents/Missubibi/frontend
npm run dev
```
Frontend: `http://localhost:5174`

**Key files:**
- `frontend/src/App.tsx` — main dashboard component, calls the backend on load via `useEffect`
- `frontend/src/App.css` — dashboard styling

---

## 10. Frontend ↔ Backend Data Flow

```
                 React Frontend
                 localhost:5174
                       │
                       │ fetch()
                       ↓
             http://127.0.0.1:8100
                       │
                       ↓
                 FastAPI Router
                       │
       ┌───────────────┼────────────────┐
       ↓               ↓                ↓
  /api/dashboard   /api/sales    /api/products / /api/insights
       │               │                │
       └───────────────┼────────────────┘
                       ↓
                Analytics Service
                       │
                       ↓
                   Mock Data
                       │
                       ↓
                    Pandas
                       │
                       ↓
                  JSON Response
                       │
                       ↓
                  React State
                       │
                       ↓
                 Dashboard UI
```

**Already dynamic (driven by live API data, not hardcoded):**

Total Units · Revenue · Forecast Accuracy · Top Product · Monthly Sales · Monthly Revenue · Product Data · Forecast Variance · AI Insights · Sales chart · Revenue visualization

**Still hardcoded (minor, low priority):**
A few KPI comparison/trend badges (e.g. `↑ 8.4%`, `↑ 6.2%`, `+2.1%`) are static. A replacement approach to calculate these dynamically was prepared, but this is a small polish item — **not** a blocker. The bigger priority is the forecasting model.

**Why this architecture matters:** the frontend calls the same API regardless of whether the backend is reading from mock data or MySQL. The data source can change entirely behind the API without React needing to change:

```
Current:  /api/sales → get_sales_data() → mock data
Future:   /api/sales → get_sales_data() → SQLAlchemy → MySQL
```
The React frontend should never connect to MySQL directly.

---

## 11. Current "AI" ≠ Machine Learning Yet

**Important distinction for the project write-up:** `/api/insights` is currently **rule-based analytics**, not a trained ML model. It evaluates conditions like *"is demand up more than 5%?"* or *"is forecast error above 5%?"* and returns a matching message.

```
Current:   Rule-based analytics
NOT yet:   Trained AI forecasting model
```

The next major milestone is implementing the actual forecasting model (see [§14](#14-whats-next-forecasting-model)).

---

## 12. Git History & Workflow

**Commits made so far:**
- `2eac8e6` — Initial project structure
- `afdc3ab` — Test mbsave

The repo has been successfully pushed to GitHub.

**`mbsave`** — a personal shell shortcut that runs, in the Missubibi directory:
```bash
git status
git add .
git commit -m "..."
git push
```
Usage: `mbsave "Add API endpoint"`. Convenient solo, but not the team workflow.

**Recommended team workflow (3–4 collaborators):**
```bash
git checkout -b feature/xgboost-forecast
git add .
git commit -m "Add XGBoost forecasting model"
git push -u origin feature/xgboost-forecast
```
Then open a Pull Request into `main`.

**Team rules:**

| Do | Avoid |
|---|---|
| Pull before starting work | Force-pushing to `main` |
| Use feature branches for major features | Committing `.env` |
| Commit logical, clearly-messaged changes | Committing database passwords or API keys |
| Review Pull Requests | Editing the same large file simultaneously without coordinating |
| Keep credentials out of GitHub | Modifying LH-1 while working on Missubibi |
| Say which files you're touching | |

---

## 13. Current Status Checklist

| Item | Status |
|---|---|
| GitHub repository (private) | ✅ |
| Project folder structure | ✅ |
| Backend environment (Python 3.12, FastAPI, Uvicorn, Pandas, SQLAlchemy) | ✅ |
| Mock data | ✅ |
| REST API + CORS | ✅ |
| Backend ↔ frontend connection | ✅ |
| React frontend (TypeScript, Vite) | ✅ |
| Dashboard UI | ✅ |
| Dynamic dashboard data | ✅ |
| Product analysis | ✅ |
| Revenue visualization | ✅ |
| Rule-based insights | ✅ |
| MySQL integration | ⏳ |
| Actual ML forecasting | ⏳ |
| XGBoost | ⏳ |
| SARIMA | ⏳ |
| Model comparison | ⏳ |
| `/api/forecast` | ⏳ |
| Inventory risk | ⏳ |
| Advanced customer analysis | ⏳ |
| Final real-data integration | ⏳ |

---

## 14. What's Next: Forecasting Model

The dashboard already proves the backend, API, frontend, and data flow all work correctly. The next — and biggest — milestone is the real forecasting layer.

**Recommended main model: XGBoost** (gradient-boosted decision trees), trained on engineered time-series features.

**Recommended benchmark: SARIMA** (classical statistical time-series model). Comparing the two gives the project a stronger academic story than a single-model approach — *"we compared a classical time-series approach with a machine-learning approach and evaluated them on forecasting metrics"* rather than *"we used XGBoost."*

**Potential XGBoost features:**
```
month, year, lag_1, lag_3, lag_6, lag_12, rolling_mean_3, rolling_mean_6
```
Depending on the real dataset, also consider: `product`, `customer`, historical revenue, seasonality, previous demand.

**Evaluation metrics:**
| Metric | What it measures |
|---|---|
| MAE | Mean Absolute Error — average absolute difference, actual vs. predicted |
| RMSE | Root Mean Squared Error — penalizes larger errors more heavily |
| MAPE | Mean Absolute Percentage Error — error as a percentage |
| R² | Coefficient of determination — useful for some regression framings, but not sufficient alone for time-series forecasting |

**New backend file recommended:**
```
backend/app/services/forecasting.py
```
kept separate from `analytics.py`. SARIMA can live in its own `sarima.py`, or be combined with `forecasting.py` if that's cleaner for the team.

**Planned pipeline:**
```
Load data → Sort chronologically → Feature engineering →
Train/test split by time → Train XGBoost → Generate forecast →
Calculate metrics → Return forecast + metrics
```
> **Do not use a random train/test split.** Time-series evaluation must respect chronological order.

**Planned new endpoint:**
```
GET /api/forecast
```
```json
{
  "model": "XGBoost",
  "forecast": [
    { "month": "2025-01", "forecast_units": 150 },
    { "month": "2025-02", "forecast_units": 157 }
  ],
  "metrics": { "mae": 12.4, "rmse": 18.7, "mape": 4.8 }
}
```
(Exact shape may be adjusted once the model is implemented.)

**ML dependencies to add:**
```bash
cd /Users/mac/Documents/Missubibi/backend
uv add xgboost scikit-learn numpy joblib
```
> Development machine is Apple Silicon — test the XGBoost install before building the model around it.

---

## 15. Forecasting Methodology & Rules

**Recommended training/evaluation split:**
```
FY2021 – FY2024  →  Training
                          ↓
                    Forecast FY2025
                          ↓
              Compare with FY2025 Actual
```

> ⚠️ **Critical rule:** if FY2025 is the forecast/evaluation period, **do not train on FY2025 actuals** before evaluating. Otherwise the model has seen the target period and the forecast will look artificially accurate. Exact fiscal years should be confirmed against the team's real cleaned dataset.

**Data volume caveat:** the current ~12-month mock dataset is enough to prove out the backend, API, dashboard, and basic analytics — but it's **not enough for a meaningful ML model**. Before building XGBoost, expand mock data to a multi-year, multi-product, multi-customer dataset (`date, product, customer, actual_units, revenue`) so lag features, seasonality, and rolling averages are actually demonstrable.

---

## 16. Recommended Development Order

```
1.  Confirm current dashboard works                    ✅ done
2.  Expand mock data to multiple years
3.  Implement feature engineering
4.  Install and test XGBoost
5.  Build XGBoost forecasting model
6.  Evaluate XGBoost (MAE / RMSE / MAPE)
7.  Implement SARIMA benchmark
8.  Compare XGBoost vs. SARIMA
9.  Create /api/forecast
10. Connect forecasts to React
11. Add model-performance dashboard section
12. Add deeper product/customer analysis
13. Add inventory-risk logic
14. Connect MySQL
15. Replace mock data
16. Final testing
17. Documentation
18. University presentation / report
```

---

## 17. Big Picture / Target Architecture

**Where the project stands right now:**
```
MISSUBIBI
    │
    ↓
 Mock Data → FastAPI → REST API → React Dashboard → Basic Analytics
```

**The next stage:**
```
Historical Sales Data → Feature Engineering → XGBoost → Forecast
       → Evaluation → SARIMA → Model Comparison → FastAPI API
       → React Forecast Dashboard
```

**Eventual full target architecture:**
```
                     MISSUBIBI
                         │
                    MySQL Data
                         │
                         ↓
                  Data Processing
                         │
             ┌───────────┴───────────┐
             ↓                       ↓
          XGBoost                 SARIMA
             │                       │
             └───────────┬───────────┘
                         ↓
                  Model Evaluation
                         │
                         ↓
                     Best Model
                         │
                         ↓
                      Forecast
                         │
                         ↓
                       FastAPI
                         │
                         ↓
                  React Dashboard
                         │
        ┌────────────────┼────────────────┐
        ↓                ↓                ↓
    Forecast          Revenue        Risk Analysis
        │                │                │
        └────────────────┼────────────────┘
                         ↓
                Business Insights
```

**Bottom line:** the foundation — repo, backend, API, frontend, dynamic dashboard, rule-based insights — is already built and confirmed working end-to-end. The single most important next milestone is **not** another frontend pass; it's building the real forecasting pipeline (XGBoost + SARIMA) and wiring its output into the dashboard that already exists. That's the step that turns this from a dashboard prototype into an actual AI-based forecasting system.
