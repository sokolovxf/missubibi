"""Validated, bounded background jobs for the planning workspace."""
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
import threading
import time
import json
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from app.data.adapter import adapter, DIMENSIONS, GRANULARITIES
from app.services.forecast_service import forecast

router = APIRouter(prefix='/api/planning')
_pool = ThreadPoolExecutor(max_workers=2)
_jobs = {}
_lock = threading.RLock()
_JOB_ROOT = Path(__file__).resolve().parents[2] / 'var' / 'jobs'


def _job_file(job_id):
    return _JOB_ROOT / f'{job_id}.json'


def _save_job(job_id, job):
    _JOB_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = _JOB_ROOT / f'{job_id}.tmp'
    temporary.write_text(json.dumps(job, allow_nan=False))
    temporary.replace(_job_file(job_id))


def _load_job(job_id):
    path = _job_file(job_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


class ForecastRequest(BaseModel):
    model: Literal['trend','sarima','randomforest','lstm','xgboost','ensemble'] = 'trend'
    dimension: Literal['total','item','product','customer','industry','vendor'] = 'total'
    dimension_value: str | None = None
    filters: dict[str, str] = Field(default_factory=dict)
    value_col: Literal['revenue','actual_units'] = 'revenue'
    granularity: Literal['daily','weekly','monthly','quarterly','yearly'] = 'monthly'
    calendar: Literal['calendar','fiscal_apr'] = 'calendar'
    use_classifier_signals: bool = False
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
            value_col: str='revenue', granularity: str='monthly', calendar: str='calendar', native: bool=False):
    try:
        if native:
            return adapter.get_native_series(dimension, dimension_value, value_col, granularity).to_dict('records')
        fiscal_start = 4 if calendar == 'fiscal_apr' else 1 if calendar == 'calendar' else None
        if fiscal_start is None: raise ValueError('Unsupported calendar')
        return adapter.get_series(dimension, dimension_value, value_col, granularity,
                                  fiscal_start_month=fiscal_start).to_dict('records')
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/inventory/lead-time')
def lead_time_inventory(lead_time_days: int = 30, safety_stock_months: float = 1.0,
                        coverage_months: float = 2.0, limit: int = 25,
                        dimension: str = 'item', dimension_value: str | None = None,
                        on_hand_units: float = 0.0, as_of: str | None = None):
    """Calculate replenishment needs from the canonical Mitsubishi SQL sales frame."""
    from app.services.inventory_planning import build_lead_time_plan
    try:
        return build_lead_time_plan(
            adapter._get_base_data(),
            lead_time_days=lead_time_days,
            safety_stock_months=safety_stock_months,
            coverage_months=coverage_months,
            limit=limit,
            dimension=dimension,
            dimension_value=dimension_value,
            on_hand_units=on_hand_units,
            as_of=as_of,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, 'MySQL data is unavailable. Check the backend database connection.') from exc


def _run(job_id, params):
    try:
        result = forecast(params)
    except Exception as exc:
        result = {'status': 'error', 'message': f'Forecast failed: {type(exc).__name__}. Check backend logs.'}
        import logging
        logging.getLogger(__name__).exception('Forecast job failed')
    with _lock:
        _jobs[job_id].update(status='done', result=result, finished=time.time())
        _save_job(job_id, _jobs[job_id])


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
        _save_job(job_id, _jobs[job_id])
    _pool.submit(_run, job_id, params.model_dump())
    return {'status':'running', 'job_id':job_id}


@router.get('/forecast/{job_id}')
def status(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            job = _load_job(job_id)
        if job is None:
            raise HTTPException(404, 'Job not found or expired')
        return {'status':'running', 'job_id':job_id} if job['status']=='running' else {**job['result'], 'job_id':job_id}


@router.get('/classifiers')
def classifiers():
    from app.services.classifier_runtime import predict
    from app.services.classifier_jobs import training_status
    models=[]
    for kind,name,target in [('nn','Neural network · rev 9','High demand'),('tr','Tabular transformer · rev 8','Sold / not sold')]:
        result=predict(kind)
        models.append({'id':kind,'name':name,'target':target,'status':result['status'],
            'diagnostics':result.get('diagnostics'),'items':len(result.get('predictions',[])),
            'prediction_month':result.get('prediction_month')})
    return {'status':'ok','models':models,'training':training_status(),
            'message':'Train on your sales history, then explore item probabilities and held-out model accuracy.'}


class TrainingRequest(BaseModel):
    fast: bool=True


@router.post('/classifier/train',status_code=202)
def train_classifiers(params: TrainingRequest=TrainingRequest()):
    from app.services.classifier_jobs import start_training
    return start_training(params.fast)


@router.get('/classifier/training')
def classifier_training():
    from app.services.classifier_jobs import training_status
    return training_status()


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


@router.post('/imports/preview')
async def import_preview(request: Request, filename: str='sales.csv'):
    from app.services.csv_import import preview
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>20*1024*1024:raise HTTPException(413,'CSV size limit is 20 MB.')
    try:return preview(bytes(raw),filename)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc


class ImportCommit(BaseModel):
    token: str
    mode: Literal['append','replace']='append'


@router.post('/imports/commit')
def import_commit(params: ImportCommit):
    from app.services.csv_import import commit
    try:
        result=commit(params.token,params.mode)
        from app.services.classifier_jobs import start_training
        result['training']=start_training(fast=True)
        return result
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
