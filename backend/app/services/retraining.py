"""Refresh recorded forecast configurations on new data or a new UTC month.

A single application lifespan worker checks hourly. It only refreshes configurations
already run by a planner; no exhaustive SKU/customer Cartesian-product training.
"""
import hashlib
import logging
import threading
from datetime import datetime, timezone
from app.data.adapter import adapter
from app.services import model_registry

_stop = threading.Event()
_thread = None
_log = logging.getLogger(__name__)


def refresh_once():
    from app.services.forecast_service import forecast
    current_month = datetime.now(timezone.utc).strftime('%Y-%m')
    from app.services.classifier_runtime import predict
    from app.services.classifier_jobs import start_training
    try:
        if any(predict(kind)['status']=='stale' for kind in ('nn','tr')):
            start_training(fast=True)
    except Exception:
        _log.exception('Classifier refresh check failed')
    for entry in model_registry.list_series().values():
        if _stop.is_set():
            return
        params = entry['params']
        try:
            monthly = adapter.get_series(params['dimension'], params.get('dimension_value'),
                params['value_col'], filters=params.get('filters'))
            fingerprint = hashlib.sha256(monthly.to_csv(index=False).encode()).hexdigest()
            if fingerprint == entry['data_fingerprint'] and entry['updated_at'].startswith(current_month):
                continue
            result = forecast(params, force=True)
            _log.info('Scheduled refresh %s: %s', entry['active'], result['status'])
        except Exception:
            _log.exception('Scheduled refresh failed for %s', entry['active'])


def _loop():
    while not _stop.wait(3600):
        refresh_once()


def start():
    global _thread
    _stop.clear()
    _thread = threading.Thread(target=_loop, name='forecast-refresh', daemon=True)
    _thread.start()


def stop():
    _stop.set()


if __name__ == '__main__':
    refresh_once()
