"""Deterministic monthly OLS baseline with seasonal harmonics.

Validation is chronological; errors and MASE use original units, not log residuals.
"""
import numpy as np
import pandas as pd


def _design(t, seasonal):
    cols = [np.ones(len(t)), t / 12]
    if seasonal:
        cols += [np.sin(2*np.pi*t/12), np.cos(2*np.pi*t/12)]
    return np.column_stack(cols)


def _fit(y, horizon):
    seasonal = len(y) >= 24
    x = _design(np.arange(len(y)), seasonal)
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    future = _design(np.arange(len(y), len(y)+horizon), seasonal)
    point = np.maximum(0, future @ beta)
    residual = y - x @ beta
    variance = float(np.sum(residual**2) / max(1, len(y)-x.shape[1]))
    leverage = np.einsum('ij,jk,ik->i', future, np.linalg.pinv(x.T@x), future)
    radius = 1.645 * np.sqrt(variance * (1 + leverage))
    return point, np.maximum(0, point-radius), point+radius


def run_forecast(sales_df, *, month_col='month', value_col='value', horizon=12,
                 fast=True, series_name='revenue_total', debug=False):
    df = sales_df.copy()
    df[month_col] = pd.to_datetime(df[month_col])
    s = df.groupby(month_col)[value_col].sum().sort_index()
    y = s.to_numpy(dtype=float)
    if len(y) < 6:
        return {'status': 'insufficient_history', 'message': 'Trend needs at least 6 months.'}
    point, lo, hi = _fit(y, horizon)
    holdout = min(12, max(1, len(y)//5))
    train = y[:-holdout]
    pred = _fit(train, holdout)[0]
    mae = float(np.abs(y[-holdout:]-pred).mean())
    lag = 12 if len(train)>12 else 1
    scale = float(np.abs(train[lag:]-train[:-lag]).mean())
    dates = pd.date_range(s.index[-1]+pd.offsets.MonthBegin(), periods=horizon, freq='MS')
    return {'status': 'ok', 'forecast': {
        'series': series_name, 'spec': 'OLS trend + seasonal harmonics', 'horizon': horizon,
        'months': dates.strftime('%Y-%m-%d').tolist(), 'point': point.tolist(),
        'lower_90': lo.tolist(), 'upper_90': hi.tolist(),
        'annual_total': float(point.sum()), 'annual_yoy_pct': None,
        'interval_source': 'Approximate OLS 90% prediction interval',
    }, 'diagnostics': {'holdout_mae': mae, 'holdout_samples': holdout,
        'mase': mae/scale if scale > 0 else None}, 'warnings': []}
