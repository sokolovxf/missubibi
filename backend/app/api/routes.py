"""Compatibility routes backed by the shared, validated planning service."""
import threading
from fastapi import APIRouter, HTTPException
from pydantic import Field
from app.api.planning import ForecastRequest, start, status, classifier_predict, ClassifierRequest, classifier_signals
from app.services.analytics import get_dashboard_summary, get_monthly_sales, get_product_summary, get_ai_insights
from app.data.adapter import adapter

router=APIRouter(prefix='/api')
_aliases={}
_lock=threading.RLock()


@router.get('/health')
def health_check():
    return {'status':'ok'}


@router.get('/dashboard')
def dashboard():
    return get_dashboard_summary()


@router.get('/sales')
def sales():
    return get_monthly_sales()


@router.get('/products')
def products():
    return get_product_summary()


@router.get('/insights')
def insights():
    return get_ai_insights()


@router.get('/forecast/options')
def forecast_options():
    options=adapter.options()
    return {**options,'products':options['product'],'customers':options['customer'],
            'industries':options['industry'],'vendors':options['vendor'],'items':options['item']}


class LegacyForecastRequest(ForecastRequest):
    job_id: str=Field(default='default', min_length=1, max_length=100)


def _start_for(model):
    def handler(params: LegacyForecastRequest=LegacyForecastRequest()):
        key=(model,params.job_id)
        with _lock:
            previous=_aliases.get(key)
            if previous:
                try:
                    if status(previous)['status']=='running':
                        return {'status':'already_running','job_id':params.job_id}
                except HTTPException:
                    pass
            arguments=params.model_dump(exclude={'job_id'})
            arguments['model']=model
            job=start(ForecastRequest(**arguments))
            if len(_aliases)>=100:
                _aliases.pop(next(iter(_aliases)))
            _aliases[key]=job['job_id']
        return {**job,'job_id':params.job_id,'status':'started'}
    return handler


def _status_for(model):
    def handler(job_id: str='default'):
        with _lock:
            actual=_aliases.get((model,job_id))
        if actual is None:
            return {'status':'idle','job_id':job_id}
        return {**status(actual),'job_id':job_id}
    return handler


for _model,_prefix in [('sarima',''),('xgboost','/xgboost'),('randomforest','/randomforest'),
                        ('lstm','/lstm'),('trend','/trend'),('ensemble','/ensemble')]:
    router.add_api_route(f'{_prefix}/forecast/run',_start_for(_model),methods=['POST'],name=f'{_model}_start')
    router.add_api_route(f'{_prefix}/forecast',_status_for(_model),methods=['GET'],name=f'{_model}_status')

router.add_api_route('/classifier/signals',classifier_signals,methods=['GET'])
router.add_api_route('/classifier/{kind}/predict',classifier_predict,methods=['POST'])
