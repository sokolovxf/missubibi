"""Common chronological validation and regularized inverse-MASE ensemble.

Legacy engines mutate module-level state; isolated workers also prevent native-library conflicts.
Weights are derived only from preceding training windows; failed members are excluded.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import threading
import numpy as np
import pandas as pd

MODELS = ('trend', 'sarima', 'randomforest', 'lstm', 'xgboost')
_LOCKS = {name: threading.RLock() for name in MODELS}


def run_member(name, frame, horizon, fast=True):
    try:
        with _LOCKS[name]:
            payload = {'model':name, 'rows':json.loads(frame.to_json(orient='records', date_format='iso')),
                       'horizon':horizon, 'fast':fast, 'classifier_signals':frame.attrs.get('classifier_signals')}
            process = subprocess.run([sys.executable, '-m', 'app.services.model_worker'],
                input=json.dumps(payload), capture_output=True, text=True, timeout=600,
                cwd=Path(__file__).resolve().parents[2])
            if process.returncode:
                raise RuntimeError(f'Model worker exited ({process.returncode})')
            result = json.loads(process.stdout)
        if result.get('status') == 'ok':
            forecast = result['forecast']
            expected = pd.date_range(pd.to_datetime(frame['month']).max()+pd.offsets.MonthBegin(), periods=horizon, freq='MS')
            if not pd.DatetimeIndex(pd.to_datetime(forecast['months'])).equals(expected):
                raise ValueError('Forecast dates do not continue the training history')
            for key in ('point', 'lower_90', 'upper_90'):
                values = np.asarray(forecast[key], dtype=float)
                if len(values) != horizon or not np.isfinite(values).all():
                    raise ValueError('Model returned invalid forecast values')
        return result
    except Exception as exc:
        message = 'XGBoost requires the OpenMP runtime (brew install libomp on macOS).' if name == 'xgboost' and 'libomp' in str(exc) else f'{type(exc).__name__}: {exc}'
        return {'status': 'unavailable', 'message': message}


def evaluate_member(name, frame, fast=True, granularity='monthly', fiscal_start_month=1):
    n = len(frame)
    errors, scales, fold_rows = [], [], []
    # Two expanding windows with up to 12 monthly observations per test fold.
    width = min(12, max(1, (n-30)//2))
    for end in (n-2*width, n-width):
        if end < 25:
            continue
        train = frame.iloc[:end]
        result = run_member(name, train, width, fast)
        if result.get('status') != 'ok':
            continue
        from app.data.adapter import resample_monthly
        y = resample_monthly(train, granularity, fiscal_start_month=fiscal_start_month)['value'].to_numpy(float)
        lag = {'monthly':12, 'daily':365, 'weekly':52, 'quarterly':4, 'yearly':1}[granularity]
        scale = float(np.abs(y[lag:]-y[:-lag]).mean()) if len(y)>lag else 0.
        actual = resample_monthly(frame.iloc[end:end+width], granularity, fiscal_start_month=fiscal_start_month)['value'].to_numpy(float)
        predicted_frame = pd.DataFrame({'month':result['forecast']['months'], 'value':result['forecast']['point']})
        predicted = resample_monthly(predicted_frame, granularity, fiscal_start_month=fiscal_start_month)['value'].to_numpy(float)
        error = float(np.abs(actual-predicted).mean())
        errors.append(error)
        scales.append(scale)
        fold_rows.append({"origin":end,"actual":actual.tolist(),"predicted":predicted.tolist(),"scale":scale})
    mase = [e/s for e, s in zip(errors, scales) if s > 0]
    absolute_error=sum(float(np.abs(np.asarray(f['actual'])-f['predicted']).sum()) for f in fold_rows)
    actual_total=sum(float(np.abs(f['actual']).sum()) for f in fold_rows)
    wape=100*absolute_error/actual_total if actual_total>0 else None
    fold_summary=[]
    for fold in fold_rows:
        actual=np.asarray(fold['actual'],dtype=float)
        predicted=np.asarray(fold['predicted'],dtype=float)
        denominator=float(np.abs(actual).sum())
        fold_summary.append({'origin':fold['origin'],
            'test_start':str(frame.iloc[fold['origin']]['month']),
            'test_end':str(frame.iloc[min(len(frame)-1,fold['origin']+len(actual)-1)]['month']),
            'horizon':len(actual),
            'wape_pct':100*float(np.abs(actual-predicted).sum())/denominator if denominator else None})
    source_fingerprint=hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest()
    return {'accuracy_pct':max(0.,100-wape) if wape is not None else None,
            'wape_pct':wape,'accuracy_definition':'max(0, 100 − validation WAPE)', '_folds':fold_rows,
            'mae': float(np.mean(errors)) if errors else None,
            'mase': float(np.mean(mase)) if mase else None,
            'folds': len(errors), 'horizon': width, 'granularity': granularity,
            'method': 'expanding-window seasonal MASE',
            'protocol_version':'walk-forward-v1', 'history_points':n,
            'history_start':str(frame.iloc[0]['month']), 'history_end':str(frame.iloc[-1]['month']),
            'data_fingerprint':source_fingerprint, 'fold_summary':fold_summary,
            'reproducible':True}


def run_ensemble_forecast(sales_df, horizon=12, fast=True, **kwargs):
    fiscal_start_month = kwargs.get('fiscal_start_month', 1)
    def member(name):
        validation = evaluate_member(name, sales_df, fast, kwargs.get('granularity','monthly'), fiscal_start_month)
        result = run_member(name, sales_df, horizon, fast)
        return name, result, validation
    with ThreadPoolExecutor(max_workers=3) as pool:
        runs = list(pool.map(member, MODELS))
    members = {name: {**result, 'validation': validation} for name, result, validation in runs}
    valid = {name: result for name, result in members.items() if result.get('status') == 'ok'}
    if not valid:
        return {'status': 'error', 'message': 'No model could forecast this series.', 'members': members}
    validated = {n: r for n, r in valid.items() if r['validation']['mase'] is not None}
    selected = validated or valid
    scores = np.array([1/max(r['validation']['mase'], .05) if validated else 1 for r in selected.values()])
    weights = .05 + (1-.05*len(scores))*scores/scores.sum()
    weight_map = dict(zip(selected, weights.tolist()))
    first = next(iter(selected.values()))['forecast']
    forecast = dict(first)
    for key in ('point', 'lower_90', 'upper_90'):
        forecast[key] = sum(np.asarray(r['forecast'][key])*weight_map[n] for n, r in selected.items()).tolist()
    forecast['spec'] = 'Regularized inverse-MASE ensemble'
    forecast['annual_total'] = sum(forecast['point'])
    forecast['interval_source'] = 'Weighted member bounds; approximate, not jointly calibrated'
    # Evaluate the ensemble with weights learned only on PRECEDING folds.
    origins=sorted({f['origin'] for r in members.values() for f in r['validation']['_folds']})
    past_scores={}
    ensemble_actual, ensemble_pred=[],[]
    for origin in origins:
        available={n:next((f for f in r['validation']['_folds'] if f['origin']==origin),None) for n,r in members.items()}
        available={n:f for n,f in available.items() if f is not None}
        if not available:continue
        score=np.array([1/max(past_scores.get(n,1.),.05) for n in available])
        w=.05+(1-.05*len(score))*score/score.sum()
        prediction=sum(np.asarray(f['predicted'])*v for f,v in zip(available.values(),w))
        actual=np.asarray(next(iter(available.values()))['actual'])
        ensemble_actual.extend(actual.tolist());ensemble_pred.extend(prediction.tolist())
        for n,f in available.items():
            if f['scale']>0:past_scores[n]=float(np.abs(np.asarray(f['actual'])-f['predicted']).mean()/f['scale'])
    denominator=float(np.abs(ensemble_actual).sum())
    wape=100*float(np.abs(np.asarray(ensemble_actual)-ensemble_pred).sum())/denominator if denominator else None
    validation={'accuracy_pct':max(0.,100-wape) if wape is not None else None,'wape_pct':wape,
                'folds':len(origins),'method':'Walk-forward ensemble; weights from preceding folds only',
                'accuracy_definition':'max(0, 100 − validation WAPE)',
                'protocol_version':'walk-forward-ensemble-v1', 'history_points':len(sales_df),
                'history_start':str(sales_df.iloc[0]['month']), 'history_end':str(sales_df.iloc[-1]['month']),
                'data_fingerprint':hashlib.sha256(sales_df.to_csv(index=False).encode()).hexdigest(),
                'reproducible':True}
    for member in members.values():member['validation'].pop('_folds',None)
    return {'status': 'ok', 'validation':validation, 'forecast': forecast, 'members': members, 'weights': weight_map,
            'weight_method': 'chronological CV inverse MASE' if validated else 'equal: no valid CV scale',
            'warnings': [{'kind': 'member_excluded', 'message': f'{n}: {r.get("message", r["status"])}'}
                         for n, r in members.items() if n not in selected]}
