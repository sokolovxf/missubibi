"""Planning service: data fingerprint caching, monthly model execution, calendar views."""
from collections import OrderedDict
import copy
import hashlib
import json
import math
import threading
import pandas as pd
import numpy as np
from app.data.adapter import adapter, resample_monthly
from app.services.ensemble_engine import run_member, run_ensemble_forecast, evaluate_member

_cache = OrderedDict()
_lock = threading.RLock()


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k,v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.integer, np.bool_)):
        return value.item()
    return value


def forecast(params, force=False):
    fiscal_start_month = 4 if params.get('calendar') == 'fiscal_apr' else 1
    monthly = adapter.get_series(dimension=params['dimension'], dimension_value=params.get('dimension_value'),
        value_col=params['value_col'], filters=params.get('filters'), fiscal_start_month=1)
    if monthly.empty:
        return {'status': 'insufficient_history', 'message': 'No sales match these filters.'}
    # Classifier regressors are opt-in experimental plumbing. The default remains
    # signal-free because production certification requires origin-frozen features.
    signal_context=None
    if params.get('use_classifier_signals'):
        from app.services.classifier_signals import build_context
        signal_context = build_context(adapter._get_base_data(), params)
    monthly.attrs['classifier_signals']=signal_context
    fingerprint = hashlib.sha256(monthly.to_csv(index=False).encode()).hexdigest()
    key = hashlib.sha256((fingerprint+json.dumps(params, sort_keys=True)+json.dumps((signal_context or {}).get('versions',{}),sort_keys=True)).encode()).hexdigest()
    with _lock:
        if not force and key in _cache:
            return {**copy.deepcopy(_cache[key]), 'cached': True}
    granularity, horizon = params['granularity'], params['horizon']
    # Train at the source frequency. Add calendar boundary headroom for aggregates.
    months = {'monthly': horizon, 'daily': math.ceil(horizon/28)+1,
              'weekly': math.ceil(horizon*7/28)+1, 'quarterly': horizon*3+2,
              'yearly': horizon*12+11}[granularity]
    if params['model'] == 'ensemble':
        result = run_ensemble_forecast(monthly, horizon=months, fast=params['fast'], granularity=granularity,
                                       fiscal_start_month=fiscal_start_month)
    else:
        result = run_member(params['model'], monthly, months, params['fast'])
        if result.get('status')=='ok':
            result['validation']=evaluate_member(params['model'],monthly,params['fast'],granularity,fiscal_start_month)
            result['validation'].pop('_folds',None)
    if result.get('status') != 'ok':
        return result
    result = _json_safe(copy.deepcopy(result))
    def convert(f):
        df = pd.DataFrame({'month': f['months'], **{k: f[k] for k in ('point','lower_90','upper_90')}})
        df = resample_monthly(df, granularity, ('point', 'lower_90', 'upper_90'), fiscal_start_month).iloc[:horizon]
        return {**f, 'months': df['month'].tolist(), **{k: df[k].tolist() for k in ('point','lower_90','upper_90')},
                'horizon': len(df), 'annual_total': float(df['point'].sum()), 'annual_yoy_pct': None}
    result['forecast'] = convert(result['forecast'])
    for member in result.get('members', {}).values():
        if member.get('status') == 'ok':
            member['forecast'] = convert(member['forecast'])
    result['classifier_signals']={'status':'enabled' if signal_context else 'unavailable', 'versions':(signal_context or {}).get('versions',{}), 'policy':(signal_context or {}).get('policy')}
    result.update(history=resample_monthly(monthly, granularity, fiscal_start_month=fiscal_start_month).to_dict('records'),
                  data_fingerprint=fingerprint, cached=False, params=params,
                  source_granularity='monthly', calendar=params.get('calendar','calendar'),
                  allocation_note=('Daily/weekly values are allocated monthly estimates, not observed transactions. Boundary periods may be partial.'
                    if granularity in ('daily','weekly') else 'Calendar aggregates. The first or last period may be partial.'),
                  scenarios={'optimistic': result['forecast']['upper_90'],
                             'base': result['forecast']['point'], 'pessimistic': result['forecast']['lower_90']})
    from app.services.model_registry import record
    result["revision"] = record(params, result)
    with _lock:
        _cache[key] = copy.deepcopy(result)
        while len(_cache)>32:
            _cache.popitem(last=False)
    return result
