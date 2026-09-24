# Missubibi project guide for Claude Code

This file is the working orientation document for anyone using Claude Code on the Missubibi repository. Read it before changing code. It describes the current implementation as it exists in Git, including the data lineage, model contracts, dashboard sections, startup flow, validation rules, and known limits.

The repository is the Mitsubishi Electric Sales Intelligence dashboard. The application uses Mitsubishi sales history stored in local MySQL, exposes validated forecast and planning APIs through FastAPI, and presents the results in a React/Vite dashboard.

## Source-of-truth documents

Use these documents in this order when a request touches architecture or progress:

1. `CLAUDE_CODE_PROJECT_GUIDE.md` (this current orientation)
2. `docs/IMPLEMENTATION_AUDIT.md` (verified implementation, data reconciliation, accuracy evidence, and remaining scope)
3. `backend/PLANNING.md` (API and runtime contracts)
4. `README.md` and `database/README.md` (startup and database synchronization)
5. `plan.txt` (historical plan; useful for context, but it contains older pre-implementation assumptions)
6. `SESSION_HANDOFF*.md` (chronological investigation notes and smoke checks)

If `plan.txt` conflicts with the implementation audit or the code, trust the audit and the code. Update the audit or a handoff when a material implementation decision changes.

## Git and collaboration

- Remote: `https://github.com/sokolovxf/missubibi.git`
- The repository is intended to be shared through GitHub. Pull before changing SQL or model contracts.
- Check the current branch and worktree before starting:

```bash
git status --short --branch
git log --oneline -8
git remote -v
```

- Create a topic branch for changes. Use the repository's `codex/` prefix unless the owner requests another branch name:

```bash
git switch -c codex/<short-topic-name>
```

- Keep commits focused. Review the diff before committing:

```bash
git diff --check
git diff --stat
git status --short
```

- Do not commit credentials, `backend/.env`, `backend/.venv`, `frontend/node_modules`, trained model artifacts under `backend/var`, job files, caches, or local screenshots. The database seed and schema are shared full snapshots; treat changes to them as coordinated team changes.
- `database/schema.sql` and `database/seed.sql` are not incremental migrations. A later full dump can replace an earlier one without a useful Git merge. Pull, synchronize, and announce before exporting or pushing a new database snapshot.

## System architecture

```text
Mitsubishi source workbooks
  Customer.xlsx, Item.xlsx, Sale Order History.xlsx
             |
             v
RawData_Combined.xlsx (verified combined copy)
             |
             v
 database/schema.sql + database/seed.sql
             |
             v
 local MySQL database: missubibi
   Customerfile_Data, Itemfile_Data, Sales_Order_Merged
             |
             v
 backend/app/data/adapter.py
   SQL boundary, source fingerprint inputs, filters, calendar views,
   native transaction history, CSV and vendor/inventory overlays
             |
             +------------------------------+
             v                              v
 backend/app/services/forecast_service.py  backend/app/services/inventory_planning.py
             |                              |
             v                              v
 model_worker.py -> five forecast engines  lead-time inventory plan
             |
             v
 ensemble_engine.py + model_registry.py + retraining.py
             |
             v
 FastAPI routes under /api and /api/planning
             |
             v
 React/Vite dashboard at localhost:5174
```

The backend is the only layer that reads MySQL. The browser receives JSON through FastAPI; it never connects directly to MySQL.

## Repository map

```text
Missubibi/
├── CLAUDE_CODE_PROJECT_GUIDE.md       # this guide
├── README.md                          # short startup guide
├── ARCHITECTURE.md                    # earlier architecture document
├── plan.txt                           # historical implementation plan
├── docs/IMPLEMENTATION_AUDIT.md       # verified status and evidence
├── SESSION_HANDOFF*.md                # investigation and smoke-test notes
├── start-local.sh                     # macOS/Linux launcher
├── start-local.ps1                    # Windows PowerShell launcher
├── database/
│   ├── schema.sql                     # shared MySQL schema snapshot
│   ├── seed.sql                       # shared Mitsubishi data snapshot
│   ├── ensure_current.sh/.ps1         # compare local DB fingerprints
│   ├── import_db.sh/.ps1              # rebuild local DB from snapshots
│   ├── export_db.sh                   # export local DB to snapshots
│   └── README.md                      # database workflow and safety rules
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app, lifespan, CORS, optional API key
│   │   ├── database.py                # SQLAlchemy engine/session from DATABASE_URL
│   │   ├── api/
│   │   │   ├── routes.py              # legacy-compatible /api routes
│   │   │   └── planning.py            # validated planning, import, classifier, registry routes
│   │   ├── data/
│   │   │   ├── adapter.py             # canonical SQL adapter and calendar transformations
│   │   │   ├── sales_data.py           # legacy analytics view over the adapter
│   │   │   └── mock_data.py            # old development helper; not the production source
│   │   └── services/
│   │       ├── forecast_service.py    # cache, fingerprints, forecast orchestration
│   │       ├── model_worker.py        # isolated subprocess for one base-model fit
│   │       ├── ensemble_engine.py      # Ensemble coordinator and validation weights
│   │       ├── trend_engine.py         # Trend Regression
│   │       ├── sarima_engine.py        # SARIMA
│   │       ├── randomforest_engine.py  # Random Forest
│   │       ├── lstm_engine.py          # LSTM
│   │       ├── xgboost_engine.py       # XGBoost
│   │       ├── classifier_runtime.py   # SavedModel loading and schema checks
│   │       ├── classifier_architectures.py
│   │       ├── classifier_features.py
│   │       ├── classifier_training_data.py
│   │       ├── classifier_train_worker.py
│   │       ├── classifier_jobs.py
│   │       ├── classifier_signals.py   # opt-in experimental exogenous signal plumbing
│   │       ├── nn_classifier.py         # Neural Network Rev 9 adapter
│   │       ├── tr_classifier.py         # Tabular Transformer Rev 8 adapter
│   │       ├── csv_import.py            # preview, validation, overlay persistence
│   │       ├── inventory_planning.py    # lead-time replenishment calculations
│   │       ├── model_registry.py        # reproducible run records and active revision
│   │       ├── retraining.py            # hourly refresh of previously requested runs
│   │       └── analytics.py             # compatibility summaries and insights
│   ├── scripts/export_classifier.py    # export trained classifier SavedModels
│   ├── tests/                          # backend regression tests
│   ├── pyproject.toml                  # Python dependencies and classifier extra
│   └── .env.example                    # local DATABASE_URL template
├── frontend/
│   ├── src/App.tsx                     # dashboard views and API interactions
│   ├── src/App.css                     # dashboard visual system
│   ├── src/index.css                   # global styles
│   ├── src/CsvImport.tsx               # CSV preview/commit flow
│   ├── package.json                    # Vite scripts and React dependencies
│   └── vite.config.ts                  # dev server and /api proxy
├── Sep16th new models and ML/          # original September model source files
└── DATA ORIGINAL + MERGED FILE/        # original Mitsubishi workbooks and combined workbook
```

## Data lineage and data rules

The supplied Mitsubishi files are retained in `DATA ORIGINAL + MERGED FILE/`:

- `Customer.xlsx`
- `Item.xlsx`
- `Sale Order History.xlsx`
- `RawData_Combined.xlsx`

The combined workbook was reconciled against the three originals. The canonical SQL source contains 272,000 source sales lines, with original order dates from 2021-04-01 through 2025-03-31. The adapter's forecast view contains 265,135 rows after removing extra exact duplicate groups using its documented composite key. The original rows remain in SQL and the deduplication rule is still a business assumption that should be confirmed with the source owner.

The source tables are represented in the SQL snapshot as `Customerfile_Data`, `Itemfile_Data`, and `Sales_Order_Merged`. The adapter reads the merged sales table, joins the needed attributes already present there, normalizes month labels, preserves missing price-derived values, and exposes:

- `item`, `product`, `customer`, `industry`, and `vendor` dimensions
- `actual_units` and `revenue` metrics
- original `order_date`, order ID, price, status, and source attributes where available

Vendor relationships are not present in the supplied Mitsubishi source schema. Vendor values become available only through an imported mapping. Purchase orders, receipts, warehouse balances, and supplier lead times are also not present in the source snapshot; the inventory planner accepts those as explicit inputs.

`DataAdapter` caches the canonical SQL frame for 60 seconds. CSV imports are stored as overlays in dedicated tables and are applied without altering the original source tables. Import modes are append or replace-active, exact duplicates are skipped, and item/vendor and item/inventory mapping files are validated before commit.

The adapter supports monthly, daily, weekly, quarterly, and yearly views. Monthly is the source contract used for model fitting. Daily and weekly planning views allocate monthly totals across calendar periods and are labeled as estimates. Native daily/weekly transaction history is available through the native history route for audit and future native-frequency model work.

## Model architecture

### Six forecasting engines

The five base engines are Trend Regression, SARIMA, Random Forest, LSTM, and XGBoost. `ensemble_engine.py` runs them through isolated workers and combines successful members with regularized inverse-MASE weights learned from chronological validation. The Ensemble is the sixth forecasting model exposed by the API.

Each forecast request is built from the same monthly SQL series. The selected dimension can be total, item, product, customer, industry, or vendor, and filters can be combined. A request can forecast revenue or units. The requested daily/weekly/quarterly/yearly horizon is converted to the monthly source horizon, fitted, then transformed back to the requested display granularity.

`model_worker.py` starts one Python subprocess per base-model fit. This isolates notebook-style globals and native OpenMP/PyTorch libraries. A worker has a bounded timeout and returns a JSON-safe unavailable result on failure. Do not collapse this isolation without testing macOS native-library behavior.

Accuracy shown in the dashboard is historical out-of-sample validation, not a promise about future accuracy. Forecast accuracy is `max(0, 100 - WAPE)` over expanding chronological holdout windows. WAPE is total absolute error divided by total absolute actual demand. MASE is reported beside it when its seasonal-naive scale is defined. The same SQL data fingerprint, code, model profile, and validation protocol reproduce the same score; a page refresh or scenario edit must not invent a new model score.

Prediction bounds are useful planning ranges. The weighted Ensemble bounds are approximate and are not claimed to be calibrated 90% intervals. Higher demand/revenue is the optimistic bound and lower demand/revenue is the pessimistic bound.

### Neural Network and Tabular Transformer classifiers

The September models are separate item-level classifiers, not replacements for the five time-series forecasters:

- Neural Network Rev 9 estimates the probability that an item is high demand.
- Tabular Transformer Rev 8 estimates the probability that an item is sold / not sold.

`nn_classifier.py` and `tr_classifier.py` are small production adapters. The architecture, feature engineering, runtime validation, training worker, signal handling, and export helper are separate modules. Full September source is in `Sep16th new models and ML/nn_engine(rev9).py` and `Sep16th new models and ML/tr_engine_rev8.py`.

Classifier exports include a SavedModel, feature schema, SQL data fingerprint, trained cutoff, prediction month, diagnostics, and decision threshold. Missing or stale exports must display unavailable/stale; never replace unavailable probabilities with zero. Held-out diagnostics are shown only when trained artifacts are valid.

Classifier probabilities can be requested as exogenous signals, but that path is experimental and disabled by default. Origin-frozen signals for every engine-internal validation origin are required before treating them as certified forecasting features.

## Backend API contract

All routes are registered by `backend/app/main.py`. The backend listens on `127.0.0.1:8100` and Swagger is at `/docs`.

Compatibility routes under `/api` include:

- `GET /api/health`
- `GET /api/dashboard`, `/api/sales`, `/api/products`, `/api/insights`
- `GET /api/forecast/options`
- `POST` and `GET` forecast aliases for `/forecast`, `/xgboost/forecast`, `/randomforest/forecast`, `/lstm/forecast`, `/trend/forecast`, and `/ensemble/forecast`
- `GET /api/classifier/signals`
- `POST /api/classifier/{nn|tr}/predict`

The validated planning API is under `/api/planning`:

- `GET /options` — available dimensions and values
- `GET /history` — calendar source/allocated history
- `GET /history?native=true` — observed daily/weekly transaction history
- `POST /forecast/run` and `GET /forecast/{job_id}` — bounded asynchronous forecast jobs
- `GET /inventory/lead-time` — lead-time demand, safety stock, reorder point, order quantity, order-by date, and expected arrival
- `POST /imports/preview` and `POST /imports/commit` — CSV preview and commit
- `GET /classifiers` — classifier status, item counts, and diagnostics
- `POST /classifier/train`, `GET /classifier/training`, `POST /classifier/{nn|tr}/predict`
- `GET /classifier/signals` — current exported planning indicators
- `GET /registry`, `GET /registry/{revision}`, `POST /registry/{revision}/activate`, `GET /compare`

Forecast requests use `model`, `dimension`, optional `dimension_value`, optional combined `filters`, `value_col`, `granularity`, `calendar`, `horizon`, `fast`, and opt-in `use_classifier_signals`. Limits are enforced in `ForecastRequest`; yearly horizons are limited to 10 and quarterly horizons to 40.

## Frontend sections

The dashboard is a React/Vite application at `http://localhost:5174`. It currently has these five views:

1. **Forecast workspace** — choose model, metric, dimension, filters, calendar, granularity, and horizon; view history, point forecast, approximate bounds, spark charts, scenario values, and the draggable/keyboard-editable planning preview. Editing a planning value changes the scenario overlay; it does not change historical model validation accuracy.
2. **Model performance** — compare the five base members and Ensemble status, WAPE, accuracy, MASE, validation folds, Ensemble weights, and forecast spark lines. The panel explains the SQL fingerprint and chronological validation protocol.
3. **Demand classifier** — train/refresh Quick or Full NN/TR models, search an item, view probabilities, held-out accuracy, ROC AUC, balanced accuracy, baseline, test rows, confusion matrix, and borderline review queue.
4. **Lead-time inventory** — enter supplier lead time, safety stock, coverage, on-hand units, and planning date; view demand during lead time, reorder point, order quantity, order-by date, and expected arrival. Inventory inputs remain visibly separate from source sales facts.
5. **Data & coverage** — view connected dimensions and counts, source coverage, calendar/native history assumptions, deduplication note, and source limitations.

The top bar shows whether the backend can load MySQL options. The CSV import button is available globally, and forecast export downloads the current result as CSV.

## Start, database, and environment

### macOS/Linux

From the repository root:

```bash
./start-local.sh --sync-db
```

This checks the MySQL fingerprint and refreshes the local `missubibi` database from the checked-out schema and seed only when it is missing or stale. It then reuses existing processes on ports 8100/5174 or starts the backend and frontend.

When the database is already synchronized:

```bash
./start-local.sh
```

Manual startup:

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8100

# second terminal
cd frontend
npm install
npm run dev
```

### Windows PowerShell

```powershell
.\start-local.ps1 -SyncDatabase
```

Or check/synchronize separately:

```powershell
.\database\ensure_current.ps1 -Sync
```

Copy `backend/.env.example` to `backend/.env` and set a local MySQL `DATABASE_URL`. Never commit that file. The backend expects MySQL to be running and uses SQLAlchemy with PyMySQL. On macOS, XGBoost may also require the Homebrew `libomp` runtime. TensorFlow is optional and is installed by `uv sync --extra classifiers` only when classifier training or SavedModel serving is needed.

If a manual Uvicorn command reports `Address already in use`, the service is already listening on port 8100. Use the running API or stop the existing process before starting another one; the launcher already reuses active ports.

## Tests and verification

Run the backend tests from the repository root:

```bash
cd backend
.venv/bin/python -m unittest discover -s tests -v
```

Run frontend checks:

```bash
npm --prefix frontend run build
npm --prefix frontend run lint
```

The regression suite covers calendar conservation, leap dates, fiscal boundaries, native history, compound filters, quiet tails, chronological metrics, recursive Random Forest behavior, LSTM inversion, Ensemble exclusions, inventory mappings, import validation, classifier unavailability, and registry rollback.

When changing a forecast engine, run the focused tests and a live SQL-backed quick forecast. Do not use mock data to validate a production accuracy claim. Record the SQL data fingerprint, history window, folds, metric definition, and model configuration in the audit or handoff.

## Verified current status

The implementation audit records the latest verified SQL snapshot and repeatability evidence:

- 265,135 deduplicated forecast rows from the repaired Mitsubishi SQL snapshot
- 5,706 items, 87 product categories, 2,159 customers, and 69 industries
- Source coverage April 2021 through March 2025
- Live quick-run validation: Ensemble 85.20%, Trend 78.72%, SARIMA 83.48%, Random Forest 84.42%, LSTM 86.41%, XGBoost 75.87%
- NN held-out accuracy 96.92% with 83.73% balanced accuracy and a 95.81% last-month baseline
- TR held-out accuracy 89.61% with 81.80% balanced accuracy and an 86.49% last-month baseline
- Scores are repeatable for the same SQL fingerprint, code, model profile, and validation protocol; they are evidence, not a future guarantee

Do not replace these values with defaults or display 100% merely because a model has not been trained. An unavailable or stale model must stay unavailable or stale.

## Current remaining scope

These are decisions or deployment capabilities, not reasons to rewrite working code without evidence:

1. NN/TR fresh-month monitoring and origin-frozen certification for classifier regressors.
2. Vendor mappings, purchase orders, receipts, warehouse balances, and confirmed supplier lead times.
3. Native daily/weekly model training for every engine; current engines fit monthly and allocate daily/weekly views.
4. Exact full notebook search parity for every September experiment.
5. Serialized fitted-estimator deployment, production A/B routing, and binary-weight rollback. The registry currently records reproducible runs and active revisions.
6. Multi-worker scheduling, shared durable job storage, and full user authentication for a deployed multi-user system.
7. Business-owner confirmation of the composite order-line deduplication rule and any additional Mitsubishi fiscal reporting policy.

## Rules for future Claude Code changes

- Start with `git status`, read this guide and the implementation audit, and inspect the current code before proposing edits.
- Preserve Mitsubishi source tables and original source fields. Any reduction for forecasting must be explicit, documented, and tested.
- Keep all SQL access behind `backend/app/data/adapter.py`; do not add direct database queries to React or duplicate schema assumptions in individual models.
- Keep forecast results and validation metadata together. Include data fingerprints and validation protocol in new result payloads.
- Keep scenario edits separate from model forecasts and historical accuracy. Dragging or editing a preview must not recompute or silently change model scores.
- Treat NN/TR as separate classifiers and keep their experimental forecast-signal path opt-in until origin-safe validation is certified.
- Use the existing worker isolation and bounded job queue for model changes. Avoid importing heavy native model libraries in the FastAPI request process unless the existing contract requires it.
- Add tests for behavior and data rules, not tests that merely mirror implementation details.
- Run backend tests, frontend build/lint, and a SQL-backed smoke check after meaningful changes. Update `docs/IMPLEMENTATION_AUDIT.md` or a session handoff when verified status changes.
- Do not claim that a score is proven for future demand. State the data snapshot, holdouts, metric, and limitations.
