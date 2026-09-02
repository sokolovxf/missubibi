# Missubibi — Architecture & Developer Setup

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Repository Structure](#2-repository-structure)
3. [Technology Stack](#3-technology-stack)
4. [Backend](#4-backend)
5. [Frontend](#5-frontend)
6. [Planned Dashboard](#6-planned-dashboard)
7. [Frontend ↔ Backend Communication](#7-frontend--backend-communication)
8. [First-Time Setup — macOS](#8-first-time-setup--macos)
9. [First-Time Setup — Windows](#9-first-time-setup--windows)
10. [Daily Development](#10-daily-development)
11. [Dependencies](#11-dependencies)
12. [Ports](#12-ports)
13. [Git Workflow](#13-git-workflow)
14. [Environment Variables](#14-environment-variables)
15. [MySQL Integration (Planned)](#15-mysql-integration-planned)
16. [Forecasting Architecture](#16-forecasting-architecture)
17. [Troubleshooting](#17-troubleshooting)
18. [Quick Start](#18-quick-start)
19. [Current Development Status](#19-current-development-status)
20. [Architecture Principle](#20-architecture-principle)

---

## 1. Project Overview

**Missubibi** is an AI-based Sales Order Forecasting Dashboard.

The current development version uses **mock sales data** so frontend and backend development can continue in parallel, before the production MySQL database is connected.

### Current Architecture

```
                        MISSUBIBI
                            │
            ┌───────────────┴───────────────┐
            │                                │
      React + Vite                       FastAPI
    localhost:5174                    localhost:8100
            │                                │
            └────────────  REST API  ────────┘
                                              │
                                    Mock Data / Pandas
                                              │
                                       Future: MySQL
```

### Planned Production Architecture

```
MySQL Database
      ↓
FastAPI Backend
      ↓
REST API
      ↓
React Frontend
      ↓
Missubibi Dashboard
```

---

## 2. Repository Structure

```
Missubibi/
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
│   ├── .venv/              # Local Python environment (not committed)
│   ├── pyproject.toml
│   ├── uv.lock
│   └── .python-version
│
├── frontend/
│   ├── src/
│   │   ├── assets/
│   │   ├── App.tsx
│   │   ├── App.css
│   │   ├── index.css
│   │   └── main.tsx
│   │
│   ├── public/
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.ts
│   └── ...
│
├── database/
│   ├── schema.sql
│   ├── seed.sql
│   └── README.md
│
├── docs/
│   └── ARCHITECTURE.md
│
├── .gitignore
└── README.md
```

> **Do not commit:** `.venv/`, `node_modules/`, `.env`
> These are local environments, dependencies, or potentially sensitive configuration, and should be listed in `.gitignore`.

---

## 3. Technology Stack

### Frontend

| Technology | Purpose |
|---|---|
| React | User interface |
| TypeScript | Type-safe frontend |
| Vite | Development server / build tool |
| Recharts | Data visualization |
| Lucide React | UI icons |
| CSS | Dashboard styling |
| ESLint | Code quality |

- **Frontend:** `http://localhost:5174`
- Port `5174` is intentional — LH-1 uses port `5173`.

### Backend

| Technology | Purpose |
|---|---|
| Python 3.12 | Backend runtime |
| FastAPI | REST API framework |
| Uvicorn | ASGI server |
| Pandas | Data processing |
| SQLAlchemy | Database abstraction |
| python-dotenv | Environment variables |

- **Backend:** `http://127.0.0.1:8100`
- **Swagger docs:** `http://127.0.0.1:8100/docs`
- Port `8100` is intentional — LH-1 uses port `8000`.

### Database

**Production database:** MySQL

The current backend does not connect to MySQL yet.

**Current data flow:**
```
Mock Data → Pandas → Analytics → FastAPI
```

**Future data flow:**
```
MySQL → SQLAlchemy → Analytics → FastAPI
```

---

## 4. Backend

### `backend/app/main.py`
Creates the FastAPI application and registers the API routes.

### `backend/app/api/routes.py`
Defines the REST API.

**Current endpoints:**

| Endpoint | Description |
|---|---|
| `GET /api/health` | Health check |
| `GET /api/dashboard` | Dashboard summary metrics |
| `GET /api/sales` | Monthly sales data |
| `GET /api/products` | Product-level sales data |

**Health check response:**
```json
{
  "status": "ok"
}
```

### `backend/app/data/mock_data.py`
Contains the current development dataset.

Fields currently include:
- `month`
- `product`
- `customer`
- `actual_units`
- `forecast_units`
- `revenue`

This will eventually be replaced by database-backed data.

### `backend/app/services/analytics.py`
Contains analytical / business logic.

**Current functions:**
- `get_dashboard_summary()`
- `get_monthly_sales()`
- `get_product_summary()`

> Business calculations should generally remain in the service layer rather than inside API routes.

---

## 5. Frontend

### `frontend/src/main.tsx`
React application entry point.

### `frontend/src/App.tsx`
Main Missubibi dashboard component.

**Current UI includes:**
- Sidebar
- Overview navigation
- Dashboard header
- KPI cards
- Sales performance
- Revenue
- Product performance
- AI insights

> The current dashboard still contains presentation/mock values. These will be replaced with live API data.

### `frontend/src/App.css`
Dashboard-specific styling — sidebar, header, KPI cards, charts, product table, AI insights, layout, and responsive behavior.

### `frontend/src/index.css`
Global CSS and browser-level styling.

---

## 6. Planned Dashboard

The dashboard is designed around these sections:

1. Overview
2. Sales Forecast
3. Revenue
4. Inventory Risk
5. Products
6. Customers
7. Forecast Accuracy
8. AI Insights

**Potential KPIs:**
- Total Units
- Forecast Revenue
- Forecast Accuracy
- YoY Growth
- Products at Risk
- Top Product
- Top Customer

**Potential visualizations:**
- Actual vs. Forecast
- Monthly Revenue
- Product Performance
- Customer Performance
- Inventory Risk
- Forecast Error
- Model Accuracy
- Model Comparison

---

## 7. Frontend ↔ Backend Communication

The frontend communicates with FastAPI through REST API requests.

```
React
  │
  │  GET /api/dashboard
  ↓
FastAPI
  │
  ↓
Analytics Service
  │
  ↓
Data Source
  │
  ↓
JSON
  │
  ↓
React Dashboard
```

**Example request:**
```
http://127.0.0.1:8100/api/dashboard
```

**Example response:**
```json
{
  "total_units": 1625,
  "total_revenue": 6500000,
  "forecast_accuracy": 96.8,
  "top_product": "Inverter"
}
```

> These values are currently based on mock data.

---

## 8. First-Time Setup — macOS

### Prerequisites

Install:
- Git
- Node.js
- npm
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- VS Code

Verify installation:
```bash
git --version
node --version
npm --version
python3 --version
uv --version
```
Python should report `3.12.x`.

### Clone the Repository

```bash
git clone https://github.com/sokolovxf/missubibi.git
cd missubibi
```

### Backend Setup

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8100
```

- Backend: `http://127.0.0.1:8100`
- Swagger: `http://127.0.0.1:8100/docs`
- Health check: `http://127.0.0.1:8100/api/health`

Keep this terminal running.

### Frontend Setup

Open a new Terminal tab/window:

```bash
cd missubibi/frontend
npm install
npm run dev
```

- Frontend: `http://localhost:5174`

---

## 9. First-Time Setup — Windows

Use **PowerShell**.

### Prerequisites

Verify installation:
```powershell
git --version
node --version
npm --version
python --version
uv --version
```
Python should report `3.12.x`.

### Clone the Repository

```powershell
git clone https://github.com/sokolovxf/missubibi.git
cd missubibi
```

### Backend Setup

```powershell
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8100
```

- Backend: `http://127.0.0.1:8100`
- Swagger: `http://127.0.0.1:8100/docs`

### Frontend Setup

Open a new PowerShell window:

```powershell
cd path\to\Missubibi\frontend
npm install
npm run dev
```

Example path:
```powershell
cd C:\Users\YourName\Documents\Missubibi\frontend
```

- Frontend: `http://localhost:5174`

---

## 10. Daily Development

After first-time installation, two terminals are required each time you work on the project.

**Terminal 1 — Backend**

macOS/Linux:
```bash
cd Missubibi/backend
uv run uvicorn app.main:app --reload --port 8100
```

Windows:
```powershell
cd Missubibi\backend
uv run uvicorn app.main:app --reload --port 8100
```

**Terminal 2 — Frontend**

macOS/Linux:
```bash
cd Missubibi/frontend
npm run dev
```

Windows:
```powershell
cd Missubibi\frontend
npm run dev
```

Then open: `http://localhost:5174`

---

## 11. Dependencies

### Backend

Defined in `backend/pyproject.toml`, locked via `backend/uv.lock`.

Current dependencies:
- `fastapi`
- `uvicorn`
- `pandas`
- `python-dotenv`
- `sqlalchemy`

Collaborators should use:
```bash
uv sync
```
rather than manually installing individual packages — this guarantees everyone resolves to the exact same locked versions.

### Frontend

Defined in `frontend/package.json`, locked via `frontend/package-lock.json`.

Current stack:
- React
- TypeScript
- Vite
- Recharts
- Lucide React
- ESLint

Install everything with:
```bash
npm install
```
Do not manually install packages unless a dependency is intentionally being added.

---

## 12. Ports

Missubibi deliberately uses different ports from LH-1 so both projects can run locally at the same time without conflicts.

| Project | Frontend | Backend |
|---|---|---|
| **Missubibi** | 5174 | 8100 |
| **LH-1** | 5173 | 8000 |

Do not change these without coordinating with the team.

---

## 13. Git Workflow

**Before starting work:**
```bash
git pull
```

**Check changes:**
```bash
git status
```

**Save changes:**
```bash
git add .
git commit -m "Describe your changes"
git push
```

**Feature branches** are recommended for team development:
```bash
git checkout -b feature/dashboard-charts
git push -u origin feature/dashboard-charts
```
Then open a Pull Request on GitHub.

> Avoid committing experimental work directly to `main` when multiple collaborators are working simultaneously.

---

## 14. Environment Variables

**Never commit:**
- `.env`
- `.env.*`
- API keys
- Database passwords or credentials

If environment variables are required, provide a template via `.env.example`:

```
DATABASE_HOST=localhost
DATABASE_PORT=3306
DATABASE_NAME=missubibi
DATABASE_USER=your_username
DATABASE_PASSWORD=your_password
```

Each collaborator creates their own local `.env`. Never place real credentials in `.env.example`.

---

## 15. MySQL Integration (Planned)

The current project does **not** require MySQL to run — this is intentional, so the team can build the application against mock data first.

**Once the real database is ready:**
```
MySQL
  ↓
SQLAlchemy
  ↓
Data Access
  ↓
Analytics Services
  ↓
FastAPI
  ↓
React
```

A MySQL driver will also need to be added — one option is `PyMySQL`. The exact driver should be agreed on when MySQL integration begins.

> The frontend should continue communicating with FastAPI rather than connecting directly to MySQL.

---

## 16. Forecasting Architecture

**Intended forecasting workflow:**
```
Historical Sales
      ↓
Data Cleaning
      ↓
Feature Engineering
      ↓
AI / ML Model
      ↓
Forecast
      ↓
Accuracy Evaluation
      ↓
FastAPI
      ↓
Dashboard
```

A clean methodology should separate training data from the forecast/evaluation period, e.g.:

```
FY2021–FY2024 → Training / Model Development → AI Model → FY2025 Forecast → Compare with FY2025 Actual
```

> The target evaluation period should never be used as training data when presenting an out-of-sample forecast evaluation.

---

## 17. Troubleshooting

**Frontend does not start**
```bash
cd Missubibi/frontend
npm install
npm run dev
```

**Backend dependencies missing**
```bash
cd Missubibi/backend
uv sync
```

**`No module named 'app'`**
Make sure the terminal is inside `Missubibi/backend`, then:
```bash
uv run uvicorn app.main:app --reload --port 8100
```
Do not run this command from the repository root.

**Port 5174 already in use**

macOS/Linux:
```bash
lsof -i :5174
```
Windows PowerShell:
```powershell
Get-NetTCPConnection -LocalPort 5174
```

**Port 8100 already in use**

macOS/Linux:
```bash
lsof -i :8100
```
Windows PowerShell:
```powershell
Get-NetTCPConnection -LocalPort 8100
```

---

## 18. Quick Start

Once first-time installation is complete:

**Terminal 1**
```bash
cd Missubibi/backend
uv run uvicorn app.main:app --reload --port 8100
```

**Terminal 2**
```bash
cd Missubibi/frontend
npm run dev
```

Then open:
- Frontend: `http://localhost:5174`
- Backend: `http://127.0.0.1:8100`
- Swagger: `http://127.0.0.1:8100/docs`

---

## 19. Current Development Status

**Completed**
- GitHub repository (private)
- Backend initialization (FastAPI application)
- Mock sales dataset
- Analytics service
- REST API + Swagger documentation
- React + TypeScript frontend (Vite)
- Frontend port 5174 / backend port 8100 configured
- Initial dashboard UI

**Next**
- Connect React to FastAPI
- Replace hardcoded values with live API data
- Add Recharts visualizations
- Product analysis
- Customer analysis
- Inventory risk
- Forecast accuracy
- AI/ML forecasting (SARIMA)
- MySQL integration
- Authentication (if required)
- Deployment

---

## 20. Architecture Principle

Keep the application separated into clear layers:

```
┌─────────────────────┐
│      Frontend        │
│    React + TS        │
└──────────┬───────────┘
           │  REST API
           ↓
┌─────────────────────┐
│       Backend        │
│       FastAPI         │
└──────────┬───────────┘
           │
           ↓
┌─────────────────────┐
│       Services        │
│   Analytics / ML       │
└──────────┬───────────┘
           │
           ↓
┌─────────────────────┐
│     Data Access       │
└──────────┬───────────┘
           │
           ↓
┌─────────────────────┐
│       MySQL            │
│   Future Database       │
└─────────────────────┘
```

- **The frontend should never connect directly to MySQL.**
- **The backend is responsible for:** data access, business logic, analytics, forecasting, API responses, database communication.
- **The frontend is responsible for:** user interface, visualization, navigation, user interaction, displaying API results.
