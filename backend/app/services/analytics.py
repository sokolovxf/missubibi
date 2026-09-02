from app.data.mock_data import get_sales_data


def get_dashboard_summary():
    df = get_sales_data()

    total_units = int(df["actual_units"].sum())
    total_revenue = int(df["revenue"].sum())

    forecast_accuracy = (
        1 - (abs(df["actual_units"] - df["forecast_units"]).sum() / total_units)
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