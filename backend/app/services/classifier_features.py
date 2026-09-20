"""September TR rev8 lag/recency feature block, extracted from the supplied source.

No CSV loading, training, plotting, or notebook execution occurs at import.
"""
import numpy as np
import pandas as pd

NUMERIC_FEATURES = [
    "prev_month_qty_1", "prev_month_qty_2", "prev_month_qty_3", "prev_month_qty_6",
    "prev_month_orders_1", "prev_month_orders_2", "prev_month_orders_3", "prev_month_orders_6",
    "prev_qty_roll_mean_3", "prev_qty_roll_std_3", "prev_qty_roll_mean_6", "prev_qty_roll_std_6",
    "prev_qty_pct_change", "prev_qty_ema_3", "prev_qty_ema_6",
    "prev_qty_cv_3", "prev_qty_cv_6", "prev_price_elasticity", "prev_orders_per_customer",
    "rel_qty_vs_own_history_1", "rel_qty_vs_own_history_3",
    "prev_distinct_customers_1", "prev_avg_base_price_1",
    "months_since_first_sale", "list_price",
    "calendar_month_sin", "calendar_month_cos",
    # --- Rev 8: recency / intermittency / seasonality, all strictly past-only ---
    "months_since_last_sale", "never_sold_before", "sold_count_expanding", "sold_streak",
    "sold_rate_3", "sold_rate_6", "sold_rate_12", "sold_rate_24", "sold_rate_expanding",
    "gap_mean_hist", "gap_max_hist", "gap_vs_hist",
    "prev_month_qty_9", "prev_month_qty_12", "prev_month_qty_24",
    "prev_sold_9", "prev_sold_12", "prev_sold_24",
    "prev_qty_roll_mean_12", "prev_qty_roll_max_6",
    "prev_qty_roll_sum_3", "prev_qty_roll_sum_6",
    "prev_orders_roll_sum_3", "prev_orders_roll_sum_6",
    "prev_orders_roll_mean_3", "prev_cust_roll_mean_3",
    "prev_qty_1_is_zero", "prev_qty_12_is_zero",
    "qty_trend_3_6", "sold_trend_3_12", "seasonal_sold_rate",
    "mkt_sold_rate", "mkt_qty", "cat_sold_rate", "month_index", "days_in_month",
]

CATEGORICAL_FEATURES = [
    "item_internal_id", "product_category_1", "product_category_2",
    "production_status", "prev_dominant_customer_type_1",
    "prev_dominant_industry_1", "calendar_month", "calendar_quarter",
]

def tr_features(monthly):
    monthly = monthly.sort_values(["item_internal_id", "year_month"]).reset_index(drop=True)
    g = monthly.groupby("item_internal_id")

    LAGS = [1, 2, 3, 6]
    for lag in LAGS:
        monthly[f"prev_month_qty_{lag}"] = g["quantity"].shift(lag)
        monthly[f"prev_month_orders_{lag}"] = g["n_orders"].shift(lag)

    shifted_qty = g["quantity"].shift(1)
    monthly["prev_qty_roll_mean_3"] = shifted_qty.groupby(monthly["item_internal_id"]).rolling(3, min_periods=1).mean().reset_index(level=0, drop=True)
    monthly["prev_qty_roll_std_3"]  = shifted_qty.groupby(monthly["item_internal_id"]).rolling(3, min_periods=1).std().reset_index(level=0, drop=True)
    monthly["prev_qty_roll_mean_6"] = shifted_qty.groupby(monthly["item_internal_id"]).rolling(6, min_periods=1).mean().reset_index(level=0, drop=True)
    monthly["prev_qty_roll_std_6"]  = shifted_qty.groupby(monthly["item_internal_id"]).rolling(6, min_periods=1).std().reset_index(level=0, drop=True)
    monthly["prev_qty_pct_change"]  = shifted_qty.groupby(monthly["item_internal_id"]).pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)

    monthly["prev_qty_ema_3"] = shifted_qty.groupby(monthly["item_internal_id"]).transform(
        lambda s: s.ewm(span=3, adjust=False, min_periods=1).mean()
    )
    monthly["prev_qty_ema_6"] = shifted_qty.groupby(monthly["item_internal_id"]).transform(
        lambda s: s.ewm(span=6, adjust=False, min_periods=1).mean()
    )

    monthly["prev_qty_cv_3"] = (monthly["prev_qty_roll_std_3"] / monthly["prev_qty_roll_mean_3"]).replace([np.inf, -np.inf], np.nan)
    monthly["prev_qty_cv_6"] = (monthly["prev_qty_roll_std_6"] / monthly["prev_qty_roll_mean_6"]).replace([np.inf, -np.inf], np.nan)

    monthly["prev_distinct_customers_1"] = g["distinct_customers"].shift(1)
    monthly["prev_avg_base_price_1"]     = g["avg_base_price"].shift(1)
    monthly["prev_dominant_customer_type_1"] = g["dominant_customer_type"].shift(1)
    monthly["prev_dominant_industry_1"]      = g["dominant_industry"].shift(1)

    # Rev 7: fill_method=None is pinned explicitly on both pct_change() calls below and
    # above. pandas 2.x deprecated the implicit fill_method="ffill" default (FutureWarning),
    # and forward-filling a gap before differencing would have manufactured a 0% change out
    # of a genuinely unknown month. None = leave the NaN, which the .fillna(0) below handles.
    shifted_price = g["avg_base_price"].shift(1)
    price_pct_change = shifted_price.groupby(monthly["item_internal_id"]).pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    monthly["prev_price_elasticity"] = (monthly["prev_qty_pct_change"] / price_pct_change).replace([np.inf, -np.inf], np.nan)

    monthly["prev_orders_per_customer"] = (
        monthly["prev_month_orders_1"] / monthly["prev_distinct_customers_1"]
    ).replace([np.inf, -np.inf], np.nan)

    monthly["months_since_first_sale"] = g.cumcount()

    # --- Rev 4: per-item relative demand ratios ------------------------------------
    # expanding().mean() over the *shifted* series only ever looks at months strictly
    # before the current row, for that item alone -> no leakage, and no test-set
    # statistics are used since this is computed on the full panel before the
    # train/test split purely from each item's own past.
    monthly["prev_qty_expanding_mean"] = shifted_qty.groupby(monthly["item_internal_id"]).transform(
        lambda s: s.expanding(min_periods=1).mean()
    )
    monthly["rel_qty_vs_own_history_1"] = (
        monthly["prev_month_qty_1"] / monthly["prev_qty_expanding_mean"]
    ).replace([np.inf, -np.inf], np.nan)
    monthly["rel_qty_vs_own_history_3"] = (
        monthly["prev_qty_roll_mean_3"] / monthly["prev_qty_expanding_mean"]
    ).replace([np.inf, -np.inf], np.nan)

    # --- Rev 4: cyclical calendar-month encoding -----------------------------------
    monthly["month_ts"] = monthly["year_month"].dt.to_timestamp()
    monthly["calendar_month"] = monthly["month_ts"].dt.month.astype(str)
    monthly["calendar_quarter"] = monthly["month_ts"].dt.quarter.astype(str)
    _month_num = monthly["month_ts"].dt.month.astype(float)
    monthly["calendar_month_sin"] = np.sin(2 * np.pi * _month_num / 12.0)
    monthly["calendar_month_cos"] = np.cos(2 * np.pi * _month_num / 12.0)


    # ================================================================================
    # Rev 8 additions — leak-free recency / intermittency signal
    # ================================================================================
    # The target is "did this item sell at all this month", so how *recently* and how
    # *often* an item has been selling is the dominant signal, and Rev 7 never encoded it
    # directly. Every feature below is a function of `sold_flag` shifted by >= 1 month
    # inside the item, i.e. of information available strictly before month t.
    #
    # Rejected during Rev 8 feature search, recorded here so it is not re-added by mistake:
    # a "life_progress" feature (months_since_first_sale / the item's total row count).
    # It scored +6 accuracy points and was pure leakage -- the denominator encodes when the
    # item stops selling, which is future information.
    monthly["sold_flag"] = (monthly["quantity"] > 0).astype(float)
    _sold_prev = g["sold_flag"].shift(1)
    _sold_prev_g = _sold_prev.groupby(monthly["item_internal_id"])
    _iid = monthly["item_internal_id"]

    # --- recency: months since the item last sold, as known at t-1 -------------------
    # Rows inside one dry spell share the same cumulative sale count, so a cumcount within
    # (item, cumulative-count) gives the length of the current gap without any lookahead.
    _sold_csum = _sold_prev.fillna(0).groupby(_iid).cumsum()
    monthly["months_since_last_sale"] = _sold_csum.groupby([_iid, _sold_csum]).cumcount().astype(float)
    monthly.loc[_sold_prev.isna(), "months_since_last_sale"] = np.nan
    monthly["never_sold_before"] = (_sold_csum == 0).astype(float)
    monthly["sold_count_expanding"] = _sold_csum

    # --- how often it sells: past-only hit rates -------------------------------------
    for _w in [3, 6, 12, 24]:
        monthly[f"sold_rate_{_w}"] = (
            _sold_prev_g.rolling(_w, min_periods=1).mean().reset_index(level=0, drop=True)
        )
    monthly["sold_rate_expanding"] = _sold_prev_g.transform(lambda s: s.expanding(min_periods=1).mean())

    # --- consecutive sold months ending at t-1 ---------------------------------------
    _zero = (_sold_prev == 0).astype(float)
    _zero_csum = _zero.fillna(0).groupby(_iid).cumsum()
    monthly["sold_streak"] = _zero_csum.groupby([_iid, _zero_csum]).cumcount().astype(float)

    # --- dry-spell history: how bursty has this item been, using past gaps only -------
    _msls = monthly["months_since_last_sale"]
    monthly["gap_mean_hist"] = _msls.groupby(_iid).transform(lambda s: s.shift(1).expanding(min_periods=1).mean())
    monthly["gap_max_hist"]  = _msls.groupby(_iid).transform(lambda s: s.shift(1).expanding(min_periods=1).max())
    monthly["gap_vs_hist"]   = (_msls / monthly["gap_mean_hist"]).replace([np.inf, -np.inf], np.nan)

    # --- longer / seasonal lags -------------------------------------------------------
    for _lag in [9, 12, 24]:
        monthly[f"prev_month_qty_{_lag}"] = g["quantity"].shift(_lag)
        monthly[f"prev_sold_{_lag}"] = g["sold_flag"].shift(_lag)

    _shifted_qty_g = g["quantity"].shift(1).groupby(_iid)
    monthly["prev_qty_roll_mean_12"] = _shifted_qty_g.rolling(12, min_periods=1).mean().reset_index(level=0, drop=True)
    monthly["prev_qty_roll_max_6"]   = _shifted_qty_g.rolling(6, min_periods=1).max().reset_index(level=0, drop=True)
    for _w in [3, 6]:
        monthly[f"prev_qty_roll_sum_{_w}"] = _shifted_qty_g.rolling(_w, min_periods=1).sum().reset_index(level=0, drop=True)
        monthly[f"prev_orders_roll_sum_{_w}"] = (
            g["n_orders"].shift(1).groupby(_iid).rolling(_w, min_periods=1).sum().reset_index(level=0, drop=True)
        )
    monthly["prev_orders_roll_mean_3"] = g["n_orders"].shift(1).groupby(_iid).rolling(3, min_periods=1).mean().reset_index(level=0, drop=True)
    monthly["prev_cust_roll_mean_3"]   = g["distinct_customers"].shift(1).groupby(_iid).rolling(3, min_periods=1).mean().reset_index(level=0, drop=True)
    monthly["prev_qty_1_is_zero"]  = (monthly["prev_month_qty_1"] == 0).astype(float)
    monthly["prev_qty_12_is_zero"] = (monthly["prev_month_qty_12"] == 0).astype(float)

    # --- trend / acceleration on past-only windows ------------------------------------
    monthly["qty_trend_3_6"]   = monthly["prev_qty_roll_mean_3"] - monthly["prev_qty_roll_mean_6"]
    monthly["sold_trend_3_12"] = monthly["sold_rate_3"] - monthly["sold_rate_12"]

    # --- seasonality: this item's hit rate in THIS calendar month, past years only -----
    monthly["seasonal_sold_rate"] = (
        monthly.groupby([_iid, monthly["month_ts"].dt.month])["sold_flag"]
               .transform(lambda s: s.shift(1).expanding(min_periods=1).mean())
    )

    # --- market / category context, taken from month t-1 only -------------------------
    # Cross-sectional aggregates are shifted a month forward before being joined back, so a
    # row only ever sees the previous month's market state, never its own month's.
    _mkt = (monthly.groupby("year_month")
                    .agg(mkt_sold_rate=("sold_flag", "mean"), mkt_qty=("quantity", "sum"))
                    .reset_index())
    _mkt["year_month"] = _mkt["year_month"] + 1
    monthly = monthly.merge(_mkt, on="year_month", how="left")

    _cat1 = (monthly.groupby(["product_category_1", "year_month"])
                     .agg(cat_sold_rate=("sold_flag", "mean")).reset_index())
    _cat1["year_month"] = _cat1["year_month"] + 1
    monthly = monthly.merge(_cat1, on=["product_category_1", "year_month"], how="left")

    monthly["month_index"]   = (monthly["year_month"] - monthly["year_month"].min()).apply(lambda x: x.n)
    monthly["days_in_month"] = monthly["month_ts"].dt.days_in_month.astype(float)

    # re-establish the sort the lag block relies on (the merges above do not preserve it)
    monthly = monthly.sort_values(["item_internal_id", "year_month"]).reset_index(drop=True)
    g = monthly.groupby("item_internal_id")

    # Only require the core 1-3 month lag history to keep a row, same bar as Rev 3.
    # The 6-month block is a bonus signal where available: rows lacking 6 months of
    # history simply carry a real NaN in those columns for now, which flows through the
    # same train-median imputation as every other numeric feature in Section 11 -- not
    # dropped, not fabricated. This keeps items with short histories in the training set
    # instead of discarding them, which the max(LAGS)-based dropna in a naive Rev 3-style
    # extension would otherwise have done silently.
    CORE_LAG = 3
    monthly_model = monthly.dropna(subset=[f"prev_month_qty_{CORE_LAG}"]).reset_index(drop=True)

    numeric_fill_cols = [
        "prev_qty_roll_std_3", "prev_qty_pct_change",
        "prev_qty_cv_3", "prev_price_elasticity",
        "prev_orders_per_customer", "rel_qty_vs_own_history_1", "rel_qty_vs_own_history_3",
        "gap_vs_hist", "seasonal_sold_rate",
    ]
    monthly_model[numeric_fill_cols] = monthly_model[numeric_fill_cols].fillna(0)

    return monthly_model
