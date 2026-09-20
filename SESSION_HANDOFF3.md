# Session handoff 3 — Planning workspace and forecast integration

20 September 2026. See `docs/IMPLEMENTATION_AUDIT.md` for the full plan audit, including explicit remaining gaps; `backend/PLANNING.md` for runtime/API instructions. `plan.txt` now links both instead of implying the old checklist is current.

## Running locally

Frontend: http://127.0.0.1:5174. Backend: http://127.0.0.1:8100. Database remains MySQL. Vite proxies `/api`; no credentials enter the frontend. Local servers were started and browser-tested during this session.

## Important findings and corrections

- SQL contains 265,135 deduplicated order lines, April 2021–March 2025. Live tables are only Customerfile_Data, Itemfile_Data, Sales_Order_Merged. No vendor mapping exists.
- Unfinished adapter queried a nonexistent vendor column; weekly expansion also lost monthly totals. Corrected both; source remains monthly and allocated daily/weekly views are labeled.
- RF previously leaked current targets through rolling statistics and repeated unchanged features for each future step. Fixed shifted features and true recursive rebuilding.
- LSTM log mode fed raw revenue into its network. Fixed consistent log1p transforms, zero handling, and expm1 inversion.
- XGBoost had a missing native dependency, import, deprecated pandas append, direct target leakage, rolling leakage, and DatetimeIndex issue. Corrected; libomp installed locally.
- XGBoost/PyTorch together caused a native crash. Each model now runs in its own bounded subprocess, preserving API availability and keeping notebook global state separate.
- SARIMA no longer discards partial fiscal years or requires history as long as the requested production horizon.
- Legacy forecast routes share the new implementation rather than maintaining separate job stores/validation.

## Verified

- Frontend production build and ESLint passed.
- 11 backend regression tests passed (calendar conservation/leap days; combined filters/quiet tails; trend metrics; RF leakage and recursive features; LSTM scale; ensemble exclusions/weights; request validation; registry rollback; missing classifier handling).
- All five models successfully returned live 12-month forecasts beginning April 2025. Isolated ensemble run ~20 seconds.
- Live ensemble two-window MASE: Trend 0.608, SARIMA 0.474, RF 0.445, LSTM 0.386, XGBoost 0.693. These are small-sample model-selection scores, not independently held-out ensemble performance claims.
- Live API: daily 14 periods, weekly 8, quarterly 4, yearly 3; legacy trend route; invalid vendor selection 422; registry records; classifier unavailable responses.
- Browser: live ensemble run; all five models and their weights in comparison; keyboard scenario adjustment; honest classifier unavailable page. Responsive narrow and desktop layouts inspected.

## Remaining dependencies / deliberate limits

NN/TR trained exports, fitted preprocessing, and future feature snapshots are absent. Their source notebooks still need a validated production training/feature port. Inference wrappers/export helper exist; no mock scores are shown. Historical out-of-fold classifier signals are required before including classifiers as forecast regressors. Vendor forecasts need an actual mapping. RF/LSTM remain service adaptations, not complete experimental notebook parity. Registry rollback activates recorded forecasts, not fitted-model binary deployments. No production A/B traffic experiment exists.

The built-in single-process scheduler checks hourly, refreshing configurations previously run by planners on new data or a new month. It is not a distributed scheduler or an exhaustive all-items training sweep. Registry artifacts in `backend/var/` are ignored by Git.
