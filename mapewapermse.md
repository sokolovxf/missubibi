Got it — you want the project’s actual current model metrics. I’m checking the recorded validation outputs first; if MAPE and RMSE are not stored yet, I’ll calculate them from the same SQL-backed validation runs instead of inventing values.




Read files, ran commands


The current project records WAPE, but MAPE and RMSE are not stored in the dashboard’s shared validation payload. I’m calculating all three from the same 48-month Mitsubishi snapshot and the same two expanding holdout windows, so the numbers will be comparable across the six forecasting models. NN/TR are classifiers, so they use classification metrics rather than MAPE/RMSE/WAPE.




Ran cat > /private/tmp/missubibi_metrics.py <<'PY'
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timedelta
import os, re, json, math, time
import numpy as np
import pandas as pd

os.environ.setdefault('DATABASE_URL', 'sqlite://')

XLSX = Path('/Users/mac/Documents/Missubibi/DATA ORIGINAL + MERGED FILE/RawData_Combined.xlsx')
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def col_number(ref):
    s = ''.join(ch for ch in ref if ch.isalpha())
    n = 0
    for ch in s:
        n = n * 26 + ord(ch.upper()) - 64
    return n - 1

def excel_date(value):
    return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()

def decode_cell(cell, shared):
    typ = cell.attrib.get('t')
    if typ == 'inlineStr':
        return ''.join(t.text or '' for t in cell.findall('.//m:t', NS))
    v = cell.find('m:v', NS)
    if v is None:
        return None
    raw = v.text
    return shared[int(raw)] if typ == 's' else raw

def load_monthly():
    with ZipFile(XLSX) as z:
        shared_root = ET.fromstring(z.read('xl/sharedStrings.xml'))
        shared = [''.join(t.text or '' for t in si.findall('.//m:t', NS)) for si in shared_root.findall('m:si', NS)]
        totals = defaultdict(lambda: [0.0, 0.0])
        seen = set()
        header = None
        rows = 0
        kept = 0
        for event, row in ET.iterparse(z.open('xl/worksheets/sheet3.xml'), events=('end',)):
            if not row.tag.endswith('}row'):
                continue
            cells = {}
            for cell in row.findall('m:c', NS):
                idx = col_number(cell.attrib.get('r', 'A1'))
                cells[idx] = decode_cell(cell, shared)
            if header is None:
                header = [cells.get(i) for i in range(max(cells) + 1)]
                rows += 1
                row.clear()
                continue
            rows += 1
            so_id = cells.get(0)
            order_date_raw = cells.get(1)
            item = cells.get(7)
            base_raw = cells.get(8)
            qty_raw = cells.get(9)
            if None in (so_id, order_date_raw, item, base_raw, qty_raw):
                row.clear(); continue
            try:
                order_date = excel_date(order_date_raw)
                base = float(base_raw)
                qty = float(qty_raw)
            except (ValueError, TypeError):
                row.clear(); continue
            # Same composite identity used by DataAdapter, with year/month derived from the preserved date.
            key = (str(so_id), str(item), qty, base, order_date.year, order_date.month)
            if key in seen:
                row.clear(); continue
            seen.add(key); kept += 1
            month = order_date.strftime('%Y-%m-01')
            totals[month][0] += qty
            totals[month][1] += base * qty
            row.clear()
    frame = pd.DataFrame([{'month': month, 'actual_units': vals[0], 'revenue': vals[1]} for month, vals in sorted(totals.items())])
    return frame, rows - 1, kept

def metric_arrays(folds):
    actual=[]; pred=[]
    for fold in folds:
        actual.extend(fold['actual']); pred.extend(fold['predicted'])
    y=np.asarray(actual,dtype=float); yhat=np.asarray(pred,dtype=float); err=y-yhat
    nz=np.abs(y)>0
    return {
        'mape_pct': float(np.mean(np.abs(err[nz]/y[nz]))*100) if nz.any() else None,
        'rmse': float(np.sqrt(np.mean(err**2))) if len(err) else None,
        'wape_pct': float(np.abs(err).sum()/np.abs(y).sum()*100) if np.abs(y).sum() else None,
        'points': int(len(y)),
    }

def ensemble_arrays(fold_map):
    origins=sorted({f['origin'] for fs in fold_map.values() for f in fs})
    by_model_origin={n:{f['origin']:f for f in fs} for n,fs in fold_map.items()}
    past_scores={}; actual=[]; pred=[]
    for origin in origins:
        available={n:by_model_origin[n][origin] for n in fold_map if origin in by_model_origin[n]}
        if not available: continue
        score=np.array([1/max(past_scores.get(n,1.),.05) for n in available],dtype=float)
        weights=.05+(1-.05*len(score))*score/score.sum()
        y=np.asarray(next(iter(available.values()))['actual'],dtype=float)
        yh=sum(np.asarray(f['predicted'],dtype=float)*w for f,w in zip(available.values(),weights))
        actual.extend(y.tolist()); pred.extend(yh.tolist())
        for n,f in available.items():
            if f['scale']>0:
                past_scores[n]=float(np.abs(np.asarray(f['actual'])-f['predicted']).mean()/f['scale'])
    y=np.asarray(actual,dtype=float); yhat=np.asarray(pred,dtype=float); err=y-yhat; nz=np.abs(y)>0
    return {
        'mape_pct': float(np.mean(np.abs(err[nz]/y[nz]))*100) if nz.any() else None,
        'rmse': float(np.sqrt(np.mean(err**2))) if len(err) else None,
        'wape_pct': float(np.abs(err).sum()/np.abs(y).sum()*100) if np.abs(y).sum() else None,
        'points': int(len(y)),
    }

start=time.time()
frame, source_rows, kept_rows = load_monthly()
print(json.dumps({'source_rows':source_rows,'dedup_rows':kept_rows,'months':len(frame),'start':frame.iloc[0]['month'],'end':frame.iloc[-1]['month']}, indent=2), flush=True)
from app.services.ensemble_engine import evaluate_member
models=('trend','sarima','randomforest','lstm','xgboost')
fold_map={}; out={}
for name in models:
    print(f'Running {name}...', flush=True)
    v=evaluate_member(name, frame[['month','revenue']].rename(columns={'revenue':'value'}), fast=True, granularity='monthly', fiscal_start_month=1)
    fold_map[name]=v.get('_folds',[])
    out[name]=metric_arrays(fold_map[name])
    print(json.dumps({name:out[name]}, indent=2), flush=True)
out['ensemble']=ensemble_arrays(fold_map)
print(json.dumps({'metrics':out,'elapsed_seconds':round(time.time()-start,1)}, indent=2), flush=True)
PY
cd backend && DATABASE_URL=sqlite:// .venv/bin/python /private/tmp/missubibi_metrics.py




The SQL-equivalent snapshot reconstructed correctly: 272,000 source lines, 265,135 deduplicated forecast rows, and 48 monthly points from April 2021 through March 2025. The first metric run stopped before model evaluation because the temporary runner needed the backend module path; I’m rerunning it with that path corrected.




Read files, ran commands


The first SQL-backed calculation is complete for Trend, SARIMA, LSTM, XGBoost, and Ensemble. Random Forest’s fresh run differs from the older registry record, so I’m repeating that member once before I report the table; I don’t want to present a stale or unstable number as current.




  Ran commands





Current forecasting metrics, calculated over the two expanding validation windows and 18 held-out monthly points:
Model	MAPE	RMSE	WAPE
Ensemble	14.92%	฿40,848,039	14.87%
Trend Regression	20.79%	฿54,034,594	21.28%
SARIMA	16.88%	฿39,365,844	16.52%
Random Forest	16.75%	฿43,044,532	16.62%
LSTM	13.09%	฿36,658,649	13.59%
XGBoost	24.63%	฿64,378,800	24.13%


NN and Tabular Transformer are classifiers, so their relevant metrics are accuracy, balanced accuracy, ROC AUC, and confusion matrix—not MAPE/RMSE/WAPE.