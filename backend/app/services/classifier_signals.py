"""Dated out-of-sample classifier regressors and explicit future carry-forward policy."""
import json
import numpy as np
import pandas as pd
from app.services.classifier_runtime import ROOT
from app.services.classifier_training_data import data_fingerprint


def build_context(source, params):
    fingerprint=data_fingerprint(source)
    selected=source
    filters=dict(params.get('filters',{}))
    if params['dimension']!='total':filters[params['dimension']]=params.get('dimension_value')
    for key,value in filters.items():
        if value:selected=selected.loc[selected[key]==value]
    items=set(selected.item.dropna().astype(str))
    merged=None;versions={}
    for kind in ('nn','tr'):
        current=ROOT/kind/'current.json'
        if not current.exists():return None
        revision=json.loads(current.read_text())['version'];folder=ROOT/kind/'versions'/revision
        snapshot=json.loads((folder/'predictions.json').read_text())
        if snapshot['data_fingerprint']!=fingerprint:return None
        history=pd.read_csv(folder/'historical_signals.csv',dtype={'item_internal_id':str})
        history=history.loc[history.item_internal_id.isin(items)]
        history=history.loc[history.year_month>=history.trained_before] # reject a provenance violation
        monthly=history.groupby('year_month').probability.sum()
        monthly.index=pd.to_datetime(monthly.index).strftime('%Y-%m-%d')
        monthly.loc[snapshot['prediction_month']]=sum(p['probability'] for p in snapshot['predictions'] if p['item'] in items)
        frame=monthly.rename(kind).to_frame()
        merged=frame if merged is None else merged.join(frame,how='inner')
        versions[kind]=revision
    return {'values':{index:{'nn':float(r.nn),'tr':float(r.tr)} for index,r in merged.iterrows()},
            'versions':versions,'policy':'Past-only item probability sums. Future horizons carry the first available next-period signal forward.'}

_CONTEXT=None
_START=None
_CUTOFF=None


def configure(frame, context):
    global _CONTEXT,_START,_CUTOFF
    dates=pd.to_datetime(frame['month'])
    _START=dates.min();_CUTOFF=dates.max()
    # Do not add unidentifiable regressors to short series / early backtest folds.
    count=sum(date<=_CUTOFF.strftime('%Y-%m-%d') for date in (context or {}).get('values',{}))
    _CONTEXT=context if count>=6 else None


def for_dates(dates):
    dates=pd.DatetimeIndex(pd.to_datetime(dates))
    if _CONTEXT is None:return pd.DataFrame(index=dates)
    next_date=(_CUTOFF+pd.offsets.MonthBegin()).strftime('%Y-%m-%d')
    result=[]
    for date in dates:
        key=date.strftime('%Y-%m-%d') if date<=_CUTOFF else next_date
        signals=_CONTEXT['values'].get(key)
        result.append([np.log1p(signals['nn']),np.log1p(signals['tr']),1.] if signals else [0.,0.,0.])
    return pd.DataFrame(result,index=dates,columns=['classifier_nn','classifier_tr','classifier_available'])


def for_positions(positions):
    if _START is None:return pd.DataFrame(index=range(len(positions)))
    dates=[_START+pd.DateOffset(months=int(p)) for p in positions]
    return for_dates(dates).reset_index(drop=True)
