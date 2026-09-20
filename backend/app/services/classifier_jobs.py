"""Single background training job with durable progress and process isolation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
ROOT=Path(__file__).resolve().parents[2]/'var'/'classifiers'
_lock=threading.Lock()
_running=False


def training_status():
    file=ROOT/'training-progress.json'
    return json.loads(file.read_text()) if file.exists() else {'status':'idle'}


def _run(fast):
    global _running
    try:
        with (ROOT/'training.log').open('w') as log:
            result=subprocess.run([sys.executable,'-m','app.services.classifier_train_worker',*([] if fast else ['--full'])],
                cwd=Path(__file__).resolve().parents[2],stdout=log,stderr=log,timeout=7200)
        if result.returncode and training_status().get('status')!='error':
            _write({'status':'error','message':'Training worker stopped. See the classifier training log.'})
    except Exception as exc:_write({'status':'error','message':str(exc)})
    finally:
        with _lock:_running=False


def _write(payload):
    temporary=ROOT/'training-progress.tmp';temporary.write_text(json.dumps(payload));temporary.replace(ROOT/'training-progress.json')


def start_training(fast=True):
    global _running
    with _lock:
        if _running:return training_status()
        previous=training_status()
        if previous.get('status')=='running' and previous.get('pid'):
            try:
                os.kill(previous['pid'],0)
                return previous
            except ProcessLookupError:
                pass
        ROOT.mkdir(parents=True,exist_ok=True)
        _running=True;_write({'status':'running','stage':'Preparing training job'})
        threading.Thread(target=_run,args=(fast,),daemon=True).start()
    return training_status()
