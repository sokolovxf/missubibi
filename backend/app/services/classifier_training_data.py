"""Build calendar-complete item panels and prior-only NN/TR features from the adapter."""
import hashlib
import numpy as np
import pandas as pd
from app.data.adapter import adapter
from app.services.classifier_features import tr_features, NUMERIC_FEATURES, CATEGORICAL_FEATURES

NN_NUMERIC=['list_price','prev_month_qty_1','prev_month_qty_2','prev_month_qty_3',
 'prev_avg_base_price_1','prev_num_orders_1','prev_num_customers_1',
 'prev_avg_base_price_2','prev_num_orders_2','prev_num_customers_2',
 'hist_mean_qty','hist_max_qty','hist_n_months','roll3_mean_qty','roll6_mean_qty',
 'hist_high_rate','months_since_high']
NN_CATEGORICAL=['product_category_1','product_category_2','production_status','dominant_customer_type','dominant_industry']


def data_fingerprint(data):
    cols=sorted(data.columns)
    normalized=data[cols].astype('string').fillna('')
    hashes=pd.util.hash_pandas_object(normalized,index=False).sort_values().values
    return hashlib.sha256(hashes.tobytes()).hexdigest()


def mode(series):
    counts=series.value_counts()
    return counts.index[0] if len(counts) else None


def build_panel(data=None):
    source=adapter._get_base_data() if data is None else data.copy()
    fingerprint=data_fingerprint(source)
    last=pd.Timestamp(source.month.max()).to_period('M')
    cutoff=(last+1).to_timestamp().strftime('%Y-%m-%d')
    df=source.loc[source.actual_units>0].copy()
    if 'sales_order_status' in df:
        df=df.loc[~df.sales_order_status.astype(str).str.contains('cancel',case=False)]
    df['year_month']=pd.to_datetime(df.month).dt.to_period('M')
    df['item_internal_id']=df['item'].astype(str)
    for column in ('customer_type','production_status','product_category_1','list_price','base_price','order_id'):
        if column not in df:df[column]=np.nan
    df['base_price']=pd.to_numeric(df.base_price,errors='coerce')
    df['list_price']=pd.to_numeric(df.list_price,errors='coerce')
    df['product_category_2']=df['product']
    monthly=df.groupby(['item_internal_id','year_month'],as_index=False).agg(
        quantity=('actual_units','sum'),n_orders=('order_id','nunique'),distinct_customers=('customer','nunique'),
        avg_base_price=('base_price','mean'),dominant_customer_type=('customer_type',mode),dominant_industry=('industry',mode))
    static=df.sort_values('month').drop_duplicates('item_internal_id',keep='last')[['item_internal_id','production_status','product_category_1','product_category_2','list_price']]
    parts=[]
    for item,group in monthly.groupby('item_internal_id',sort=False):
        index=pd.period_range(group.year_month.min(),last+1,freq='M')
        part=group.set_index('year_month').reindex(index).rename_axis('year_month').reset_index()
        part['item_internal_id']=item
        parts.append(part)
    if not parts:raise ValueError('No positive item sales are available for training.')
    panel=pd.concat(parts,ignore_index=True).merge(static,on='item_internal_id',validate='m:1')
    panel[['quantity','n_orders','distinct_customers']]=panel[['quantity','n_orders','distinct_customers']].fillna(0)
    return panel,fingerprint,cutoff


def nn_features(panel,threshold):
    agg=panel.sort_values(['item_internal_id','year_month']).copy()
    grp=agg.groupby('item_internal_id');key=agg.item_internal_id
    for lag in (1,2,3):agg[f'prev_month_qty_{lag}']=grp.quantity.shift(lag)
    for name,column in [('avg_base_price','avg_base_price'),('num_orders','n_orders'),('num_customers','distinct_customers')]:
        for lag in (1,2):agg[f'prev_{name}_{lag}']=grp[column].shift(lag)
    shifted=grp.quantity.shift(1)
    group=shifted.groupby(key)
    agg['hist_mean_qty']=group.expanding().mean().reset_index(level=0,drop=True)
    agg['hist_max_qty']=group.expanding().max().reset_index(level=0,drop=True)
    agg['hist_n_months']=group.expanding().count().reset_index(level=0,drop=True)
    for window in (3,6):agg[f'roll{window}_mean_qty']=group.rolling(window,min_periods=1).mean().reset_index(level=0,drop=True)
    high=(agg.quantity>threshold).astype(float)
    agg['hist_high_rate']=high.groupby(key).shift(1).groupby(key).expanding().mean().reset_index(level=0,drop=True)
    pos=grp.cumcount();last=pd.Series(np.where(high==1,pos,np.nan),index=agg.index)
    agg['months_since_high']=(pos-last.groupby(key).transform(lambda s:s.shift(1).ffill())).fillna(99)
    # Notebook's contemporaneous customer categories are shifted for production use.
    for col in ('dominant_customer_type','dominant_industry'):agg[col]=grp[col].shift(1)
    return agg.loc[agg.prev_month_qty_1.notna()].copy()
