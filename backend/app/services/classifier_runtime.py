"""Inference-only deployment boundary for September NN/TR TensorFlow exports.

Requires SavedModel + manifest + next-month feature snapshot from the matching
notebook pipeline. Never trains at import or substitutes mock probabilities.
The export must contain preprocessing in the serving graph or supply already
transformed tensors. No pickle is loaded from deployment artifacts.
"""
import json
import os
from pathlib import Path
import threading
import numpy as np

ROOT = Path(os.getenv('CLASSIFIER_MODEL_DIR', Path(__file__).resolve().parents[2] / 'var' / 'classifiers'))
_lock = threading.RLock()
_models = {}


def predict(kind, item=None):
    if kind not in ('nn','tr'):
        raise ValueError('Unknown classifier')
    current = ROOT / kind / 'current.json'
    if current.exists():
        revision=json.loads(current.read_text())['version']
        if len(revision)!=32 or any(c not in '0123456789abcdef' for c in revision):
            return {'status':'error','model':kind,'predictions':[],'message':'Invalid model revision.'}
        result=json.loads((ROOT/kind/'versions'/revision/'predictions.json').read_text())
        from app.services.classifier_training_data import data_fingerprint
        from app.data.adapter import adapter
        if result['data_fingerprint']!=data_fingerprint(adapter._get_base_data()):
            return {'status':'stale','model':kind,'predictions':[],'diagnostics':result.get('diagnostics'),
                    'message':'The dataset changed. Train the classifiers to refresh item predictions.'}
        if item:
            result['predictions']=[r for r in result['predictions'] if r['item']==item]
            if not result['predictions']:
                return {**result,'status':'insufficient_history','message':'This item has insufficient eligible history for this model (the transformer requires three prior months).'}
        return result
    folder = ROOT / kind
    required = ('manifest.json','features.json','saved_model/saved_model.pb')
    if not all((folder / p).exists() for p in required):
        return {'status':'unavailable', 'model':kind, 'predictions':[],
                'message':'Awaiting trained SavedModel, preprocessing/feature manifest, and next-month feature snapshot.'}
    try:
        manifest = json.loads((folder/'manifest.json').read_text())
        features = json.loads((folder/'features.json').read_text())
        if manifest['model'] != kind or manifest['feature_schema_version'] != 1:
            raise ValueError('Model/feature schema mismatch')
        if manifest['trained_through'] >= manifest['prediction_month']:
            raise ValueError('Prediction features must be strictly after training')
        if features['prediction_month'] != manifest['prediction_month']:
            raise ValueError('Feature snapshot period mismatch')
        from app.data.adapter import adapter
        latest = adapter._get_base_data()['month'].max()
        import pandas as pd
        expected = (pd.Timestamp(latest)+pd.offsets.MonthBegin()).strftime('%Y-%m-%d')
        if manifest['prediction_month'] != expected:
            return {'status':'stale', 'model':kind, 'predictions':[],
                    'message':'Classifier features do not match the next month of the current SQL dataset. Re-export features.'}
        rows = features['rows']
        if item:
            rows = [r for r in rows if r['item']==item]
        if not rows:
            return {'status':'unavailable', 'model':kind, 'predictions':[], 'message':'No exported features for this item.'}
        import tensorflow as tf
        with _lock:
            stamp = (folder/'saved_model/saved_model.pb').stat().st_mtime_ns
            key = (kind, stamp)
            if key not in _models:
                _models.clear()
                _models[key] = tf.saved_model.load(str(folder/'saved_model'))
            signature = _models[key].signatures[manifest.get('signature','serving_default')]
            tensors = {}
            for name, spec in manifest['inputs'].items():
                dtype = tf.string if spec['dtype']=='string' else tf.float32
                tensors[name] = tf.constant([row['inputs'][name] for row in rows], dtype=dtype)
            output = signature(**tensors)
            probs = np.asarray(output[manifest['output']]).reshape(-1)
        if len(probs)!=len(rows) or not np.isfinite(probs).all() or ((probs<0)|(probs>1)).any():
            raise ValueError('Classifier output must contain one valid probability per item')
        threshold = float(manifest.get('decision_threshold',.5))
        predictions = [{'item':r['item'],'probability':float(p),'label':bool(p>=threshold),
                        'review':bool(abs(p-threshold)<=.1)} for r,p in zip(rows,probs)]
        return {'status':'ok', 'model':kind,'prediction_month':manifest['prediction_month'],
                'target':'high_demand' if kind=='nn' else 'sold', 'threshold':threshold,
                'version':manifest['version'], 'diagnostics':manifest.get('diagnostics'), 'predictions':predictions}
    except ImportError:
        return {'status':'unavailable','model':kind,'predictions':[],
                'message':'TensorFlow inference runtime is not installed. Install the classifiers optional dependency.'}
    except Exception as exc:
        return {'status':'error','model':kind,'predictions':[], 'message':str(exc)}


def signals():
    nn, tr = predict('nn'), predict('tr')
    if nn['status']!='ok' or tr['status']!='ok':
        return {'status':'unavailable', 'message':'Both classifiers require current, validated exports.',
                'nn':nn['status'],'tr':tr['status'], 'signals':None}
    return {'status':'ok', 'prediction_month':nn['prediction_month'], 'signals':{
        'nn_high_demand_count':sum(r['probability']>.7 for r in nn['predictions']),
        'tr_sold_count':sum(r['probability']>.7 for r in tr['predictions'])},
        'usage':'Planning indicators only. Forecast regressors require historical out-of-fold signals.'}
