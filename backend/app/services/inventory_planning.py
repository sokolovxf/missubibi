"""Lead-time inventory planning derived from the canonical SQL sales frame.

The Mitsubishi source tables do not contain purchase orders, receipts, or
warehouse balances. This service therefore makes those missing inputs explicit:
sales history supplies the demand run rate, while on-hand is a planner input
that defaults to zero until an inventory balance is provided.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd


MONTH_DAYS = 30.4375
INVENTORY_DIMENSIONS = ("total", "item", "product", "customer", "industry", "vendor")


def _as_date(value: str | date | datetime | None, fallback: pd.Timestamp) -> pd.Timestamp:
    if value is None:
        return fallback.normalize() + pd.offsets.MonthEnd(0)
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError("as_of must be an ISO date")
    return pd.Timestamp(parsed).normalize()


def build_lead_time_plan(
    frame: pd.DataFrame,
    *,
    lead_time_days: int = 30,
    safety_stock_months: float = 1.0,
    coverage_months: float = 2.0,
    limit: int = 25,
    dimension: str = "item",
    dimension_value: str | None = None,
    on_hand_units: float = 0.0,
    as_of: str | date | datetime | None = None,
) -> dict[str, Any]:
    """Return reorder recommendations from monthly actual units.

    The run rate blends the trailing three complete source months (70%) with
    the trailing twelve months (30%). This dampens a single recent spike while
    retaining a responsive planning signal. Order quantities target lead-time
    demand plus the requested forward coverage and safety stock.
    """
    if dimension not in INVENTORY_DIMENSIONS:
        raise ValueError("Unsupported inventory dimension")
    if dimension != "total" and dimension not in frame.columns:
        raise ValueError(f"Inventory dimension '{dimension}' is unavailable")
    if not 1 <= lead_time_days <= 365:
        raise ValueError("lead_time_days must be between 1 and 365")
    if not 0 <= safety_stock_months <= 12:
        raise ValueError("safety_stock_months must be between 0 and 12")
    if not 0.25 <= coverage_months <= 24:
        raise ValueError("coverage_months must be between 0.25 and 24")
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    if on_hand_units < 0:
        raise ValueError("on_hand_units cannot be negative")

    required = {"month", "actual_units"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Inventory source is missing: {', '.join(sorted(missing))}")
    source = frame.copy()
    source["month"] = pd.to_datetime(source["month"], errors="coerce")
    source["actual_units"] = pd.to_numeric(source["actual_units"], errors="coerce").fillna(0.0)
    source = source.loc[source["month"].notna()].copy()
    if dimension_value and dimension != "total":
        source = source.loc[source[dimension].astype("string") == dimension_value]
    if source.empty:
        planning_date = _as_date(as_of, pd.Timestamp(date.today()))
        return {
            "status": "ok",
            "rows": [],
            "source_as_of": None,
            "planning_as_of": planning_date.strftime("%Y-%m-%d"),
            "planning_start": (planning_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            "source_rows": 0,
            "assumptions": {
                "lead_time_days": lead_time_days,
                "safety_stock_months": safety_stock_months,
                "coverage_months": coverage_months,
                "on_hand_default_units": on_hand_units,
                "run_rate_method": "70% trailing 3 months + 30% trailing 12 months",
            },
        }

    source["month"] = source["month"].dt.to_period("M").dt.to_timestamp()
    cutoff = source["month"].max()
    source_as_of = cutoff + pd.offsets.MonthEnd(0)
    planning_date = _as_date(as_of, pd.Timestamp(date.today()))
    month_index = pd.date_range(cutoff - pd.DateOffset(months=11), cutoff, freq="MS")
    group_column = dimension if dimension != "total" else None
    if group_column:
        source[group_column] = source[group_column].astype("string").str.strip()
        source = source.loc[source[group_column].notna() & (source[group_column] != "")]
        source["_inventory_group"] = source[group_column]
    else:
        source["_inventory_group"] = "Company total"

    monthly_matrix = (
        source.groupby(["_inventory_group", "month"])["actual_units"]
        .sum()
        .unstack(fill_value=0.0)
        .reindex(columns=month_index, fill_value=0.0)
    )

    rows: list[dict[str, Any]] = []
    for key, monthly_row in monthly_matrix.iterrows():
        monthly = monthly_row.astype(float)
        recent = float(monthly.tail(3).mean())
        annual = float(monthly.mean())
        run_rate = max(0.0, recent * 0.70 + annual * 0.30)
        previous = float(monthly.iloc[-6:-3].mean()) if len(monthly) >= 6 else 0.0
        trend_pct = ((recent / previous) - 1.0) * 100.0 if previous > 0 else None
        lead_demand = run_rate * lead_time_days / MONTH_DAYS
        safety_stock = run_rate * safety_stock_months
        reorder_point = lead_demand + safety_stock
        target_stock = run_rate * (lead_time_days / MONTH_DAYS + coverage_months + safety_stock_months)
        order_qty = max(0.0, target_stock - on_hand_units)
        days_cover = on_hand_units / run_rate * MONTH_DAYS if run_rate > 0 else None
        if run_rate > 0 and on_hand_units > reorder_point:
            order_by = planning_date + pd.to_timedelta(max(0.0, (on_hand_units - reorder_point) / run_rate * MONTH_DAYS), unit="D")
        else:
            order_by = planning_date
        arrival = order_by + pd.to_timedelta(lead_time_days, unit="D")
        rows.append(
            {
                "dimension": dimension,
                "key": str(key),
                "item": str(key) if dimension == "item" else None,
                "vendor": None,
                "recent_avg_units": round(recent, 3),
                "annual_avg_units": round(annual, 3),
                "run_rate_units_per_month": round(run_rate, 3),
                "trend_pct": round(trend_pct, 2) if trend_pct is not None else None,
                "lead_time_demand_units": round(lead_demand, 3),
                "safety_stock_units": round(safety_stock, 3),
                "reorder_point_units": round(reorder_point, 3),
                "target_stock_units": round(target_stock, 3),
                "on_hand_units": round(on_hand_units, 3),
                "suggested_order_units": round(order_qty, 3),
                "days_of_cover": round(days_cover, 1) if days_cover is not None else None,
                "order_by_date": order_by.strftime("%Y-%m-%d"),
                "expected_arrival_date": arrival.strftime("%Y-%m-%d"),
                "status": "Order now" if on_hand_units <= reorder_point else "Covered",
                "months_with_source_data": int((monthly > 0).sum()),
            }
        )

    rows.sort(key=lambda row: (row["suggested_order_units"], row["run_rate_units_per_month"]), reverse=True)
    return {
        "status": "ok",
        "rows": rows[:limit],
        "source_as_of": source_as_of.strftime("%Y-%m-%d"),
        "planning_as_of": planning_date.strftime("%Y-%m-%d"),
        "planning_start": (planning_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "source_rows": int(len(source)),
        "total_groups": len(rows),
        "vendor_mapping_available": bool(source.get("vendor", pd.Series(dtype="object")).notna().any()),
        "assumptions": {
            "lead_time_days": lead_time_days,
            "safety_stock_months": safety_stock_months,
            "coverage_months": coverage_months,
            "on_hand_default_units": on_hand_units,
            "run_rate_method": "70% trailing 3 months + 30% trailing 12 months",
            "source_note": "Supplier lead time and warehouse on-hand are planning inputs; they are not present in the Mitsubishi sales source.",
        },
    }
