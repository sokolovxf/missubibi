from app.data.sales_data import get_sales_data

def get_dashboard_summary():
    df = get_sales_data()

    total_units = int(df["actual_units"].sum())
    total_revenue = int(df["revenue"].sum())

    forecast_accuracy = (
        1
        - (
            abs(df["actual_units"] - df["forecast_units"]).sum()
            / total_units
        )
    ) * 100

    top_product = (
        df.groupby("product")["revenue"]
        .sum()
        .sort_values(ascending=False)
        .index[0]
    )

    return {
        "total_units": total_units,
        "total_revenue": total_revenue,
        "forecast_accuracy": round(forecast_accuracy, 2),
        "top_product": top_product,
    }


def get_monthly_sales():
    df = get_sales_data()

    monthly = (
        df.groupby("month")
        .agg(
            actual_units=("actual_units", "sum"),
            forecast_units=("forecast_units", "sum"),
            revenue=("revenue", "sum"),
        )
        .reset_index()
    )

    return monthly.to_dict(orient="records")


def get_product_summary():
    df = get_sales_data()

    products = (
        df.groupby("product")
        .agg(
            actual_units=("actual_units", "sum"),
            forecast_units=("forecast_units", "sum"),
            revenue=("revenue", "sum"),
        )
        .reset_index()
        .sort_values("revenue", ascending=False)
    )

    return products.to_dict(orient="records")


def get_ai_insights():
    df = get_sales_data()

    insights = []

    # ---------------------------------------------------------
    # 1. DEMAND TREND
    # ---------------------------------------------------------

    monthly = (
        df.groupby("month")["actual_units"]
        .sum()
        .reset_index()
    )

    if len(monthly) >= 2:
        first_month_units = monthly.iloc[0]["actual_units"]
        last_month_units = monthly.iloc[-1]["actual_units"]

        if first_month_units > 0:
            demand_change = (
                (last_month_units - first_month_units)
                / first_month_units
            ) * 100
        else:
            demand_change = 0

        if demand_change > 5:
            insights.append(
                {
                    "type": "positive",
                    "title": "Demand increasing",
                    "message": (
                        f"Actual demand increased by "
                        f"{demand_change:.1f}% across the available period."
                    ),
                }
            )
        elif demand_change < -5:
            insights.append(
                {
                    "type": "warning",
                    "title": "Demand declining",
                    "message": (
                        f"Actual demand decreased by "
                        f"{abs(demand_change):.1f}% across the available period."
                    ),
                }
            )
        else:
            insights.append(
                {
                    "type": "neutral",
                    "title": "Demand stable",
                    "message": (
                        "Overall demand remains relatively stable "
                        "across the available period."
                    ),
                }
            )

    # ---------------------------------------------------------
    # 2. FORECAST RISK
    # ---------------------------------------------------------

    products = (
        df.groupby("product")
        .agg(
            actual_units=("actual_units", "sum"),
            forecast_units=("forecast_units", "sum"),
        )
        .reset_index()
    )

    products["forecast_error_pct"] = (
        (
            products["forecast_units"]
            - products["actual_units"]
        )
        / products["actual_units"].replace(0, 1)
    ) * 100

    highest_error_product = products.iloc[
        products["forecast_error_pct"].abs().argmax()
    ]

    error = highest_error_product["forecast_error_pct"]

    if abs(error) >= 5:
        if error > 0:
            message = (
                f"{highest_error_product['product']} is being "
                f"forecast {abs(error):.1f}% above actual demand. "
                "Review inventory planning."
            )
        else:
            message = (
                f"{highest_error_product['product']} is being "
                f"forecast {abs(error):.1f}% below actual demand. "
                "Potential demand risk should be monitored."
            )

        insights.append(
            {
                "type": "warning",
                "title": "Forecast risk",
                "message": message,
            }
        )
    else:
        insights.append(
            {
                "type": "neutral",
                "title": "Forecast stable",
                "message": (
                    "Product-level forecast differences "
                    "remain within a relatively stable range."
                ),
            }
        )

    # ---------------------------------------------------------
    # 3. FORECAST ACCURACY
    # ---------------------------------------------------------

    total_units = df["actual_units"].sum()

    if total_units > 0:
        forecast_accuracy = (
            1
            - (
                abs(
                    df["actual_units"]
                    - df["forecast_units"]
                ).sum()
                / total_units
            )
        ) * 100
    else:
        forecast_accuracy = 0

    if forecast_accuracy >= 95:
        insights.append(
            {
                "type": "positive",
                "title": "Forecast performing well",
                "message": (
                    f"Current forecast accuracy is "
                    f"{forecast_accuracy:.1f}%, above the 95% target."
                ),
            }
        )
    elif forecast_accuracy >= 90:
        insights.append(
            {
                "type": "neutral",
                "title": "Forecast performance acceptable",
                "message": (
                    f"Current forecast accuracy is "
                    f"{forecast_accuracy:.1f}%. "
                    "Further model improvement may be beneficial."
                ),
            }
        )
    else:
        insights.append(
            {
                "type": "warning",
                "title": "Forecast needs attention",
                "message": (
                    f"Current forecast accuracy is "
                    f"{forecast_accuracy:.1f}%. "
                    "The forecasting model may require improvement."
                ),
            }
        )

    return insights


# =============================================================================
# SARIMA FORECAST
# =============================================================================
# Wraps the v7 SARIMA engine (app/services/sarima_engine.py, extracted verbatim
# from backend/sarima_sales_forecast_v7.py) behind one function.
#
# WHAT IT EXPECTS
#   A monthly DataFrame in this project's own shape - the same frame
#   get_sales_data() returns:
#
#     month          "2025-01" / a date / anything pd.to_datetime parses  (required)
#     revenue        numeric                                              (preferred)
#     actual_units   numeric - used only if there is no revenue column
#
#   Extra columns (product, customer, forecast_units) are ignored. Rows are
#   summed per calendar month, so transaction-level rows work too.
#
#   HISTORY IS THE BINDING CONSTRAINT. The walk-forward validation needs at
#   least MIN_TRAIN_MONTHS + horizon = 36 months, and those months must fall in
#   COMPLETE fiscal years (April-March). 48 months / 4 whole fiscal years is
#   what the model was tuned on. The 12-month mock data in app/data/mock_data.py
#   is far short of this, so this function returns status="insufficient_history"
#   on it - by design, not as a failure.
#
# COST
#   A run fits several hundred SARIMA models: roughly 40-90 seconds on 48 months
#   of history. Results are cached per input frame, but the FIRST call is slow.
#   Do NOT wire this straight into a request handler - call it from a background
#   task or a scheduled job and serve the cached dict.
# =============================================================================

import hashlib

import pandas as pd

from app.services import sarima_engine

_FORECAST_CACHE: dict = {}
_CACHE_LIMIT = 8


def _frame_fingerprint(df, horizon, fast, value_col, month_col):
    """Cache key. Uses the frame's values, so a changed dataset misses the cache."""
    h = hashlib.sha256()
    h.update(repr((sorted(map(str, df.columns)), len(df), horizon,
                   bool(fast), value_col, month_col)).encode())
    try:
        h.update(pd.util.hash_pandas_object(df, index=False).values.tobytes())
    except Exception:
        h.update(df.to_csv(index=False).encode("utf-8", "ignore"))
    return h.hexdigest()


def get_sarima_forecast(
    sales_df=None,
    *,
    horizon=12,
    fast=True,
    value_col=None,
    month_col=None,
    series_name="revenue_total",
    use_cache=True,
    debug=False,
):
    """Forecast the next `horizon` months and report how much to trust it.

    Args:
        sales_df:    monthly DataFrame (see the header above). Defaults to
                     get_sales_data() so the signature matches the other
                     functions in this module.
        horizon:     months to forecast. 12 = one fiscal year.
        fast:        smaller order-search grid. True is the sane default for a
                     backend; False matches the notebook exactly and is slower.
        value_col:   force the column to forecast. Auto-detected otherwise.
        month_col:   force the month column. Auto-detected otherwise.
        use_cache:   reuse a previous result for an identical frame.
        debug:       print the engine's notes as they are raised.

    Returns a JSON-serialisable dict. Always has "status"; the caller should
    branch on it rather than assume a forecast came back:

        status  "ok"                    -> "forecast" and "diagnostics" are populated
                "insufficient_history"  -> "detail" says what is missing
                "error"                 -> "message" carries the exception

        forecast        spec, months, point, lower_90, upper_90, annual_total,
                        annual_yoy_pct, plausibility_ok
        diagnostics     wf1 / wf12, each with accuracy_pct, mase_pooled,
                        bias_pct (negative = forecast runs HIGH),
                        beats_naive, and a bootstrap vs_baseline block;
                        plus ljung_box_p, negative_predictions_clipped
        fiscal_years    which fiscal years were used, and the one forecast
        data_anomalies  fiscal years that deviate sharply from the median
        warnings        [{kind, message}] raised during the run
    """
    if sales_df is None:
        sales_df = get_sales_data()

    key = None
    if use_cache:
        try:
            key = _frame_fingerprint(sales_df, horizon, fast, value_col, month_col)
            if key in _FORECAST_CACHE:
                cached = dict(_FORECAST_CACHE[key])
                cached["cached"] = True
                return cached
        except Exception:
            key = None                      # an unhashable frame just skips the cache

    result = sarima_engine.run_forecast(
        sales_df,
        month_col=month_col,
        value_col=value_col,
        horizon=horizon,
        fast=fast,
        series_name=series_name,
        debug=debug,
    )
    result["cached"] = False

    if key is not None and result.get("status") == "ok":
        if len(_FORECAST_CACHE) >= _CACHE_LIMIT:
            _FORECAST_CACHE.pop(next(iter(_FORECAST_CACHE)))
        _FORECAST_CACHE[key] = result

    return result


# =============================================================================
# FORECAST LAB — slice any product/customer out of get_sales_data() and
# forecast just that series. This is what backs the customizable Forecast
# Lab panel: the dashboard's default KPIs still call get_sarima_forecast()
# directly (dimension="total" here reproduces that exact series_name,
# "revenue_total", so nothing about the existing behaviour changes).
# =============================================================================

def get_forecast_options():
    """Distinct products/customers the Forecast Lab can slice a series by."""
    df = get_sales_data()
    return {
        "products": sorted(df["product"].dropna().unique().tolist()),
        "customers": sorted(df["customer"].dropna().unique().tolist()),
    }


def _slice_series(dimension="total", dimension_value=None):
    """Collapse get_sales_data() down to a single monthly series.

    dimension="total" aggregates everything (dimension_value is ignored).
    dimension="product" / "customer" filters to one dimension_value first.
    Returns a month-level frame with both revenue and actual_units summed,
    so the caller can forecast either column without a second query.
    """
    df = get_sales_data()

    if dimension == "product":
        if not dimension_value:
            raise ValueError("dimension_value is required when dimension='product'")
        df = df[df["product"] == dimension_value]
    elif dimension == "customer":
        if not dimension_value:
            raise ValueError("dimension_value is required when dimension='customer'")
        df = df[df["customer"] == dimension_value]
    elif dimension != "total":
        raise ValueError(f"unknown dimension: {dimension!r}")

    if df.empty:
        raise ValueError(f"no rows for dimension={dimension!r} value={dimension_value!r}")

    return (
        df.groupby("month", as_index=False)
        .agg(revenue=("revenue", "sum"), actual_units=("actual_units", "sum"))
    )


def get_sarima_forecast_for(
    dimension="total",
    dimension_value=None,
    value_col="revenue",
    horizon=12,
    fast=True,
    use_cache=True,
    debug=False,
):
    """Slice a series by dimension/dimension_value, then forecast it.

    dimension="total" + value_col="revenue" reproduces the original
    whole-company forecast (series_name="revenue_total") the dashboard
    KPIs already depend on — this function is a strict superset, not a
    replacement, of calling get_sarima_forecast() directly.

    Raises ValueError before ever touching SARIMA if dimension_value is
    missing/unmatched — the caller (routes.py) turns that into a clean
    "error" status rather than a raw 500.
    """
    monthly = _slice_series(dimension, dimension_value)

    series_name = (
        f"{value_col}_total" if dimension == "total"
        else f"{dimension}:{dimension_value}:{value_col}"
    )

    return get_sarima_forecast(
        monthly,
        horizon=horizon,
        fast=fast,
        value_col=value_col,
        series_name=series_name,
        use_cache=use_cache,
        debug=debug,
    )


# =============================================================================
# XGBOOST FORECAST
# =============================================================================
# Wraps the XGBoost engine (app/services/xgboost_engine.py) behind one function.
#
# WHAT IT EXPECTS
#   A monthly DataFrame in this project's own shape - the same frame
#   get_sales_data() returns:
#
#     month          "2025-01" / a date / anything pd.to_datetime parses  (required)
#     revenue        numeric                                              (preferred)
#     actual_units   numeric - used only if there is no revenue column
#
#   Extra columns (product, customer, forecast_units) are ignored. Rows are
#   summed per calendar month, so transaction-level rows work too.
#
#   HISTORY IS THE BINDING CONSTRAINT. The model needs at least 24 months
#   of history to create lag features. While it can work with less, the
#   forecast quality may be poor.
#
# COST
#   A run trains an XGBoost model and generates a recursive forecast.
#   Speed depends on data size and horizon but is generally faster than SARIMA.
#   Results are cached per input frame, but the FIRST call may take a few seconds.
# =============================================================================

_XGBOOST_FORECAST_CACHE: dict = {}
_XGBOOST_CACHE_LIMIT = 8


def get_xgboost_forecast(
    sales_df=None,
    *,
    horizon=12,
    fast=True,
    value_col=None,
    month_col=None,
    series_name="revenue_total",
    use_cache=True,
    debug=False,
):
    """Forecast the next `horizon` months using XGBoost and report how much to trust it.

    Args:
        sales_df:    monthly DataFrame (see the header above). Defaults to
                     get_sales_data() so the signature matches the other
                     functions in this module.
        horizon:     months to forecast. 12 = one fiscal year.
        fast:        use fewer estimators for faster training (less accurate).
        value_col:   force the column to forecast. Auto-detected otherwise.
        month_col:   force the month column. Auto-detected otherwise.
        use_cache:   reuse a previous result for an identical frame.
        debug:       print the engine's notes as they are raised.

    Returns a JSON-serialisable dict. Always has "status"; the caller should
    branch on it rather than assume a forecast came back:

        status  "ok"                    -> "forecast" and "diagnostics" are populated
                "insufficient_history"  -> "detail" says what is missing
                "error"                 -> "message" carries the exception

        forecast        spec, months, point, lower_90, upper_90, annual_total,
                        annual_yoy_pct, plausibility_ok
        diagnostics     holdout_mae, holdout_rmse, holdout_mape, model_params,
                        training_samples, holdout_samples, feature_count
        fiscal_years    which fiscal years were used, and the one forecast
        data_anomalies  []
        warnings        [{kind, message}] raised during the run
    """
    if sales_df is None:
        sales_df = get_sales_data()

    key = None
    if use_cache:
        try:
            key = _frame_fingerprint(sales_df, horizon, fast, value_col, month_col)
            if key in _XGBOOST_FORECAST_CACHE:
                cached = dict(_XGBOOST_FORECAST_CACHE[key])
                cached["cached"] = True
                return cached
        except Exception:
            key = None                      # an unhashable frame just skips the cache

    # Import here to avoid circular imports
    from app.services import xgboost_engine

    result = xgboost_engine.run_forecast(
        sales_df,
        month_col=month_col,
        value_col=value_col,
        horizon=horizon,
        fast=fast,
        series_name=series_name,
        debug=debug,
    )
    result["cached"] = False

    if key is not None and result.get("status") == "ok":
        if len(_XGBOOST_FORECAST_CACHE) >= _XGBOOST_CACHE_LIMIT:
            _XGBOOST_FORECAST_CACHE.pop(next(iter(_XGBOOST_FORECAST_CACHE)))
        _XGBOOST_FORECAST_CACHE[key] = result

    return result


def get_xgboost_forecast_for(
    dimension="total",
    dimension_value=None,
    value_col="revenue",
    horizon=12,
    fast=True,
    use_cache=True,
    debug=False,
):
    """Slice a series by dimension/dimension_value, then forecast it using XGBoost.

    dimension="total" + value_col="revenue" reproduces the original
    whole-company forecast (series_name="revenue_total") the dashboard
    KPIs already depend on — this function is a strict superset, not a
    replacement, of calling get_xgboost_forecast() directly.

    Raises ValueError before ever touching XGBoost if dimension_value is
    missing/unmatched — the caller (routes.py) turns that into a clean
    "error" status rather than a raw 500.
    """
    monthly = _slice_series(dimension, dimension_value)

    series_name = (
        f"{value_col}_total" if dimension == "total"
        else f"{dimension}:{dimension_value}:{value_col}"
    )

    return get_xgboost_forecast(
        monthly,
        horizon=horizon,
        fast=fast,
        value_col=value_col,
        series_name=series_name,
        use_cache=use_cache,
        debug=debug,
    )


# =============================================================================
# RANDOM FOREST FORECAST
# =============================================================================
# Wraps the RandomForest engine (app/services/randomforest_engine.py) behind one function.
#
# WHAT IT EXPECTS
#   A monthly DataFrame in this project's own shape - the same frame
#   get_sales_data() returns:
#
#     month          "2025-01" / a date / anything pd.to_datetime parses  (required)
#     revenue        numeric                                              (preferred)
#     actual_units   numeric - used only if there is no revenue column
#
#   Extra columns (product, customer, forecast_units) are ignored. Rows are
#   summed per calendar month, so transaction-level rows work too.
#
#   HISTORY IS THE BINDING CONSTRAINT. The model needs at least 24 months
#   of history to create lag features. While it can work with less, the
#   forecast quality may be poor.
#
# COST
#   A run trains a RandomForest model and generates a recursive forecast.
#   Speed depends on data size and horizon but is generally faster than SARIMA.
#   Results are cached per input frame, but the FIRST call may take a few seconds.
# =============================================================================

_RANDOMFOREST_FORECAST_CACHE: dict = {}
_RANDOMFOREST_CACHE_LIMIT = 8


def get_randomforest_forecast(
    sales_df=None,
    *,
    horizon=12,
    fast=True,
    value_col=None,
    month_col=None,
    series_name="revenue_total",
    use_cache=True,
    debug=False,
):
    """Forecast the next `horizon` months using RandomForest and report how much to trust it.

    Args:
        sales_df:    monthly DataFrame (see the header above). Defaults to
                     get_sales_data() so the signature matches the other
                     functions in this module.
        horizon:     months to forecast. 12 = one fiscal year.
        fast:        use fewer estimators for faster training (less accurate).
        value_col:   force the column to forecast. Auto-detected otherwise.
        month_col:   force the month column. Auto-detected otherwise.
        use_cache:   reuse a previous result for an identical frame.
        debug:       print the engine's notes as they are raised.

    Returns a JSON-serialisable dict. Always has "status"; the caller should
    branch on it rather than assume a forecast came back:

        status  "ok"                    -> "forecast" and "diagnostics" are populated
                "insufficient_history"  -> "detail" says what is missing
                "error"                 -> "message" carries the exception

        forecast        spec, months, point, lower_90, upper_90, annual_total,
                        annual_yoy_pct, plausibility_ok
        diagnostics     holdout_mae, holdout_rmse, holdout_mape, model_params,
                        training_samples, holdout_samples, feature_count
        fiscal_years    which fiscal years were used, and the one forecast
        data_anomalies  []
        warnings        [{kind, message}] raised during the run
    """
    if sales_df is None:
        sales_df = get_sales_data()

    key = None
    if use_cache:
        try:
            key = _frame_fingerprint(sales_df, horizon, fast, value_col, month_col)
            if key in _RANDOMFOREST_FORECAST_CACHE:
                cached = dict(_RANDOMFOREST_FORECAST_CACHE[key])
                cached["cached"] = True
                return cached
        except Exception:
            key = None                      # an unhashable frame just skips the cache

    # Import here to avoid circular imports
    from app.services import randomforest_engine
    from app.services import lstm_engine

    result = randomforest_engine.run_forecast(
        sales_df,
        horizon=horizon,
        fast=fast,
        value_col=value_col,
        month_col=month_col,
        series_name=series_name,
        debug=debug,
    )
    result["cached"] = False

    if key is not None and result.get("status") == "ok":
        if len(_RANDOMFOREST_FORECAST_CACHE) >= _RANDOMFOREST_CACHE_LIMIT:
            _RANDOMFOREST_FORECAST_CACHE.pop(next(iter(_RANDOMFOREST_FORECAST_CACHE)))
        _RANDOMFOREST_FORECAST_CACHE[key] = result

    return result


def get_randomforest_forecast_for(
    dimension="total",
    dimension_value=None,
    value_col="revenue",
    horizon=12,
    fast=True,
    use_cache=True,
    debug=False,
):
    """Slice a series by dimension/dimension_value, then forecast it using RandomForest.

    dimension="total" + value_col="revenue" reproduces the original
    whole-company forecast (series_name="revenue_total") the dashboard
    KPIs already depend on — this function is a strict superset, not a
    replacement, of calling get_randomforest_forecast() directly.

    Raises ValueError before ever touching RandomForest if dimension_value is
    missing/unmatched — the caller (routes.py) turns that into a clean
    "error" status rather than a raw 500.
    """
    monthly = _slice_series(dimension, dimension_value)

    series_name = (
        f"{value_col}_total" if dimension == "total"
        else f"{dimension}:{dimension_value}:{value_col}"
    )

    return get_randomforest_forecast(
        monthly,
        horizon=horizon,
        fast=fast,
        value_col=value_col,
        series_name=series_name,
        use_cache=use_cache,
        debug=debug,
    )


# =============================================================================
# LSTM FORECAST
# =============================================================================
# Wraps the LSTM engine (app/services/lstm_engine.py) behind one function.
#
# WHAT IT EXPECTS
#   A monthly DataFrame in this project's own shape - the same frame
#   get_sales_data() returns:
#
#     month          "2025-01" / a date / anything pd.to_datetime parses  (required)
#     revenue        numeric                                              (preferred)
#     actual_units   numeric - used only if there is no revenue column
#
#   Extra columns (product, customer, forecast_units) are ignored. Rows are
#   summed per calendar month, so transaction-level rows work too.
#
#   HISTORY IS THE BINDING CONSTRAINT. The model needs at least 24 months
#   of history to create lag features. While it can work with less, the
#   forecast quality may be poor.
#
# COST
#   A run trains an LSTM model and generates a recursive forecast.
#   Speed depends on data size and horizon but is generally faster than SARIMA.
#   Results are cached per input frame, but the FIRST call may take a few seconds.
# =============================================================================

_LSTM_FORECAST_CACHE: dict = {}
_LSTM_CACHE_LIMIT = 8


def get_lstm_forecast(
    sales_df=None,
    *,
    horizon=12,
    fast=True,
    value_col=None,
    month_col=None,
    series_name="revenue_total",
    use_cache=True,
    debug=False,
):
    """Forecast the next `horizon` months using LSTM and report how much to trust it.

    Args:
        sales_df:    monthly DataFrame (see the header above). Defaults to
                     get_sales_data() so the signature matches the other
                     functions in this module.
        horizon:     months to forecast. 12 = one fiscal year.
        fast:        use fewer epochs for faster training (less accurate).
        value_col:   force the column to forecast. Auto-detected otherwise.
        month_col:   force the month column. Auto-detected otherwise.
        use_cache:   reuse a previous result for an identical frame.
        debug:       print the engine's notes as they are raised.

    Returns a JSON-serialisable dict. Always has "status"; the caller should
    branch on it rather than assume a forecast came back:

        status  "ok"                    -> "forecast" and "diagnostics" are populated
                "insufficient_history"  -> "detail" says what is missing
                "error"                 -> "message" carries the exception

        forecast        spec, months, point, lower_90, upper_90, annual_total,
                        annual_yoy_pct, plausibility_ok
        diagnostics     holdout_mae, holdout_rmse, holdout_mape, model_params,
                        training_samples, holdout_samples, feature_count
        fiscal_years    which fiscal years were used, and the one forecast
        data_anomalies  []
        warnings        [{kind, message}] raised during the run
    """
    if sales_df is None:
        sales_df = get_sales_data()

    key = None
    if use_cache:
        try:
            key = _frame_fingerprint(sales_df, horizon, fast, value_col, month_col)
            if key in _LSTM_FORECAST_CACHE:
                cached = dict(_LSTM_FORECAST_CACHE[key])
                cached["cached"] = True
                return cached
        except Exception:
            key = None                      # an unhashable frame just skips the cache

    # Import here to avoid circular imports
    from app.services import lstm_engine

    result = lstm_engine.run_forecast(
        sales_df,
        horizon=horizon,
        fast=fast,
        value_col=value_col,
        month_col=month_col,
        series_name=series_name,
        debug=debug,
    )
    result["cached"] = False

    if key is not None and result.get("status") == "ok":
        if len(_LSTM_FORECAST_CACHE) >= _LSTM_CACHE_LIMIT:
            _LSTM_FORECAST_CACHE.pop(next(iter(_LSTM_FORECAST_CACHE)))
        _LSTM_FORECAST_CACHE[key] = result

    return result


def get_lstm_forecast_for(
    dimension="total",
    dimension_value=None,
    value_col="revenue",
    horizon=12,
    fast=True,
    use_cache=True,
    debug=False,
):
    """Slice a series by dimension/dimension_value, then forecast it using LSTM.

    dimension="total" + value_col="revenue" reproduces the original
    whole-company forecast (series_name="revenue_total") the dashboard
    KPIs already depend on — this function is a strict superset, not a
    replacement, of calling get_lstm_forecast() directly.

    Raises ValueError before ever touching LSTM if dimension_value is
    missing/unmatched — the caller (routes.py) turns that into a clean
    "error" status rather than a raw 500.
    """
    monthly = _slice_series(dimension, dimension_value)

    series_name = (
        f"{value_col}_total" if dimension == "total"
        else f"{dimension}:{dimension_value}:{value_col}"
    )

    return get_lstm_forecast(
        monthly,
        horizon=horizon,
        fast=fast,
        value_col=value_col,
        series_name=series_name,
        use_cache=use_cache,
        debug=debug,
    )
