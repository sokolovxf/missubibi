import threading

from fastapi import APIRouter

from app.services.analytics import (
    get_dashboard_summary,
    get_monthly_sales,
    get_product_summary,
    get_ai_insights,
    get_sarima_forecast,
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
# block a request handler. The frontend should call POST /forecast/run
# once, then poll GET /forecast until status is no longer "running".

_forecast_state = {"status": "idle", "result": None}
_forecast_lock = threading.Lock()


def _run_forecast_background():
    try:
        result = get_sarima_forecast()
        with _forecast_lock:
            _forecast_state["status"] = "done"
            _forecast_state["result"] = result
    except Exception as exc:
        with _forecast_lock:
            _forecast_state["status"] = "done"
            _forecast_state["result"] = {
                "status": "error",
                "message": f"{type(exc).__name__}: {exc}",
            }


@router.post("/forecast/run")
def start_forecast():
    with _forecast_lock:
        if _forecast_state["status"] == "running":
            return {"status": "already_running"}
        _forecast_state["status"] = "running"
        _forecast_state["result"] = None

    thread = threading.Thread(target=_run_forecast_background, daemon=True)
    thread.start()
    return {"status": "started"}


@router.get("/forecast")
def forecast_status():
    with _forecast_lock:
        if _forecast_state["status"] == "idle":
            return {"status": "idle", "message": "No forecast run yet. POST /api/forecast/run to start one."}
        if _forecast_state["status"] == "running":
            return {"status": "running"}
        return _forecast_state["result"]