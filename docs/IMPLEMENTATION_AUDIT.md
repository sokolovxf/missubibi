# Implementation audit — 21 September 2026

## Evidence and source state

Local HEAD and GitHub `sokolovxf/missubibi` both resolved to `00ba32a75bae161ed678fde56851c6b1d90ed576` before changes. The adapter, trend engine, and plan were untracked local work; their intent was retained while repairing their implementations. Source SQL tables were preserved. Code was pushed on codex/forecast-planning-workspace; model artifacts stay local and ignored by Git.

Read `plan.txt`, both handoffs, the mockup, September model sources, current engine adapters, and the supplied MySQL schema. Live read-only verification returned 265,135 deduplicated rows, 5,706 items, 87 product categories, 2,159 customers, and 69 industries. Source coverage is April 2021–March 2025. Vendor mapping is absent from the live merged table and supplied schema.

## Mitsubishi source lineage audit

The four supplied workbooks were checked at sheet level. `RawData_Combined.xlsx`
contains exact copies of the three originals: Customer (2,159 rows), Item
(5,706 rows), and SalesOrderHistory (272,000 rows). The canonical sheet hashes
matched the originals before the SQL comparison: Customer
`36039626dd840be0d4a54163ba9402918a1ffbfd2742777cbb2eef811380526b`, Item
`094552938f0d85ba0dd72fb5f91fc5b17620df89eb1556d5d4ac8acde827020c`, and
SalesOrderHistory `e30616593d1b93fb8a220de107c23b84053acd93f0bd20e7be71cb878b01a68e`.

The SQL tables now reconcile to those originals. Customer and Item identifiers
and attributes match; the sales table contains all 272,000 source lines, all
original dates (2021-04-01 through 2025-03-31), all original order/item/price/
quantity fields, and 48 monthly totals. The derived revenue formula matches
`base_price × quantity` on every row. The repository seed was regenerated from
the repaired database so a future local import retains this state.

The first SQL load had stored a zero date for every sales row and a carriage
return on 271,999 month labels. Those artifacts were repaired from the source
files. The 13 source items with blank list prices are now marked as missing and
their 15 affected sales lines retain NULL list-price-derived values. The source
contains 6,865 extra exact duplicate lines (11,928 rows belong to duplicate
groups); the rows remain in SQL and are flagged. Forecasting intentionally uses
the 265,135-row canonical view after removing those extra copies. This is the
only source-row reduction in the forecast input and remains a business rule to
confirm.

## Implemented

- One SQL adapter used by the new planning service and legacy sales analytics. Preserves existing deduplication assumptions, strips imported carriage returns, supports item/product/customer/industry/vendor filters, and permits combinations of filters.
- Monthly source series with missing months filled through the global dataset cutoff; no last-sale truncation of quiet items.
- Monthly/daily/weekly/quarterly/yearly views. Calendar-day allocation conserves monthly totals, including leap days and partial boundary weeks. Daily/weekly values are explicitly estimates, not observed transactions.
- Corrected trend baseline, original-unit chronological error metrics, and approximate prediction intervals.
- Five forecasting adapters plus a weighted ensemble. Shared expanding-window validation, inverse-MASE weights, minimum weight 0.05, and explicit unavailable/excluded members. Validation errors are calculated at the selected output granularity, while fitting remains monthly.
- Isolated model worker processes with timeouts to prevent native OpenMP/PyTorch conflicts and contain engine crashes. API queue is bounded, job IDs are unique, and completed jobs expire.
- SARIMA now retains partial fiscal years and separates production horizon from validation horizon. Forecasts must continue from the actual history cutoff.
- Random Forest rolling features exclude the current target; recursive predictions rebuild lags, rolling statistics, and calendar features each step. Removed fixed forecast-fiscal-year label.
- LSTM uses consistent log1p inputs/targets and expm1 inversion, including zero-sales months. Verified real revenue forecasts in hundreds of millions of THB rather than near-zero values.
- XGBoost fixes: missing contextlib import, removed pandas Series.append, DatetimeIndex fiscal-year handling, independent holdout length, removal of direct target feature, and shifted rolling features. Installed the missing local Homebrew libomp runtime.
- New dashboard with restrained red/neutral styling, responsive layout, live history, sparklines, interval chart, draggable planning values, keyboard-editable period table, scenario slider/reset, CSV export, model comparison, data coverage, and classifier readiness/prediction screens.
- Horizon slider reruns an existing forecast on release (or keyboard change). Model forecast and edited scenario remain separate.
- Legacy forecast HTTP paths now delegate to the validated common service, including new trend/ensemble paths and classifier aliases. Baseline dashboard accuracy is no longer presented as model accuracy.
- Forecast-run registry stores parameters, data/code fingerprints, diagnostics, results, and active revisions with atomic writes. Recorded forecast rollback and comparison endpoints are available.
- Application-lifespan scheduler checks hourly and refreshes previously requested configurations on changed data or a new UTC month. Forecasts retrain inside fresh model worker processes; no exhaustive all-SKU/customer training is launched.
- NN/TR inference wrappers and SavedModel export helper. Next-month feature tensors, input schema, trained cutoff, diagnostics, and decision threshold travel with the model. Missing/stale exports return unavailable/stale rather than fake probabilities.

## Still dependent on missing artifacts or decisions

1. **NN/TR production scores:** implemented and trained locally. NN rev9 architecture plus equal HistGradientBoosting blend and TR rev8 architecture/features run in an isolated TensorFlow worker. Fit/validation/test months are chronological; preprocessing is fit-only, threshold is validation-only. SavedModel, preprocessing, predictions, diagnostics, and test-only historical signals are versioned locally. Quick (12 epoch maximum) and full (100 maximum) training are available. Dataset changes trigger refresh after CSV imports and in the hourly scheduler.
2. **Classifier exogenous regressors:** retained as experimental plumbing but disabled in the forecast service. Outer validation alone is insufficient: all engine-internal origins must also freeze signals. Validation-period classifier scores were excluded from historical exports because early stopping used those labels. Current probability indicators and item predictions work independently.
3. **CSV imports and vendors:** preview/validate UTF-8 CSV, commit append or replace-active transactions to dedicated MySQL tables, preserve original source tables, skip exact duplicates, and apply item/vendor mapping files. Actual vendor relationships must still be supplied.
4. **Daily/weekly true models:** the original transaction dates are now preserved in SQL, but the forecasting layer still fits monthly and allocates daily/weekly outputs. Native daily training is a separate model change.
5. **Full notebook parity:** existing RF/LSTM adapters are simplified service adaptations of the September notebooks, not identical full notebook experiments. This work fixes their correctness and integration; it does not claim to reproduce every search, feature trial, or diagnostic in the notebooks.
6. **Model registry scope:** versions reproducible forecast runs, not serialized fitted estimator binaries. A/B comparison is offline comparison of recorded runs; production traffic experiments and fitted-weight deployment rollback remain future work.
7. **Data rules:** composite order-line deduplication still needs business-owner confirmation. Calendar quarter/year boundaries are used; full Mitsubishi fiscal reporting is not implemented for those views.
8. **Operational scope:** local single-process application, in-memory job queue/cache, local registry. Multi-worker/distributed scheduling, authentication, and durable job recovery need separate deployment work.

## Corrected plan assumptions

The original plan inverted optimistic/pessimistic bounds. Higher demand/revenue is now the optimistic bound and lower demand/revenue the pessimistic bound. Weighted member bounds are approximate; they are not asserted to be calibrated ensemble 90% intervals. Partial calendar periods are labeled. MASE is undefined when the seasonal naive scale is zero; the system does not invent a validation score.

## Verification

Run `cd backend && .venv/bin/python -m unittest discover -s tests -v` and `npm --prefix frontend run build` / `npm --prefix frontend run lint` from the repository root as appropriate. Regression tests cover conservation, leap dates, compound filters, quiet tails, chronological metrics, RF leakage/recursion, LSTM inversion, ensemble exclusions, API validation, classifier unavailability, and registry rollback. Live engine and browser smoke checks are recorded in the session handoff.

## Latest verification and accuracy

15 unit tests pass, including CSV aliases/invalid values, transactional append/replace,
idempotence, vendor mapping, and known-denominator WAPE. Frontend build and lint pass.
Live company/monthly/revenue quick run: ensemble 85.20%, trend 78.72%, SARIMA 83.48%,
RF 84.42%, LSTM 86.41%, XGBoost 75.87%. Forecast accuracy means max(0,100-WAPE),
measured on two expanding validation windows; it is not classification accuracy.
NN held-out classification accuracy 96.92% (last-month baseline 95.81%, balanced
accuracy 83.73%); TR 89.61% (last-month baseline 86.49%, balanced accuracy 81.80%).
NN scores 5,706 items; TR scores 5,620 with sufficient
lag history. Prediction month is April 2025, the month after the dataset cutoff,
not the wall-clock current month. Classification tests cover June 2024–March 2025.

Training adaptations: the NN panel includes complete inactive months and a fit-only
positive-quantity demand threshold; this differs from the notebook cohort. Latest
item metadata is used where historical metadata is unavailable. Quick training is
not the notebook's full experiment/search. Accuracy is conditional on these choices.
No sample CSV was committed to the user's production dataset during verification;
transaction behavior was tested in an isolated SQLite database.

## Repeatability audit

On the live SQL snapshot (265,135 deduplicated rows; 48 monthly points from
2021-04 through 2025-03), two independent validation runs produced identical
scores to eight decimal places: Trend 78.72398414%, SARIMA 83.47812981%, Random
Forest 84.42170712%, LSTM 86.41353212%, and XGBoost 75.87171241%. The response now
includes the data fingerprint, validation protocol, history window, holdout count,
and fold summaries. The same snapshot, code, model profile, and protocol therefore
reproduce the same score. A score is expected to change after new SQL rows, a model
code/configuration change, or a different output granularity; a page refresh or
scenario edit does not change it.

The scores are evidence from historical out-of-sample tests, not a guarantee about
future months. Both classifier exports carry the repaired SQL fingerprint
`c98bf93f1ab1ad9817a99abd86d59b9264ffef1ccbbfc115db5a63a63271d6c0`. Fresh actuals should
be appended and monitored before treating any model as production-certified.
