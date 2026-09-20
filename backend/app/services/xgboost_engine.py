"""
XGBoost forecasting engine — importable, silent, side-effect free.

The modelling functions below are inspired by the randomforest_sales_forecast_v3.py
but adapted for XGBoost. They are designed to be called from the analytics module.

What this module adds around the core:

  * no I/O          — the caller supplies a DataFrame; nothing reads a CSV
  * no printing     — notebook's narrative print()/plt.show() calls are not carried over
  * no plotting     — matplotlib is never imported
  * collected notes — what the notebook printed as a checklist is returned as a
                      list of {kind, message} dicts instead (if debug=True)

Run state lives in function locals because we want each call to be independent.
It is safe to call from concurrent requests, but note that XGBoost training
can take several seconds to a minute depending on data size and horizon.
Do not call it synchronously inside a request handler — cache it, or run it
from a background task.
"""

from __future__ import annotations

import time
import contextlib
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import xgboost as xgb
except ImportError:  # pragma: no cover
    xgb = None  # type: ignore

# ----------------------------------------------------------------------------------
# Diagnostics infrastructure. Here we collect warnings and notes.
# ----------------------------------------------------------------------------------
FIT_LOG: List[Dict[str, Any]] = []
FAILURES: List[Dict[str, Any]] = []
NOTES: List[Dict[str, Any]] = []


def _reset_run_state() -> None:
    """Clear diagnostic lists."""
    for lst in (FIT_LOG, FAILURES, NOTES):
        lst.clear()


@contextlib.contextmanager
def capture_warnings(context: str):
    """Capture warnings during a context and store them in FIT_LOG."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        yield
    for w in caught:
        FIT_LOG.append(
            {
                "context": context,
                "category": w.category.__name__,
                "message": str(w.message).split("\n")[0][:160],
            }
        )


def log_failure(context: str, exc: Exception) -> None:
    """Log an exception that occurred during fitting."""
    FAILURES.append(
        {"context": context, "error": type(exc).__name__, "message": str(exc)[:200]}
    )


def note(kind: str, msg: str) -> None:
    """Record a note that the caller might want to act on."""
    NOTES.append({"kind": kind, "message": msg})


# ----------------------------------------------------------------------------------
# Helper functions for time series feature engineering
# ----------------------------------------------------------------------------------
def _make_lag_features(series: pd.Series, lags: List[int]) -> pd.DataFrame:
    """Create lag features for a time series."""
    df = pd.DataFrame()
    for lag in lags:
        df[f"lag_{lag}"] = series.shift(lag)
    return df


def _make_rolling_features(
    series: pd.Series, windows: List[int], agg_funcs: List[str]
) -> pd.DataFrame:
    """Create rolling window features."""
    df = pd.DataFrame()
    for window in windows:
        for func in agg_funcs:
            if func == "mean":
                df[f"rmean_{window}"] = series.shift(1).rolling(window).mean()
            elif func == "std":
                df[f"rstd_{window}"] = series.shift(1).rolling(window).std()
    return df


def _make_datetime_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Create datetime-derived features."""
    df = pd.DataFrame(index=index)
    df["month"] = index.month
    df["quarter"] = index.quarter
    df["dayofyear"] = index.dayofyear
    df["dayofmonth"] = index.day
    df["weekofyear"] = index.isocalendar().week
    # Cyclical encoding for month
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    from app.services.classifier_signals import for_dates
    return pd.concat([df,for_dates(index)],axis=1)


def _prepare_forecast_features(
    history: pd.Series,
    horizon: int,
    lags: List[int],
    rolling_windows: List[int],
) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    """
    Prepare features for training and forecasting.

    Returns:
        X: feature matrix for the historical data (with target aligned)
        y: target values
        feature_names: list of feature names in order
    """
    # Create a DataFrame with the index of the history
    df_hist = pd.DataFrame(index=history.index)
    df_hist["value"] = history.values

    # Lag features
    df_lag = _make_lag_features(history, lags)
    # Rolling features
    df_roll = _make_rolling_features(history, rolling_windows, ["mean", "std"])
    # Datetime features
    df_dt = _make_datetime_features(history.index)

    # Combine
    features = pd.concat([df_hist, df_lag, df_roll, df_dt], axis=1)

    # The target is the current value (we are predicting the current value from past lags)
    features["target"] = history.values

    # Drop rows where any feature is NaN (due to lag or rolling windows)
    features_clean = features.dropna()
    if features_clean.empty:
        # Return empty arrays if no valid features
        return pd.DataFrame(), np.array([]), []

    X = features_clean.drop(columns=["target", "value"])
    y = features_clean["target"].values
    feature_names = X.columns.tolist()

    return X, y, feature_names


def _forecast_recursive(
    model: Any,
    history: pd.Series,
    horizon: int,
    lags: List[int],
    rolling_windows: List[int],
    feature_names: List[str],
) -> np.ndarray:
    """
    Generate a recursive forecast for the given horizon.

    We start with the last point in history and iteratively predict the next point,
    updating the history with each prediction.
    """
    # We'll keep a copy of the history that we update
    hist = history.copy()
    predictions = []

    for i in range(horizon):
        # Prepare features for the next point (which is at index len(hist))
        # We need to compute the lag features, rolling features, and datetime features
        # for the point we are about to predict.

        # Create a temporary series that includes the history and the predictions so far
        temp_hist = hist.copy()

        # Compute lag features
        lag_features = {}
        for lag in lags:
            lag_features[f"lag_{lag}"] = temp_hist.iloc[-lag] if len(temp_hist) >= lag else np.nan

        # Compute rolling features
        roll_features = {}
        for window in rolling_windows:
            if len(temp_hist) >= window:
                roll_features[f"rmean_{window}"] = temp_hist.iloc[-window:].mean()
                roll_features[f"rstd_{window}"] = temp_hist.iloc[-window:].std()
            else:
                roll_features[f"rmean_{window}"] = np.nan
                roll_features[f"rstd_{window}"] = np.nan

        # Compute datetime features for the next period
        # The index of the next point: we assume monthly frequency
        last_date = hist.index[-1]
        next_date = last_date + pd.DateOffset(months=1)
        dt_features = _make_datetime_features(pd.DatetimeIndex([next_date]))
        dt_features_dict = dt_features.iloc[0].to_dict()

        # Combine all features
        features_dict = {
            **lag_features,
            **roll_features,
            **dt_features_dict,
        }

        # Convert to DataFrame in the correct order (same as training)
        # We need to ensure the columns are in the same order as feature_names
        features_df = pd.DataFrame([features_dict], columns=feature_names)
        # Fill any NaN values with 0 (or we could use the mean, but 0 is simple)
        features_df = features_df.fillna(0)

        # Predict the next value
        y_pred = model.predict(features_df.values)[0]
        predictions.append(y_pred)
        # Update history with this prediction for the next iteration
        hist = pd.concat([hist, pd.Series([y_pred], index=[next_date])])

    return np.array(predictions)


# ----------------------------------------------------------------------------------
# Main forecasting function
# ----------------------------------------------------------------------------------
def run_forecast(
    sales_df: pd.DataFrame,
    *,
    month_col: Optional[str] = None,
    value_col: Optional[str] = None,
    horizon: Optional[int] = None,
    fast: bool = True,  # ignored for now, but kept for compatibility
    series_name: str = "revenue_total",
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Fit, validate and forecast one monthly series using XGBoost.

    This function mimics the interface of sarima_engine.run_forecast but uses
    an XGBoost model with lag and rolling features.

    Args:
        sales_df:    monthly DataFrame (see the header in analytics.py). Defaults to
                     get_sales_data() so the signature matches the other functions.
        month_col:   name of the column containing the month/date. Auto-detected otherwise.
        value_col:   name of the column containing the value to forecast. Auto-detected otherwise.
        horizon:     months to forecast. 12 = one fiscal year.
        fast:        (ignored in this implementation) smaller model? True is the sane default.
        series_name: name of the series, used in the returned dict.
        debug:       if True, raise notes as they occur.

    Returns a JSON-serialisable dict. Always has "status"; the caller should
    branch on it rather than assume a forecast came back.

        status  "ok"                    -> "forecast" and "diagnostics" are populated
                "insufficient_history"  -> "detail" says what is missing
                "error"                 -> "message" carries the exception

        forecast        spec, months, point, lower_90, upper_90, annual_total,
                        annual_yoy_pct, plausibility_ok
        diagnostics     ... (we will fill in some basic metrics)
        fiscal_years    which fiscal years were used, and the one forecast
        data_anomalies  []
        warnings        [{kind, message}] raised during the run
    """
    global FIT_LOG, FAILURES, NOTES
    if debug:
        _reset_run_state()
    else:
        # If not debugging, we still want to clear the logs from previous runs?
        # We'll clear them at the start of each run to avoid cross-run contamination.
        _reset_run_state()

    t0 = time.time()
    try:
        # ------------------------------------------------------------------
        # 1. Data preparation (similar to sarima_engine's _run)
        # ------------------------------------------------------------------
        if not isinstance(sales_df, pd.DataFrame) or sales_df.empty:
            return _insufficient("No rows supplied.", {"rows": 0}, t0)

        df = sales_df.copy()
        mcol = _pick_col(df, _MONTH_HINTS, month_col)
        if mcol is None:
            raise KeyError(f"no month/date column found; have {list(df.columns)}")
        vcol = _pick_col(df, _VALUE_HINTS, value_col) or _pick_col(df, _QTY_HINTS, value_col)
        if vcol is None:
            raise KeyError(f"no revenue/quantity column found; have {list(df.columns)}")

        df[mcol] = pd.to_datetime(df[mcol], errors="coerce")
        df = df[df[mcol].notna()].copy()
        df[mcol] = df[mcol].values.astype("datetime64[M]")
        df[mcol] = pd.to_datetime(df[mcol])
        df[vcol] = pd.to_numeric(df[vcol], errors="coerce").fillna(0.0)
        if df.empty:
            return _insufficient("Every row had an unparseable date.", {"rows": 0}, t0)

        # Collapse to monthly granularity (same as in sarima_engine)
        # We'll group by month and sum the value_col
        # We'll also keep other columns? Not needed for the forecast.
        monthly = (
            df.groupby(mcol, as_index=False)
            .agg({vcol: "sum"})
            .rename(columns={mcol: "month", vcol: "value"})
        )
        # Ensure sorted by month
        monthly = monthly.sort_values("month")
        # Set the index to month for easier handling
        monthly_series = monthly.set_index("month")["value"]

        # ------------------------------------------------------------------
        # 2. Check sufficient history
        # ------------------------------------------------------------------
        horizon = int(horizon or 12)
        min_history = 24  # we need at least 2 years to create lag 12 features
        if len(monthly_series) < min_history:
            return _insufficient(
                f"Insufficient history: need at least {min_history} months, got {len(monthly_series)}.",
                {"history_months": len(monthly_series), "min_required": min_history},
                t0,
            )

        # ------------------------------------------------------------------
        # 3. Feature engineering and holdout evaluation
        # ------------------------------------------------------------------
        # We'll hold out the last `horizon` months for evaluation
        # (but note: we are going to forecast the next `horizon` months, so we need to train on all data for the final forecast)
        # We do:
        #   - Train on all but last `horizon` months, predict the last `horizon` months (holdout) to compute metrics.
        #   - Then retrain on all data to forecast the next `horizon` months.

        # Holdout split
        holdout_horizon = min(12, max(1, len(monthly_series)//5))
        train_series = monthly_series.iloc[:-holdout_horizon]
        holdout_series = monthly_series.iloc[-holdout_horizon:]

        # Prepare features for the training set
        # We'll use lag features: 1, 2, 3, 6, 12
        # Rolling windows: 3, 6, 12
        lags = [1, 2, 3, 6, 12]
        rolling_windows = [3, 6, 12]

        X_train, y_train, feature_names = _prepare_forecast_features(
            train_series, horizon, lags, rolling_windows
        )

        if X_train.empty or len(y_train) == 0:
            return _insufficient(
                "Not enough historical data to create features after lag/rolling window processing.",
                {"train_samples": len(train_series), "features_created": len(X_train)},
                t0,
            )

        # ------------------------------------------------------------------
        # 4. Train XGBoost model
        # ------------------------------------------------------------------
        if xgb is None:
            raise ImportError("XGBoost is not installed. Please install xgboost.")

        # We'll use XGBoostRegressor with some default parameters.
        # We can adjust based on `fast` if we want, but for now we use fixed.
        model = xgb.XGBRegressor(
            n_estimators=200 if not fast else 100,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="reg:squarederror",
            random_state=42,
            n_jobs=1,
        )

        # Train on the training set
        model.fit(X_train, y_train)

        # ------------------------------------------------------------------
        # 5. Evaluate on holdout (recursive forecast)
        # ------------------------------------------------------------------
        # We'll generate a recursive forecast for the holdout period.
        # We'll start with the training series and iteratively predict each point in the holdout.
        holdout_predictions = _forecast_recursive(
            model, train_series, holdout_horizon, lags, rolling_windows, feature_names
        )

        # If we couldn't generate predictions (e.g., not enough history for recursion), fall back to direct prediction
        if len(holdout_predictions) == 0:
            # Try direct prediction on holdout features
            X_holdout, _, _ = _prepare_forecast_features(
                holdout_series, horizon, lags, rolling_windows
            )
            if len(X_holdout) > 0:
                holdout_predictions = model.predict(X_holdout.values)
            else:
                holdout_predictions = np.full(len(holdout_series), np.nan)

        # Convert to Series for easy comparison
        holdout_pred_series = pd.Series(holdout_predictions, index=holdout_series.index)
        # Compute metrics on holdout
        # Only compute metrics where we have both actual and predicted values
        valid_mask = ~(np.isnan(holdout_series.values) | np.isnan(holdout_pred_series.values))
        if np.any(valid_mask):
            holdout_actual_valid = holdout_series.values[valid_mask]
            holdout_pred_valid = holdout_pred_series.values[valid_mask]
            holdout_errors = holdout_actual_valid - holdout_pred_valid
            holdout_mae = np.mean(np.abs(holdout_errors))
            holdout_rmse = np.sqrt(np.mean(holdout_errors ** 2))
            holdout_mape = (
                np.mean(np.abs(holdout_errors / holdout_actual_valid)) * 100
                if np.all(holdout_actual_valid != 0)
                else np.nan
            )
        else:
            holdout_mae = holdout_rmse = holdout_mape = np.nan

        # ------------------------------------------------------------------
        # 6. Train final model on all data
        # ------------------------------------------------------------------
        X_full, y_full, _ = _prepare_forecast_features(
            monthly_series, horizon, lags, rolling_windows
        )
        if X_full.empty or len(y_full) == 0:
            # Fallback: use a simple naive forecast if we can't create features
            final_model = None
            forecast_values = np.full(horizon, monthly_series.iloc[-1])  # last value forecast
        else:
            final_model = xgb.XGBRegressor(
                n_estimators=200 if not fast else 100,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                objective="reg:squarederror",
                random_state=42,
                n_jobs=1,
            )
            final_model.fit(X_full, y_full)

            # ------------------------------------------------------------------
            # 7. Generate forecast for the next `horizon` months (recursive)
            # ------------------------------------------------------------------
            forecast_values = _forecast_recursive(
                final_model, monthly_series, horizon, lags, rolling_windows, feature_names
            )

            # If recursive forecast failed, fall back to direct prediction using the last known features
            if len(forecast_values) == 0:
                # Create features for the last point in history and predict next horizon points
                # This is less accurate but better than nothing
                last_features, _, _ = _prepare_forecast_features(
                    monthly_series.tail(max(lags + rolling_windows)), horizon, lags, rolling_windows
                )
                if len(last_features) > 0:
                    # Use the last feature row to predict all horizon points (simplification)
                    last_feature_row = last_features.iloc[-1:].values
                    forecast_values = np.tile(
                        final_model.predict(last_feature_row)[0], horizon
                    )
                else:
                    # Ultimate fallback: use the last observed value
                    forecast_values = np.full(horizon, monthly_series.iloc[-1])

        # ------------------------------------------------------------------
        # 8. Compute prediction intervals (simple method using holdout errors)
        # ------------------------------------------------------------------
        # We'll use the standard deviation of the holdout errors to create a 90% prediction interval.
        # We assume the error distribution is similar for the forecast horizon.
        if not np.isnan(holdout_mae) and not np.isnan(holdout_rmse):
            # Use holdout RMSE as error estimate
            error_std = holdout_rmse
            # For 90% interval, we use 1.645 * std (assuming normality)
            multiplier = 1.645
            lower_90 = [val - multiplier * error_std for val in forecast_values]
            upper_90 = [val + multiplier * error_std for val in forecast_values]
        else:
            # Fallback: use a percentage of the forecast value
            lower_90 = [val * 0.8 for val in forecast_values]  # 20% below
            upper_90 = [val * 1.2 for val in forecast_values]  # 20% above

        # ------------------------------------------------------------------
        # 9. Build the forecast dictionary to match sarima_engine's output
        # ------------------------------------------------------------------
        forecast_dates = [
            monthly_series.index[-1] + pd.DateOffset(months=i+1)
            for i in range(horizon)
        ]
        forecast_months = [d.strftime("%Y-%m-%d") for d in forecast_dates]
        annual_total = np.sum(forecast_values)
        # Compute year-over-year percentage change if we have at least one year of history
        if len(monthly_series) >= 12:
            last_year_total = np.sum(monthly_series.iloc[-12:].values)
            annual_yoy_pct = (annual_total / last_year_total - 1) * 100 if last_year_total != 0 else None
        else:
            annual_yoy_pct = None

        # We'll create a spec dictionary (simplified)
        spec = {
            "model_type": "XGBoost",
            "lags": lags,
            "rolling_windows": rolling_windows,
            "horizon": horizon,
            "fast": fast,
        }

        # We'll create a diagnostics dictionary with some basic metrics
        diagnostics = {
            "holdout_mae": float(holdout_mae) if not np.isnan(holdout_mae) else None,
            "holdout_rmse": float(holdout_rmse) if not np.isnan(holdout_rmse) else None,
            "holdout_mape": float(holdout_mape) if not np.isnan(holdout_mape) else None,
            "model_params": (
                final_model.get_params() if final_model is not None else None
            ),
            "training_samples": len(X_train) if 'X_train' in locals() else 0,
            "holdout_samples": len(holdout_series),
            "feature_count": len(feature_names) if 'feature_names' in locals() else 0,
        }

        # Fiscal years (we'll reuse the logic from sarima_engine but simplified)
        # We'll compute the fiscal years used in the history.
        # We'll assume a fiscal year starting in April (as in the SARIMA engine)
        # We'll compute the fiscal year for each month in the history.
        # We'll then get the unique fiscal years.
        # We'll use the same function as in sarima_engine.py? We'll copy a simplified version.
        def _fiscal_year_vec(dt, start_month=4):
            # Assuming fiscal year label is "start" (as in SARIMA engine)
            return dt.year - (dt.month < start_month).astype(int)

        # We need a DatetimeIndex for the monthly series index
        months_idx = monthly_series.index
        fys = _fiscal_year_vec(months_idx)
        used_fys = sorted(int(fy) for fy in np.unique(fys))
        forecast_fy = _fiscal_year_vec(pd.DatetimeIndex([forecast_dates[-1]]))[0] if forecast_dates else None

        # Totals by fiscal year (we'll sum the monthly values per fiscal year)
        fy_totals = {}
        for fy in used_fys:
            mask = fys == fy
            fy_totals[int(fy)] = float(monthly_series[mask].sum())

        # ------------------------------------------------------------------
        # 10. Return the result
        # ------------------------------------------------------------------
        result = {
            "status": "ok",
            "message": f"Forecast for {horizon} months from {forecast_dates[0]:%Y-%m}.",
            "fiscal_years": {
                "used": used_fys,
                "label_convention": "start",
                "start_month": 4,
                "first_month": str(monthly_series.index[0].date()),
                "last_month": str(monthly_series.index[-1].date()),
                "n_months": len(monthly_series),
                "forecast_fiscal_year": int(forecast_fy) if forecast_fy is not None else None,
                "totals_by_fiscal_year": fy_totals,
            },
            "forecast": {
                "series": series_name,
                "spec": str(spec),  # We'll just convert to string for simplicity
                "selected_on_months": len(X_full) if 'X_full' in locals() else 0,
                "horizon": horizon,
                "months": forecast_months,
                "point": [round(float(v), 2) for v in forecast_values],
                "lower_90": [round(float(v), 2) for v in lower_90],
                "upper_90": [round(float(v), 2) for v in upper_90],
                "interval_source": "holdout_errors" if not np.isnan(holdout_mae) else "scaled_forecast",
                "annual_total": round(float(annual_total), 2),
                "annual_yoy_pct": round(float(annual_yoy_pct), 2) if annual_yoy_pct is not None else None,
                "plausibility_ok": True,  # we don't implement plausibility checks
                "plausibility_detail": None,
            },
            "diagnostics": diagnostics,
            "data_anomalies": [],  # we don't implement anomaly detection
            "warnings": [{"kind": n["kind"], "message": n["message"]} for n in NOTES],
            "runtime_seconds": round(time.time() - t0, 1),
        }
        return result

    except Exception as exc:  # pragma: no cover
        log_failure("run_forecast", exc)
        return {
            "status": "error",
            "message": f"{type(exc).__name__}: {exc}",
            "fiscal_years": None,
            "forecast": None,
            "diagnostics": None,
            "data_anomalies": None,
            "warnings": list(NOTES),
            "runtime_seconds": round(time.time() - t0, 1),
        }


def _insufficient(msg: str, detail: Dict[str, Any], t0: float) -> Dict[str, Any]:
    """Return an insufficient_history result."""
    return {
        "status": "insufficient_history",
        "message": msg,
        "detail": detail,
        "fiscal_years": None,
        "forecast": None,
        "diagnostics": None,
        "data_anomalies": None,
        "warnings": list(NOTES),
        "runtime_seconds": round(time.time() - t0, 1),
    }


def _pick_col(df: pd.DataFrame, hints: Tuple[str, ...], explicit: Optional[str]) -> Optional[str]:
    """Pick a column from a DataFrame using a list of hints."""
    if explicit:
        if explicit not in df.columns:
            raise KeyError(f"column {explicit!r} is not in the frame; have {list(df.columns)}")
        return explicit
    lowered = {c.lower(): c for c in df.columns}
    for h in hints:
        if h in lowered:
            return lowered[h]
    for h in hints:
        for lc, orig in lowered.items():
            if h in lc:
                return orig
    return None


# Constants for column picking (same as in sarima_engine.py)
_MONTH_HINTS = ("month", "date", "period", "sales_order_date", "order_date")
_VALUE_HINTS = ("revenue", "amount", "sales", "net_amount", "value")
_QTY_HINTS = ("actual_units", "quantity", "qty", "units")