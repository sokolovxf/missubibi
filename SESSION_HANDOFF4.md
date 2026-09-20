# September 20 — accuracy, CSV imports, real classifiers

Implemented model validation accuracy (`max(0,100-WAPE)`) for solo models and
walk-forward ensemble; displayed in cards, comparison, and KPI. NN rev9 and TR
rev8 now train from MySQL with chronological splits in an isolated TensorFlow
worker, save versioned model/preprocessing/predictions, and serve actual item
probabilities. UI includes quick/full training, progress, classification accuracy,
balanced accuracy, AUC, baseline, confusion matrix, and borderline review filtering.

Both classifiers trained successfully with quick profile. NN 96.90% held-out
accuracy (95.81% persistence, 83.10% balanced), TR 89.60% (86.47% persistence,
81.80% balanced). 5,706 NN items and 5,620 TR items; prediction month April 2025
because source history ends March 2025. Weights are local under backend/var and
ignored by Git. Production forecasts remain independent of classifier regressors:
inner-origin leakage must be resolved before enabling experimental signal hooks.
Historical exports retain test months only because early stopping used validation.

CSV header button opens preview-first importer. Supports sales append/replace-active
and item/vendor mapping; preserves original MySQL tables. Imports use dedicated
SQL tables created on first commit, stage expiring local tokens, and skip exact
canonical duplicates. Automatic quick classifier refresh starts after commit;
hourly scheduler refreshes stale trained classifiers after source changes.
No test rows were written to live MySQL. Import transactions were tested in SQLite.

Verified: 14 backend unit tests, Python compile, frontend build/lint, live five-model
ensemble with per-member accuracy, browser classifier cards/metrics and import UI.
Live company monthly revenue ensemble score 85.20%; Trend78.72, SARIMA83.48,
RF84.42, LSTM86.41, XGBoost75.87. Accuracy is scope-dependent, not global.

Remaining plan items: safe classifier regressors through each inner backtest;
full notebook search/feature parity (RF/LSTM remain service adaptations); serialized
forecast-estimator rollback and production A/B routing; real vendor mappings and
reliable dated transactions for native daily/weekly fitting. See audit for details.
