"""Local forecast-run registry with atomic writes and explicit active revision.

Stores reproducible inputs, data/code fingerprints, outputs and validation, not pickled
Python estimators. Rollback changes the active recorded forecast; it never changes SQL.
"""
import hashlib
import json
import os
from pathlib import Path
import threading
from datetime import datetime, timezone
from uuid import uuid4

ROOT = Path(os.getenv('FORECAST_REGISTRY_DIR', Path(__file__).resolve().parents[2] / 'var' / 'registry'))
_lock = threading.RLock()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, allow_nan=False))
    temp.replace(path)


def _read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def series_key(params):
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:20]


def record(params, result):
    with _lock:
        key = series_key(params)
        revision = uuid4().hex
        sources = Path(__file__).parent.glob('*engine.py')
        code_hash = hashlib.sha256(b''.join(p.read_bytes() for p in sorted(sources))).hexdigest()
        entry = {'id':revision, 'series_key':key, 'created_at':datetime.now(timezone.utc).isoformat(),
                 'params':params, 'data_fingerprint':result.get('data_fingerprint'),
                 'code_fingerprint':code_hash, 'result':result}
        _write(ROOT / f'{revision}.json', entry)
        index = _read(ROOT/'index.json', {})
        previous = index.get(key, {})
        index[key] = {'active':revision, 'params':params, 'updated_at':entry['created_at'],
                      'data_fingerprint':entry['data_fingerprint'],
                      'revisions':(previous.get('revisions',[])+[revision])[-24:]}
        _write(ROOT/'index.json', index)
        return revision


def list_series():
    with _lock:
        return _read(ROOT/'index.json', {})


def get_revision(revision):
    if len(revision) != 32 or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('Invalid revision')
    with _lock:
        entry = _read(ROOT/f'{revision}.json')
        if entry is None:
            raise ValueError('Revision not found')
        return entry


def activate(revision):
    with _lock:
        entry = get_revision(revision)
        index = list_series()
        index[entry['series_key']]['active'] = revision
        _write(ROOT/'index.json',index)
        return {'active':revision,'series_key':entry['series_key']}


def compare(a, b):
    left, right = get_revision(a), get_revision(b)
    keys = ('dimension','dimension_value','filters','value_col','granularity','horizon')
    if any(left['params'].get(k) != right['params'].get(k) for k in keys):
        raise ValueError('Compare forecasts with matching dimensions, filters, metric, frequency, and horizon')
    return {'a':left, 'b':right, 'same_data':left['data_fingerprint']==right['data_fingerprint']}
