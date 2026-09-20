# Forecast planning workspace

Start from the repository root:

```sh
cd backend
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8100
```

In a second terminal:

```sh
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5174. Vite proxies `/api` to port 8100. MySQL configuration stays in `backend/.env`; it is not exposed in the browser. On macOS, XGBoost requires `brew install libomp`. PyTorch is now declared in pyproject.toml. TensorFlow is optional: `uv sync --extra classifiers` only when deploying NN/TR exports.

## API

- `GET /api/planning/options` — distinct dimension values.
- `GET /api/planning/history` — source/allocated history.
- `POST /api/planning/forecast/run` — validated request, returns unique job ID.
- `GET /api/planning/forecast/{job_id}` — running state or result; unknown/expired jobs return 404.
- `POST /api/planning/classifier/{nn|tr}/predict` — optional `{"item":"SKU"}` filter.
- `GET /api/planning/classifier/signals` — current exported classifier planning indicators.
- `GET /api/planning/registry` — saved configurations and active revisions.
- `GET /api/planning/registry/{revision}` — recorded forecast/metadata.
- `POST /api/planning/registry/{revision}/activate` — make a recorded forecast the active revision.
- `GET /api/planning/compare?a=...&b=...` — compare two recorded revisions.

Forecast request:

```json
{
  "model": "ensemble",
  "dimension": "item",
  "dimension_value": "your-item-code",
  "filters": {"customer": "your-customer"},
  "value_col": "revenue",
  "granularity": "monthly",
  "horizon": 12,
  "fast": true
}
```

Models: trend, sarima, randomforest, lstm, xgboost, ensemble. Dimensions: total, item, product, customer, industry, vendor. Metric: revenue or actual_units. Frequencies: daily, weekly, monthly, quarterly, yearly. Maximums: 120 periods, 40 quarters, or 10 years. Queue: two executing/four outstanding jobs. Worker timeout: 600 seconds per individual model fit. Registry/cache keys isolate all request parameters and data fingerprints.

## Classifier exports

The repository has notebook source but no trained classifier artifacts. Do not run Colab exports on API import. Complete training and generate **next-month** feature rows with the notebook's fitted scalers, category vocabularies, and exact feature definitions. Validation/test metrics must come from held-out data.

`backend/scripts/export_classifier.py` provides `export_classifier(model, ...)` for use at the end of that workflow. Supply input tensors by model input name, one row per SKU, and `YYYY-MM-DD` cutoff/prediction dates. The serving graph must include any remaining preprocessing. Output directories:

```
backend/var/classifiers/nn/{manifest.json,features.json,saved_model/}
backend/var/classifiers/tr/{manifest.json,features.json,saved_model/}
```

The runtime rejects mismatched schemas, invalid probabilities, and feature snapshots that do not target the next month of the SQL dataset. These are inference snapshots, not a replacement for a leakage-safe production feature pipeline. Original NN/TR feature engineering and training still need a validated production port before automatic classifier retraining can be enabled. Forecast engines deliberately do not treat unavailable classifier probabilities as zero-valued regressors.

`CLASSIFIER_MODEL_DIR` and `FORECAST_REGISTRY_DIR` can override local paths. Keep artifacts outside Git. Run a single backend process for the built-in scheduler; in a distributed deployment, replace it with one durable scheduler and worker queue. `python -m app.services.retraining` performs one refresh check manually.


### CSV import and trained classifiers (September 20 update)

`POST /api/planning/imports/preview?filename=sales.csv` accepts a raw UTF-8 CSV body,
not multipart. Required columns: month,item,actual_units,revenue; optional product,
customer,industry,vendor. Two-column item,vendor files update mappings. Preview
returns errors and an expiring token. `POST /imports/commit` takes token and mode
(append or replace). SQL source tables remain intact. Dates normalize to month.
An import starts quick classifier refresh; changed data invalidates old predictions.

Install classifier dependencies with `uv sync --extra classifiers`. Run training via
`POST /classifier/train` with `{ "fast": true }`, poll `/classifier/training`, or
run `.venv/bin/python -m app.services.classifier_train_worker` from backend.
Use `--full` for up to 100 epochs. Local trained artifacts live under
`backend/var/classifiers/{nn,tr}/versions/` and current.json selects deployment.
The UI now serves real item probabilities and held-out diagnostics. Historical
signals are test-only; forecast injection stays disabled pending origin-safe inner
validation. See the audit for accuracy interpretation and remaining limitations.
