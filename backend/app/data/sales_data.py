"""Legacy analytics compatibility; SQL lives exclusively in adapter.py.

forecast_units is explicitly a naive prior-observed-period baseline, not ML.
The deduplication key remains an assumption pending source-system confirmation.
"""
from app.data.adapter import adapter


def get_sales_data():
    df = adapter._get_base_data()
    df = df.groupby(['month', 'product', 'customer'], dropna=False, as_index=False).agg(
        actual_units=('actual_units', 'sum'), revenue=('revenue', 'sum'))
    df = df.sort_values(['product', 'customer', 'month'])
    df['forecast_units'] = df.groupby(['product', 'customer'], dropna=False)['actual_units'].shift(1).fillna(0)
    df['month'] = df['month'].str[:7]
    return df.reset_index(drop=True)
