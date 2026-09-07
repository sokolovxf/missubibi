import threading
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.analytics import (
    get_dashboard_summary,
    get_monthly_sales,
    get_product_summary,
    get_ai_insights,
    get_sarima_forecast_for,
    get_forecast_options,
)

router = APIRouter(prefix="/api")


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.get("/dashboard")
def dashboard():
    return get_dashboard_summary()


@router.get("/sales")
def monthly_sales():
    return get_monthly_sales()


@router.get("/products")
def products():
    return get_product_summary()


@router.get("/insights")
def insights():
    return get_ai_insights()


# --- SARIMA forecast: background trigger + poll, never synchronous ---
# See sarima_engine.py's own docstring: a run takes 40-90s and must not
# block a request handler. The frontend calls POST /forecast/run once
# per job, then polls GET /forecast?job_id=... until status is no
# longer "running".
#
# Jobs are keyed by job_id so the dashboard's default whole-company
# forecast (job_id="default" — what Overview / Sales forecast / Forecast
# accuracy all read) and the Forecast Lab's exploratory per-product /
# per-customer runs (job_id="lab") don't overwrite each other. Without
# this, running a one-off product forecast from the Lab would silently
# replace the number every other view is showing.
#
# _forecast_lock protects the dict itself (fast, in-memory bookkeeping)
# — it is NOT held during the actual 40-90s run, which happens in its
# own daemon thread.

class ForecastRunRequest(BaseModel):
    job_id: str = "default"
    dimension: str = "total"          # "total" | "product" | "customer"
    dimension_value: Optional[str] = None
    value_col: str = "revenue"        # "revenue" | "actual_units"
    horizon: int = 12
    fast: bool = True


_forecast_jobs: dict = {}
_forecast_lock = threading.Lock()


def _run_forecast_background(job_id: str, params: "ForecastRunRequest"):
    try:
        result = get_sarima_forecast_for(
            dimension=params.dimension,
            dimension_value=params.dimension_value,
            value_col=params.value_col,
            horizon=params.horizon,
            fast=params.fast,
        )
    except Exception as exc:
        result = {"status": "error", "message": f"{type(exc).__name__}: {exc}"}

    with _forecast_lock:
        job = _forecast_jobs.setdefault(job_id, {})
        job["status"] = "done"
        job["result"] = result
        job["params"] = params.dict()


@router.post("/forecast/run")
def start_forecast(params: ForecastRunRequest = ForecastRunRequest()):
    with _forecast_lock:
        job = _forecast_jobs.setdefault(params.job_id, {"status": "idle", "result": None})
        if job.get("status") == "running":
            return {"status": "already_running", "job_id": params.job_id}
        job["status"] = "running"
        job["result"] = None
        job["params"] = params.dict()

    thread = threading.Thread(
        target=_run_forecast_background,
        args=(params.job_id, params),
        daemon=True,
    )
    thread.start()
    return {"status": "started", "job_id": params.job_id, "params": params.dict()}


@router.get("/forecast")
def forecast_status(job_id: str = "default"):
    with _forecast_lock:
        job = _forecast_jobs.get(job_id)

    if job is None or job.get("status") == "idle":
        return {
            "status": "idle",
            "job_id": job_id,
            "message": "No forecast run yet. POST /api/forecast/run to start one.",
        }
    if job["status"] == "running":
        return {"status": "running", "job_id": job_id}

    result = dict(job["result"] or {})
    result["job_id"] = job_id
    result["params"] = job.get("params")
    return result


@router.get("/forecast/options")
def forecast_options():
    """Distinct products/customers the Forecast Lab can slice a series by."""
    return get_forecast_options()