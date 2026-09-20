"""Only SQL-schema boundary. Monthly source data is never presented as daily actuals."""
import threading
import time

import pandas as pd
from sqlalchemy import inspect
from app.database import engine

DIMENSIONS = ('total', 'item', 'product', 'customer', 'industry', 'vendor')
GRANULARITIES = ('daily', 'weekly', 'monthly', 'quarterly', 'yearly')
VALUE_COLUMNS = ('revenue', 'actual_units')
_lock = threading.RLock()
_cache = {'data': None, 'time': 0}


def resample_monthly(frame, granularity, columns=('value',)):
    """Allocate monthly totals to calendar days before summing Monday-based weeks.

    This conserves totals, including leap days and partial boundary weeks.
    Returned period labels are ISO start dates, never ambiguous week numbers.
    """
    if granularity not in GRANULARITIES:
        raise ValueError('Unsupported granularity')
    df = frame.copy()
    df['month'] = pd.to_datetime(df['month'])
    df = df.set_index('month')[list(columns)].sort_index()
    if df.empty:
        return pd.DataFrame(columns=['month', *columns])
    if granularity in ('daily', 'weekly'):
        end = df.index.max() + pd.offsets.MonthEnd(0)
        idx = pd.date_range(df.index.min(), end, freq='D')
        daily = df.reindex(idx.to_period('M').to_timestamp())
        daily.index = idx
        df = daily.div(idx.days_in_month, axis=0)
        if granularity == 'weekly':
            df = df.resample('W-MON', label='left', closed='left').sum()
    elif granularity != 'monthly':
        df = df.resample({'quarterly': 'QS', 'yearly': 'YS'}[granularity]).sum()
    df.index.name = 'month'
    df = df.reset_index()
    df['month'] = df['month'].dt.strftime('%Y-%m-%d')
    return df


class DataAdapter:
    def _get_base_data(self):
        # Serialize cache fills: simultaneous page requests must not flood MySQL.
        with _lock:
            if _cache['data'] is not None and time.monotonic() - _cache['time'] < 60:
                return _cache['data'].copy()
            cols = {c['name'] for c in inspect(engine).get_columns('Sales_Order_Merged')}
            vendor = '`vendor_name`' if 'vendor_name' in cols else 'NULL'
            query = f"""
                WITH deduped AS (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY so_internal_id, item_code, quantity,
                                     base_price, calendar_year, month_name
                        ORDER BY so_internal_id
                    ) AS rn FROM Sales_Order_Merged
                )
                SELECT `year_month` AS month, item_code AS item,
                    product_category_2 AS product, company_name AS customer,
                    fa_sub_industries AS industry, {vendor} AS vendor,
                    quantity AS actual_units, total_revenue_thb AS revenue,
                    base_price, list_price, product_category_1, production_status,
                    customer_type, so_internal_id AS order_id, sales_order_status
                FROM deduped WHERE rn = 1
            """
            df = pd.read_sql(query, engine)
            for col in ('month', *DIMENSIONS[1:]):
                df[col] = df[col].astype('string').str.strip().replace('', pd.NA)
            dates = pd.to_datetime(df['month'], format='%Y-%m', errors='coerce')
            df = df.loc[dates.notna()].copy()
            df['month'] = dates.loc[dates.notna()].dt.strftime('%Y-%m-%d')
            for col in VALUE_COLUMNS:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(float)
            from app.services.csv_import import load_overlay
            include_base, imported, vendors = load_overlay()
            if not include_base:
                df = df.iloc[:0]
            if not imported.empty:
                df = pd.concat([df, imported], ignore_index=True)
            for col in DIMENSIONS[1:]:
                df[col] = df[col].astype('string').str.strip().replace('', pd.NA)
            df['vendor'] = df['vendor'].fillna(df['item'].map(vendors))
            _cache.update(data=df, time=time.monotonic())
            return df.copy()

    def get_series(self, dimension='total', dimension_value=None, value_col='revenue',
                   granularity='monthly', filters=None):
        if dimension not in DIMENSIONS or value_col not in VALUE_COLUMNS:
            raise ValueError('Unsupported dimension or metric')
        df = self._get_base_data()
        first, last = df['month'].min(), df['month'].max()
        selected = dict(filters or {})
        if dimension != 'total':
            if not dimension_value:
                raise ValueError('Select a dimension value')
            selected[dimension] = dimension_value
        for key, value in selected.items():
            if key not in DIMENSIONS[1:]:
                raise ValueError('Unsupported filter')
            if value:
                df = df[df[key] == value]
        if df.empty:
            return pd.DataFrame(columns=['month', 'value'])
        values = df.groupby('month')[value_col].sum()
        # Continue through the dataset end: a quiet SKU must not end at its last sale.
        start = df['month'].min() if selected else first
        idx = pd.date_range(start, last, freq='MS').strftime('%Y-%m-%d')
        values = values.reindex(idx, fill_value=0)
        result = values.rename_axis('month').reset_index(name='value')
        return resample_monthly(result, granularity)

    def get_dimension_values(self, dimension):
        if dimension not in DIMENSIONS[1:]:
            raise ValueError('Unsupported dimension')
        return sorted(self._get_base_data()[dimension].dropna().unique().tolist())

    def options(self):
        df = self._get_base_data()
        return {d: sorted(df[d].dropna().unique().tolist()) for d in DIMENSIONS[1:]}

    def get_industries(self):
        return self.get_dimension_values('industry')

    def get_vendors(self):
        return self.get_dimension_values('vendor')

    def invalidate(self):
        with _lock:
            _cache.update(data=None, time=0)


adapter = DataAdapter()
