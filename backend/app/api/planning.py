"""Validated, bounded background jobs for the planning workspace."""
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
import threading
import time
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator
from app.data.adapter import adapter, DIMENSIONS, GRANULARITIES
from app.services.forecast_service import forecast

router = APIRouter(prefix='/api/planning')
_pool = ThreadPoolExecutor(max_workers=2)
_jobs = {}
_lock = threading.RLock()


class ForecastRequest(BaseModel):
    model: Literal['trend','sarima','randomforest','lstm','xgboost','ensemble'] = 'trend'
    dimension: Literal['total','item','product','customer','industry','vendor'] = 'total'
    dimension_value: str | None = None
    filters: dict[str, str] = Field(default_factory=dict)
    value_col: Literal['revenue','actual_units'] = 'revenue'
    granularity: Literal['daily','weekly','monthly','quarterly','yearly'] = 'monthly'
    horizon: int = Field(default=12, ge=1, le=120)
    fast: bool = True

    @model_validator(mode='after')
    def validate_selection(self):
        if self.dimension != 'total' and not self.dimension_value:
            raise ValueError('Choose a dimension value')
        if any(k not in DIMENSIONS[1:] for k in self.filters):
            raise ValueError('Unknown filter dimension')
        if self.granularity == 'yearly' and self.horizon > 10:
            raise ValueError('Yearly horizon is limited to 10 years')
        if self.granularity == 'quarterly' and self.horizon > 40:
            raise ValueError('Quarterly horizon is limited to 40 quarters')
        return self


@router.get('/options')
def options():
    try:
        return {'dimensions': adapter.options(), 'granularities': GRANULARITIES,
                'source_granularity': 'monthly'}
    except Exception as exc:
        raise HTTPException(503, 'MySQL data is unavailable. Check the backend database connection.') from exc


@router.get('/history')
def history(dimension: str='total', dimension_value: str | None=None,
            value_col: str='revenue', granularity: str='monthly'):
    try:
        return adapter.get_series(dimension, dimension_value, value_col, granularity).to_dict('records')
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _run(job_id, params):
    try:
        result = forecast(params)
    except Exception as exc:
        result = {'status': 'error', 'message': f'Forecast failed: {type(exc).__name__}. Check backend logs.'}
        import logging
        logging.getLogger(__name__).exception('Forecast job failed')
    with _lock:
        _jobs[job_id].update(status='done', result=result, finished=time.time())


@router.post('/forecast/run', status_code=202)
def start(params: ForecastRequest):
    with _lock:
        for key in list(_jobs):
            if _jobs[key].get('finished', float('inf')) < time.time()-3600:
                del _jobs[key]
        if sum(j['status']=='running' for j in _jobs.values()) >= 4:
            raise HTTPException(429, 'Forecast queue is full. Please wait for a running job.')
        if len(_jobs) >= 100:
            oldest = next((k for k,v in _jobs.items() if v['status']=='done'), None)
            if oldest:
                del _jobs[oldest]
        job_id = uuid4().hex
        _jobs[job_id] = {'status':'running', 'result':None}
    _pool.submit(_run, job_id, params.model_dump())
    return {'status':'running', 'job_id':job_id}


@router.get('/forecast/{job_id}')
def status(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(404, 'Job not found or expired')
        return {'status':'running', 'job_id':job_id} if job['status']=='running' else {**job['result'], 'job_id':job_id}


@router.get('/classifiers')
def classifiers():
    return {'status':'unavailable', 'models':[
        {'name':'Neural network · rev 9', 'target':'High demand', 'status':'Awaiting trained model export'},
        {'name':'Tabular transformer · rev 8', 'target':'Sold / not sold', 'status':'Awaiting trained model export'}],
        'message':'September source notebooks are present. Deployment requires trained weights, fitted preprocessing, feature schema, and validation diagnostics. No probabilities or exogenous signals are fabricated.'}


class ClassifierRequest(BaseModel):
    item: str | None = None


@router.post('/classifier/{kind}/predict')
def classifier_predict(kind: Literal['nn','tr'], params: ClassifierRequest):
    from app.services.classifier_runtime import predict
    return predict(kind, params.item)


@router.get('/classifier/signals')
def classifier_signals():
    from app.services.classifier_runtime import signals
    return signals()


@router.get('/registry')
def registry():
    from app.services.model_registry import list_series
    return list_series()


@router.get('/registry/{revision}')
def revision_details(revision: str):
    from app.services.model_registry import get_revision
    try:
        return get_revision(revision)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post('/registry/{revision}/activate')
def rollback(revision: str):
    from app.services.model_registry import activate
    try:
        return activate(revision)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get('/compare')
def compare_revisions(a: str, b: str):
    from app.services.model_registry import compare
    try:
        return compare(a,b)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
