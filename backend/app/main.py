from contextlib import asynccontextmanager
from app.services import retraining

@asynccontextmanager
async def lifespan(app):
    retraining.start()
    yield
    retraining.stop()

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os

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

_API_KEY = os.getenv('PLANNING_API_KEY')


@app.middleware('http')
async def optional_api_key(request: Request, call_next):
    """Protect API routes when deployed with PLANNING_API_KEY configured."""
    if _API_KEY and request.url.path.startswith('/api') and request.url.path != '/api/health':
        if request.headers.get('x-api-key') != _API_KEY:
            return JSONResponse({'detail': 'Valid x-api-key required.'}, status_code=401)
    return await call_next(request)

app.include_router(router)
app.include_router(planning_router)
