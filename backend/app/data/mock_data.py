import pandas as pd


def get_sales_data() -> pd.DataFrame:
    data = [
        {
            "month": "2025-01",
            "product": "MELSEC iQ-R",
            "customer": "Customer A",
            "actual_units": 120,
            "forecast_units": 125,
            "revenue": 480000,
        },
        {
            "month": "2025-02",
            "product": "MELSEC iQ-R",
            "customer": "Customer A",
            "actual_units": 135,
            "forecast_units": 132,
            "revenue": 540000,
        },
        {
            "month": "2025-03",
            "product": "MELSEC iQ-R",
            "customer": "Customer B",
            "actual_units": 150,
            "forecast_units": 145,
            "revenue": 600000,
        },
        {
            "month": "2025-04",
            "product": "MELSEC iQ-F",
            "customer": "Customer B",
            "actual_units": 110,
            "forecast_units": 118,
            "revenue": 440000,
        },
        {
            "month": "2025-05",
            "product": "MELSEC iQ-F",
            "customer": "Customer C",
            "actual_units": 128,
            "forecast_units": 125,
            "revenue": 512000,
        },
        {
            "month": "2025-06",
            "product": "MELSEC iQ-F",
            "customer": "Customer C",
            "actual_units": 142,
            "forecast_units": 140,
            "revenue": 568000,
        },
        {
            "month": "2025-07",
            "product": "Servo Motor",
            "customer": "Customer A",
            "actual_units": 95,
            "forecast_units": 100,
            "revenue": 380000,
        },
        {
            "month": "2025-08",
            "product": "Servo Motor",
            "customer": "Customer B",
            "actual_units": 105,
            "forecast_units": 108,
            "revenue": 420000,
        },
        {
            "month": "2025-09",
            "product": "Servo Motor",
            "customer": "Customer C",
            "actual_units": 115,
            "forecast_units": 112,
            "revenue": 460000,
        },
        {
            "month": "2025-10",
            "product": "Inverter",
            "customer": "Customer A",
            "actual_units": 160,
            "forecast_units": 155,
            "revenue": 640000,
        },
        {
            "month": "2025-11",
            "product": "Inverter",
            "customer": "Customer B",
            "actual_units": 175,
            "forecast_units": 170,
            "revenue": 700000,
        },
        {
            "month": "2025-12",
            "product": "Inverter",
            "customer": "Customer C",
            "actual_units": 190,
            "forecast_units": 185,
            "revenue": 760000,
        },
    ]

    return pd.DataFrame(data)