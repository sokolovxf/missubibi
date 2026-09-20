"""One model per process: isolate native OpenMP/PyTorch libraries and notebook globals."""
import contextlib
import importlib
import json
import sys
import numpy as np
import pandas as pd


def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,np.ndarray)):return [clean(v) for v in value]
    if isinstance(value,(float,np.floating)):return float(value) if np.isfinite(value) else None
    if isinstance(value,(np.integer,np.bool_)):return value.item()
    return value


def main():
    payload=json.load(sys.stdin)
    if payload['model'] not in ('trend','sarima','randomforest','lstm','xgboost'):
        raise ValueError('Unknown model')
    with contextlib.redirect_stdout(sys.stderr):
        module=importlib.import_module(f"app.services.{payload['model']}_engine")
        result=module.run_forecast(pd.DataFrame(payload['rows']),month_col='month',value_col='value',
            horizon=payload['horizon'],fast=payload['fast'],series_name='selected_series')
    json.dump(clean(result),sys.stdout,allow_nan=False)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        json.dump({'status':'unavailable','message':f'{type(exc).__name__}: {exc}'},sys.stdout)
