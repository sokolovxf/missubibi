from app.data.mock_data import get_sales_data


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
