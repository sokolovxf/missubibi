# 2025 historical data package for forecast validation

This folder is the pitch-ready 2025 data slice from the verified Mitsubishi Electric source workbook. It is intended for tomorrow's model validation and dashboard demonstration.

## What the pitch dataset contains

- Source workbook: `DATA ORIGINAL + MERGED FILE/RawData_Combined.xlsx`
- Source sheet: `SalesOrderHistory`
- Source coverage: 1 April 2021 through 31 March 2025
- Available 2025 slice: 1 January 2025 through 31 March 2025
- 2025 transaction rows: 17,020
- 2025 months: January, February, and March 2025

The source snapshot ends on 31 March 2025. This package therefore represents the complete available 2025 slice, not an invented full-year January–December 2025 dataset.

## Files

- [`mitsubishi_sales_2025.csv`](./mitsubishi_sales_2025.csv) - line-level 2025 transactions with the original sales fields.
- [`mitsubishi_sales_2025_monthly.csv`](./mitsubishi_sales_2025_monthly.csv) - monthly validation summary with transaction rows, unique orders, unique items, unique customers, units, and revenue in THB.
- [`manifest.json`](./manifest.json) - source lineage, date range, row count, and SHA-256 checksums.
- [`dashboard-mini-guide.pdf`](./dashboard-mini-guide.pdf) - short visual explanation of the dashboard and validation workflow.

## How to use it for the pitch

1. Open `mitsubishi_sales_2025_monthly.csv` for a quick actual-versus-forecast comparison.
2. Use `mitsubishi_sales_2025.csv` when a model needs transaction-level inputs.
3. Train or run a forecast using the January and February history, then compare the predicted March values with the actual March values.
4. Report the validation period and metric definition with every score. Do not present the March comparison as a full-year 2025 result.
5. Use the dashboard's Forecast workspace to choose a model, dimension, metric, and horizon. The Model performance view shows chronological validation scores, while the Data & coverage view shows the source period.

## Dashboard workflow

```text
2025 CSV or canonical MySQL history
            |
            v
Select model, dimension, metric, and horizon
            |
            v
FastAPI planning job reads the SQL adapter
            |
            v
Trend / SARIMA / Random Forest / LSTM / XGBoost
            |
            v
Ensemble combines available members using chronological validation weights
            |
            v
Dashboard displays forecast, ranges, history, WAPE, accuracy, and model comparison
            |
            v
Compare predicted values with the held-out 2025 actuals
```

The dashboard's daily and weekly planning views allocate the monthly source contract. They should be described as planning estimates, not as observed daily transactions.

## Getting the package from GitHub

```bash
git clone https://github.com/sokolovxf/missubibi.git
cd missubibi
git fetch origin
git switch --track origin/codex/forecast-planning-workspace
```

If the repository is already cloned:

```bash
git fetch origin
git switch codex/forecast-planning-workspace
git pull --ff-only
```

The pitch dataset is under `pitch/2025/`. The original source workbooks and the canonical SQL snapshot remain unchanged elsewhere in the repository.

## Data definitions

- `Base Price` is the source transaction price used to calculate the monthly `revenue_thb` summary as `Base Price × Quantity`.
- `Quantity` is the source order-line quantity.
- `transaction_rows` counts source order lines in the month.
- `unique_orders`, `unique_items`, and `unique_customers` are distinct identifier counts in the slice.
- MAPE, RMSE, and WAPE are regression validation metrics. NN Rev 9 and Tabular Transformer Rev 8 are classifiers and use accuracy, balanced accuracy, ROC AUC, and confusion matrices instead.

## Provenance and integrity

The line-level and monthly files were generated from the workbook's `SalesOrderHistory` sheet. Their checksums and the exact source coverage are recorded in `manifest.json`. Do not overwrite the canonical source data to prepare a pitch extract; create a new dated slice instead.
