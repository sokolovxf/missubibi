"""Preview-first CSV ingestion. Existing source tables are never overwritten."""
import hashlib
import io
import json
import threading
import time
from pathlib import Path
from uuid import uuid4
import numpy as np
import pandas as pd
from sqlalchemy import Column, MetaData, String, Table, Text, select, inspect
from app.database import engine

ROOT = Path(__file__).resolve().parents[2] / 'var' / 'imports'
_lock = threading.RLock()
metadata = MetaData()
batches = Table('ForecastImportBatch', metadata, Column('id',String(32),primary_key=True),Column('details',Text,nullable=False))
rows = Table('ForecastImportedSales', metadata,Column('id',String(32),primary_key=True),Column('batch_id',String(32),index=True),Column('payload',Text,nullable=False))
settings = Table('ForecastDatasetSettings',metadata,Column('id',String(32),primary_key=True),Column('payload',Text,nullable=False))
COLUMNS = ['month','item','product','customer','industry','vendor','actual_units','revenue']
ALIASES = {'year_month':'month','date':'month','sales_order_date':'month','item_code':'item','sku':'item',
           'product_category_2':'product','company_name':'customer','fa_sub_industries':'industry',
           'vendor_name':'vendor','quantity':'actual_units','units':'actual_units','total_revenue_thb':'revenue'}


def fingerprint(frame):
    normalized=frame.reindex(columns=COLUMNS).copy()
    for col in COLUMNS:
        if col in ('revenue','actual_units'):normalized[col]=pd.to_numeric(normalized[col]).round(6).astype(str)
        else:normalized[col]=normalized[col].astype('string').fillna('').str.strip()
    return normalized.apply(lambda r:hashlib.sha256(json.dumps(r.tolist()).encode()).hexdigest(),axis=1)


def load_overlay():
    if not inspect(engine).has_table(settings.name):return True, pd.DataFrame(), {}
    with engine.connect() as conn:
        state=conn.execute(select(settings.c.payload).where(settings.c.id=='active')).scalar()
        state=json.loads(state) if state else {'base':True,'batches':[],'vendors':{}}
        values=conn.execute(select(rows.c.payload).where(rows.c.batch_id.in_(state['batches']))).scalars().all() if state['batches'] else []
    return state['base'],pd.DataFrame([json.loads(v) for v in values]),state.get('vendors',{})


def preview(raw,filename):
    if len(raw)>20*1024*1024:raise ValueError('CSV size limit is 20 MB.')
    if not filename.lower().endswith('.csv'):raise ValueError('Choose a .csv file.')
    try:frame=pd.read_csv(io.BytesIO(raw),dtype=str,encoding='utf-8-sig',keep_default_na=False)
    except Exception as exc:raise ValueError('Cannot read this CSV. Use UTF-8 and a header row.') from exc
    if frame.empty or len(frame)>250000:raise ValueError('Supply 1–250,000 rows.')
    frame.columns=frame.columns.str.strip().str.lower()
    frame=frame.rename(columns=ALIASES)
    if frame.columns.duplicated().any():raise ValueError('Two columns map to the same field. Keep only one alias per field.')
    mapping_only='vendor' in frame and 'item' in frame and 'month' not in frame
    required=['item','vendor'] if mapping_only else ['month','item','actual_units','revenue']
    missing=[c for c in required if c not in frame]
    if missing:raise ValueError('Missing columns: '+', '.join(missing))
    errors=[]
    if mapping_only:
        frame=frame[required].apply(lambda s:s.str.strip())
        invalid=(frame=='').any(axis=1)
        if invalid.any():errors.append('Item and vendor must be populated on every row.')
        if frame.groupby('item').vendor.nunique().gt(1).any():errors.append('Each item must map to only one vendor.')
        duplicates=int(frame.duplicated().sum());frame=frame.drop_duplicates()
    else:
        frame=frame.reindex(columns=COLUMNS,fill_value='')
        for col in COLUMNS:frame[col]=frame[col].str.strip()
        dates=pd.to_datetime(frame.month,format='mixed',errors='coerce')
        if dates.isna().any():errors.append(f'{int(dates.isna().sum())} invalid dates. Use YYYY-MM or YYYY-MM-DD.')
        frame['month']=dates.dt.to_period('M').dt.to_timestamp().dt.strftime('%Y-%m-%d')
        for col in ('actual_units','revenue'):
            frame[col]=pd.to_numeric(frame[col].str.replace(',','',regex=False),errors='coerce')
            if not np.isfinite(frame[col]).all():errors.append(f'{col} contains missing or invalid numbers.')
        if frame.item.eq('').any():errors.append('Every row needs an item / SKU.')
        duplicates=int(frame.duplicated().sum());frame=frame.drop_duplicates()
    payload=json.loads(frame.to_json(orient='records'))
    token=uuid4().hex
    details={'token':token,'filename':Path(filename).name,'kind':'vendor_mapping' if mapping_only else 'sales',
             'row_count':len(frame),'duplicate_rows':duplicates,'errors':errors,
             'period_start':None if mapping_only else (frame.month.dropna().min() if frame.month.notna().any() else None),
             'period_end':None if mapping_only else (frame.month.dropna().max() if frame.month.notna().any() else None),
             'columns':frame.columns.tolist(),'sample':payload[:8],
             'created':time.time()}
    if not errors:
        ROOT.mkdir(parents=True,exist_ok=True)
        (ROOT/f'{token}.json').write_text(json.dumps({'details':details,'rows':payload},allow_nan=False))
    return details


def commit(token,mode):
    if len(token)!=32 or any(c not in '0123456789abcdef' for c in token):raise ValueError('Invalid import preview')
    if mode not in ('append','replace'):raise ValueError('Choose append or replace')
    with _lock:
        path=ROOT/f'{token}.json'
        if not path.exists():raise ValueError('Preview not found. Upload the CSV again.')
        payload=json.loads(path.read_text())
        if time.time()-payload['details']['created']>3600:raise ValueError('Preview expired. Upload the CSV again.')
        metadata.create_all(engine)
        from app.data.adapter import adapter
        # A token is idempotent even after an uncertain HTTP response.
        with engine.connect() as conn:
            previous=conn.execute(select(batches.c.details).where(batches.c.id==token)).scalar()
            if previous:return json.loads(previous)
        frame=pd.DataFrame(payload['rows'])
        duplicates=0
        if payload['details']['kind']=='sales' and mode=='append':
            adapter.invalidate()
            existing=set(fingerprint(adapter._get_base_data()))
            keep=~fingerprint(frame).isin(existing)
            duplicates=int((~keep).sum());frame=frame.loc[keep]
        with engine.begin() as conn:
            current=conn.execute(select(settings.c.payload).where(settings.c.id=='active').with_for_update()).scalar()
            state=json.loads(current) if current else {'base':True,'batches':[],'vendors':{}}
            if payload['details']['kind']=='vendor_mapping':
                state.setdefault('vendors',{}).update(dict(zip(frame.item,frame.vendor)))
            else:
                records=json.loads(frame.to_json(orient='records'))
                if records:conn.execute(rows.insert(),[{'id':uuid4().hex,'batch_id':token,'payload':json.dumps(r)} for r in records])
                if mode=='replace':state.update(base=False,batches=[token])
                else:state['batches'].append(token)
            result={'status':'ok','batch_id':token,'kind':payload['details']['kind'],'rows_imported':len(frame),
                    'duplicates_skipped':duplicates,'mode':mode,'message':'Import applied. Forecasts and classifiers use the updated dataset.'}
            conn.execute(batches.insert().values(id=token,details=json.dumps(result)))
            if current:conn.execute(settings.update().where(settings.c.id=='active').values(payload=json.dumps(state)))
            else:conn.execute(settings.insert().values(id='active',payload=json.dumps(state)))
        adapter.invalidate()
        return result
