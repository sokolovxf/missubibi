from fastapi import APIRouter

from app.services.analytics import (
    get_dashboard_summary,
    get_monthly_sales,
    get_product_summary,
    get_ai_insights,
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