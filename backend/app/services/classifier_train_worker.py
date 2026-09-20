"""Train September architectures, evaluate on held-out months, publish real item scores."""
import os
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','3')
os.environ.setdefault('TF_NUM_INTRAOP_THREADS','2')
os.environ.setdefault('TF_NUM_INTEROP_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','2')
import json
import time
from pathlib import Path
from uuid import uuid4
import numpy as np
import pandas as pd
import joblib
from sklearn.metrics import accuracy_score, balanced_accuracy_score, roc_auc_score, f1_score, confusion_matrix
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingClassifier
from app.services.classifier_training_data import build_panel,nn_features,NN_NUMERIC,NN_CATEGORICAL
from app.services.classifier_features import tr_features,NUMERIC_FEATURES,CATEGORICAL_FEATURES

ROOT=Path(__file__).resolve().parents[2]/'var'/'classifiers'


def write(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(payload,allow_nan=False));temporary.replace(path)


def progress(kind,stage,**kwargs):
    write(ROOT/'training-progress.json',{'status':'running','model':kind,'stage':stage,'pid':os.getpid(),**kwargs})


def train(kind,panel,fingerprint,prediction_month,fast=True):
    import tensorflow as tf
    from app.services.classifier_architectures import build_model
    tf.keras.utils.set_random_seed(42)
    all_months=sorted(panel.year_month.unique())[:-1]
    if len(all_months)<18:raise ValueError('Classifier training needs at least 18 observed months.')
    test_start=all_months[int(len(all_months)*.8)]
    val_start=all_months[int(len(all_months)*.65)]
    # The NN notebook trains only on selling rows. Preserve its high-demand threshold
    # definition on positive fit-period demand, then evaluate on a complete panel.
    positive=panel.loc[(panel.year_month<val_start)&(panel.quantity>0),'quantity']
    threshold=float(positive.quantile(.66)) if kind=='nn' else 0.
    progress(kind,'Building September features')
    features=nn_features(panel,threshold) if kind=='nn' else tr_features(panel.copy())
    numeric=NN_NUMERIC if kind=='nn' else NUMERIC_FEATURES
    categorical=NN_CATEGORICAL if kind=='nn' else CATEGORICAL_FEATURES
    target=(features.quantity>threshold).astype(int).to_numpy()
    fit_mask=(features.year_month<val_start).to_numpy()
    val_mask=((features.year_month>=val_start)&(features.year_month<test_start)).to_numpy()
    test_mask=((features.year_month>=test_start)&(features.year_month<=all_months[-1])).to_numpy()
    future_mask=(features.year_month==pd.Period(prediction_month,freq='M')).to_numpy()
    if any(np.unique(target[mask]).size<2 for mask in (fit_mask,val_mask,test_mask)):
        raise ValueError('Training, validation, and test windows must each contain both demand classes.')
    numbers=features[numeric].replace([np.inf,-np.inf],np.nan).apply(pd.to_numeric,errors='coerce')
    medians=numbers.loc[fit_mask].median().fillna(0)
    numbers=numbers.fillna(medians).fillna(0)
    scaler=StandardScaler().fit(numbers.loc[fit_mask])
    normalized=scaler.transform(numbers).astype('float32')
    categories={}
    for c in categorical:
        features[c]=features[c].astype('string').fillna('MISSING').astype(str)
        categories[c]=sorted(features.loc[fit_mask,c].unique().tolist())
    model=build_model(kind,len(numeric),categories)
    model.compile(optimizer=tf.keras.optimizers.AdamW(learning_rate=1e-3,weight_decay=1e-4),loss='binary_crossentropy')
    inputs={'numeric_input':normalized}
    for c in categorical:
        inputs[c+'_input' if kind=='nn' else c]=features[c].to_numpy(dtype=str).reshape(-1,1)
    y=target.astype('float32')
    balance={0:len(y[fit_mask])/(2*(y[fit_mask]==0).sum()),1:len(y[fit_mask])/(2*(y[fit_mask]==1).sum())}
    def dataset(mask,training=False):
        selected={k:tf.convert_to_tensor(v[mask]) for k,v in inputs.items()}
        weights=np.where(y[mask]>0,balance[1],balance[0]).astype('float32')
        ds=tf.data.Dataset.from_tensor_slices((selected,y[mask],weights))
        if training:ds=ds.shuffle(min(20000,int(mask.sum())),seed=42)
        opts=tf.data.Options();opts.threading.private_threadpool_size=2
        return ds.batch(512).with_options(opts).prefetch(1)
    class Reporter(tf.keras.callbacks.Callback):
        def on_epoch_end(self,epoch,logs=None):progress(kind,'Training',epoch=epoch+1,epochs=epochs,loss=float(logs['loss']))
    epochs=12 if fast else 100
    history=model.fit(dataset(fit_mask,True),validation_data=dataset(val_mask),epochs=epochs,verbose=0,
        callbacks=[tf.keras.callbacks.EarlyStopping(monitor='val_loss',patience=3 if fast else 12,restore_best_weights=True),Reporter()])
    best_epochs=int(np.argmin(history.history['val_loss']))+1
    def predict(mask):
        outputs=[]
        indices=np.flatnonzero(mask)
        for start in range(0,len(indices),1024):
            ix=indices[start:start+1024]
            batch={k:tf.convert_to_tensor(v[ix]) for k,v in inputs.items()}
            outputs.extend(np.asarray(model(batch,training=False)).reshape(-1).tolist())
        return np.asarray(outputs)
    progress(kind,'Evaluating held-out months')
    p_val,p_test=predict(val_mask),predict(test_mask)
    gbm=None
    if kind=='nn':
        # Revision 9's equal NN + gradient-boosting blend, trained on fit months only.
        categorical_numbers=np.column_stack([pd.Categorical(features[c].where(features[c].isin(categories[c])),categories=categories[c]).codes+1 for c in categorical])
        gbm_x=np.column_stack([numbers.to_numpy(),categorical_numbers])
        gbm=HistGradientBoostingClassifier(max_iter=120 if fast else 400,learning_rate=.06,
            early_stopping=False,class_weight='balanced',random_state=42)
        gbm.fit(gbm_x[fit_mask],target[fit_mask])
        p_val=.5*p_val+.5*gbm.predict_proba(gbm_x[val_mask])[:,1]
        p_test=.5*p_test+.5*gbm.predict_proba(gbm_x[test_mask])[:,1]
    grid=np.linspace(.05,.95,91)
    decision=float(grid[np.argmax([f1_score(target[val_mask],p_val>=t,zero_division=0) for t in grid])])
    labels=p_test>=decision
    persistence=(features.loc[test_mask,'prev_month_qty_1'].fillna(0).to_numpy()>threshold)
    diagnostics={'accuracy_pct':100*float(accuracy_score(target[test_mask],labels)),
        'balanced_accuracy_pct':100*float(balanced_accuracy_score(target[test_mask],labels)),
        'auc':float(roc_auc_score(target[test_mask],p_test)),'f1':float(f1_score(target[test_mask],labels)),
        'confusion_matrix':confusion_matrix(target[test_mask],labels,labels=[0,1]).tolist(),
        'persistence_accuracy_pct':100*float(accuracy_score(target[test_mask],persistence)),
        'test_rows':int(test_mask.sum()),'fit_rows':int(fit_mask.sum()),'validation_rows':int(val_mask.sum()),
        'test_start':str(test_start),'test_end':str(all_months[-1]),'validation_start':str(val_start),
        'definition':'Chronological held-out test; decision threshold selected on validation only',
        'high_demand_quantity_threshold':threshold,'epochs_selected':best_epochs,
        'profile':'quick' if fast else 'full','numeric_features':len(numeric)}
    # Store genuinely out-of-sample historical scores, with the fit cutoff, for later
    # exogenous-feature training. Never label full-data fitted scores as historical OOF.
    oof=features.loc[test_mask,['item_internal_id','year_month']].copy()
    probability_by_index=pd.Series(np.nan,index=features.index)
    probability_by_index.loc[val_mask]=p_val;probability_by_index.loc[test_mask]=p_test
    oof['probability']=probability_by_index.loc[oof.index]
    oof['trained_before']=str(test_start)
    oof['year_month']=oof.year_month.astype(str)
    progress(kind,'Refitting selected model on observed history')
    observed=~future_mask
    model.fit(dataset(observed,True),epochs=best_epochs,verbose=0)
    p_future=predict(future_mask)
    if gbm is not None:
        gbm.fit(gbm_x[observed],target[observed]);p_future=.5*p_future+.5*gbm.predict_proba(gbm_x[future_mask])[:,1]
    revision=uuid4().hex;folder=ROOT/kind/'versions'/revision;folder.mkdir(parents=True)
    @tf.function
    def serve(**values):return {'probability':model(values,training=False)}
    specs={k:tf.TensorSpec([None,*v.shape[1:]],tf.string if v.dtype.kind in ('U','O') else tf.float32,name=k) for k,v in inputs.items()}
    tf.saved_model.save(model,str(folder/'saved_model'),signatures={'serving_default':serve.get_concrete_function(**specs)})
    if gbm is not None:joblib.dump(gbm,folder/'gbm.joblib')
    write(folder/'preprocessing.json',{'numeric':numeric,'categories':categories,'median':medians.to_dict(),
         'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist(),'nn_blend_weight':.5 if kind=='nn' else None})
    predictions=[{'item':str(item),'probability':float(p),'label':bool(p>=decision),'review':bool(abs(p-decision)<.1)}
        for item,p in zip(features.loc[future_mask,'item_internal_id'],p_future)]
    predictions.sort(key=lambda r:r['probability'],reverse=True)
    result={'status':'ok','model':kind,'version':revision,'data_fingerprint':fingerprint,
        'prediction_month':prediction_month,'trained_through':str(all_months[-1]),'target':'high_demand' if kind=='nn' else 'sold',
        'threshold':decision,'diagnostics':diagnostics,'predictions':predictions,'trained_at':time.time()}
    oof.to_csv(folder/'historical_signals.csv',index=False)
    write(folder/'predictions.json',result)
    write(ROOT/kind/'current.json',{'version':revision})
    tf.keras.backend.clear_session()
    return {'model':kind,'version':revision,'accuracy_pct':diagnostics['accuracy_pct'],'items':len(predictions)}


def main():
    import sys
    fast='--full' not in sys.argv
    progress('both','Loading MySQL item history')
    panel,fingerprint,month=build_panel()
    results=[]
    for kind in ('nn','tr'):
        results.append(train(kind,panel,fingerprint,month,fast))
    write(ROOT/'training-progress.json',{'status':'done','models':results})
    print(json.dumps({'status':'ok','models':results}))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        write(ROOT/'training-progress.json',{'status':'error','message':str(exc)})
        raise
