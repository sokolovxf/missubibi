from contextlib import asynccontextmanager
from app.services import retraining

@asynccontextmanager
async def lifespan(app):
    retraining.start()
    yield
    retraining.stop()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.planning import router as planning_router

app = FastAPI(
    lifespan=lifespan,
    title="Missubibi API",
    description="AI-based Sales Order Forecasting Dashboard",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(planning_router)
