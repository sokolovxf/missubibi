from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="Missubibi API",
    description="AI-based Sales Order Forecasting Dashboard",
    version="1.0.0",
)

app.include_router(router)