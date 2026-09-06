"""
Real sales data, pulled from MySQL (missubibi.Sales_Order_Merged).

Returns the exact same shape as app/data/mock_data.py's get_sales_data(),
so analytics.py needed a one-line import change and nothing else:

    month, product, customer, actual_units, revenue, forecast_units

------------------------------------------------------------------------
ON DEDUPLICATION (applied below, not optional — read before trusting totals)
------------------------------------------------------------------------
The `is_duplicate_row` column in Sales_Order_Merged is 0 for all 272,000
rows in the current dump — it isn't populated, so it can't be used to
filter. But manual inspection during setup found real duplicate line
items: some (so_internal_id, item_code) combinations repeat 10-14 times
with identical quantity/price/period. Left in, several SKUs' totals would
be inflated by that same multiple.

This query dedupes using a composite key (so_internal_id, item_code,
quantity, base_price, calendar_year, month_name) via ROW_NUMBER(), keeping
one row per group. This is a judgment call based on what we found during
setup, not a confirmed-correct rule — it assumes an order never
legitimately contains the exact same SKU/quantity/price as two separate
line items (reasonable, but not verified against how the source system
actually generates orders). CONFIRM WITH THE TEAM before relying on these
totals for anything graded/reported.

------------------------------------------------------------------------
ON forecast_units (PLACEHOLDER — not a real model)
------------------------------------------------------------------------
forecast_units does not exist in the raw data — it's SARIMA's *output*,
not a stored fact. The real engine (see analytics.get_sarima_forecast)
forecasts ONE aggregate revenue series at a time, needs 36+ months of
history, and takes 40-90 seconds per run. It isn't designed to produce a
number for every (month, product) row the way the mock data faked it.

Until real forecasts are wired in as a separate, cached/background step,
this uses a naive lag-1 placeholder: each product+customer's "forecast"
for a given month is just its own actual_units from the previous month
(first month per product+customer falls back to its own actual, i.e. 0%
error). This is deterministic — the same on every reload — but it is NOT
a model. Any forecast_accuracy / forecast_risk figure downstream is only
as meaningful as this placeholder, which is to say: not very. Replace
this column with real get_sarima_forecast() output before anything
user-facing treats it as a real forecast.

------------------------------------------------------------------------
NOTE (fixed 2026-09-06): `year_month` is a MySQL reserved word (the
compound INTERVAL unit specifier, same family as DAY_HOUR/HOUR_MINUTE),
so it must be backtick-quoted wherever it's used as a bare identifier in
raw SQL — used unquoted, it throws a 1064 syntax error at parse time,
before MySQL even checks whether the table/columns exist. Both
references below are now quoted.

NOTE (fixed 2026-09-06): every year_month value also comes out of MySQL
with a trailing \r (Windows-style line endings baked into the source
data). Left in, the frontend's `new Date(\`${item.month}-01\`)` produces
an invalid date and breaks the month-axis labels on the revenue chart.
Stripped in get_sales_data() below, right after pd.read_sql.
------------------------------------------------------------------------
"""

import pandas as pd

from app.database import engine

_QUERY = """
    WITH deduped AS (
        SELECT
            `year_month`,
            product_category_2,
            company_name,
            quantity,
            total_revenue_thb,
            ROW_NUMBER() OVER (
                PARTITION BY
                    so_internal_id, item_code, quantity,
                    base_price, calendar_year, month_name
                ORDER BY so_internal_id
            ) AS rn
        FROM Sales_Order_Merged
    )
    SELECT
        `year_month`        AS month,
        product_category_2  AS product,
        company_name        AS customer,
        quantity            AS actual_units,
        total_revenue_thb   AS revenue
    FROM deduped
    WHERE rn = 1
"""


def get_sales_data() -> pd.DataFrame:
    df = pd.read_sql(_QUERY, engine)

    # year_month comes out of MySQL with a trailing \r on every row
    # (Windows-style line endings baked into the source data). Left
    # in, `${month}-01` on the frontend produces an invalid date
    # string and breaks the chart's month-axis labels. Strip it here
    # rather than relying on every consumer to know to do it.
    df["month"] = df["month"].str.strip()

    # Raw rows are transaction-level; collapse to one row per
    # (month, product, customer), same granularity mock_data.py used.
    df = (
        df.groupby(["month", "product", "customer"], as_index=False)
        .agg(actual_units=("actual_units", "sum"), revenue=("revenue", "sum"))
    )

    # --- forecast_units placeholder (see module docstring) ---
    # Grouped by (product, customer) together, not product alone —
    # otherwise the lag-1 shift can pull the "previous" value from a
    # different customer in the same month instead of this customer's
    # own prior month.
    df = df.sort_values(["product", "customer", "month"])
    df["forecast_units"] = df.groupby(["product", "customer"])["actual_units"].shift(1)
    df["forecast_units"] = df["forecast_units"].fillna(df["actual_units"])
    df["forecast_units"] = df["forecast_units"].round().astype(int)

    return df.reset_index(drop=True)
