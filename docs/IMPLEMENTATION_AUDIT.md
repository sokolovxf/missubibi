# Implementation audit — 20 September 2026

## Evidence and source state

Local HEAD and GitHub `sokolovxf/missubibi` both resolved to `00ba32a75bae161ed678fde56851c6b1d90ed576` before changes. The adapter, trend engine, and plan were untracked local work; their intent was retained while repairing their implementations. No database writes or remote Git history changes were made.

Read `plan.txt`, both handoffs, the mockup, September model sources, current engine adapters, and the supplied MySQL schema. Live read-only verification returned 265,135 deduplicated rows, 5,706 items, 87 product categories, 2,159 customers, and 69 industries. Source coverage is April 2021–March 2025. Vendor mapping is absent from the live merged table and supplied schema.

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

1. **NN/TR production scores and retraining:** the September folder contains Colab training source, not trained weights, fitted preprocessing, or next-month features. The source expects CSV exports and has notebook-only data-loading/training/plotting steps. A validated training run and export are required. Runtime wrappers and UI are ready; model training itself is not ported into a scheduled production pipeline.
2. **Classifier exogenous regressors:** not injected into forecasters. A single next-month count is not a historical regressor. Training requires dated, leakage-safe out-of-fold NN/TR signals and a future-feature policy. The signals endpoint exposes current planning indicators only when both exports exist.
3. **Vendor forecasts:** supported when `vendor_name` exists in the merged source; currently unavailable. No vendor values or relationships are guessed. A vendor-to-item/order mapping is needed.
4. **Daily/weekly true models:** source dates were unusable in the prior setup; this implementation fits monthly and allocates outputs. Native daily training requires reliable transaction dates.
5. **Full notebook parity:** existing RF/LSTM adapters are simplified service adaptations of the September notebooks, not identical full notebook experiments. This work fixes their correctness and integration; it does not claim to reproduce every search, feature trial, or diagnostic in the notebooks.
6. **Model registry scope:** versions reproducible forecast runs, not serialized fitted estimator binaries. A/B comparison is offline comparison of recorded runs; production traffic experiments and fitted-weight deployment rollback remain future work.
7. **Data rules:** composite order-line deduplication still needs business-owner confirmation. Calendar quarter/year boundaries are used; full Mitsubishi fiscal reporting is not implemented for those views.
8. **Operational scope:** local single-process application, in-memory job queue/cache, local registry. Multi-worker/distributed scheduling, authentication, and durable job recovery need separate deployment work.

## Corrected plan assumptions

The original plan inverted optimistic/pessimistic bounds. Higher demand/revenue is now the optimistic bound and lower demand/revenue the pessimistic bound. Weighted member bounds are approximate; they are not asserted to be calibrated ensemble 90% intervals. Partial calendar periods are labeled. MASE is undefined when the seasonal naive scale is zero; the system does not invent a validation score.

## Verification

Run `cd backend && .venv/bin/python -m unittest discover -s tests -v` and `npm --prefix frontend run build` / `npm --prefix frontend run lint` from the repository root as appropriate. Regression tests cover conservation, leap dates, compound filters, quiet tails, chronological metrics, RF leakage/recursion, LSTM inversion, ensemble exclusions, API validation, classifier unavailability, and registry rollback. Live engine and browser smoke checks are recorded in the session handoff.
