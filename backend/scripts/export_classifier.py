"""Call export_classifier() from a completed September training notebook.

Exports an inference graph and its exact next-month transformed inputs together.
Training, scalers, category vocabularies, and leakage-safe feature construction remain
owned by the notebook; this helper does not guess missing feature values.
"""
import json
from pathlib import Path


def export_classifier(model, *, kind, version, trained_through, prediction_month,
                      item_codes, inputs, decision_threshold, diagnostics, output_dir):
    import tensorflow as tf
    if kind not in ('nn','tr'):
        raise ValueError('kind must be nn or tr')
    if trained_through >= prediction_month:
        raise ValueError('Prediction month must follow training')
    if not item_codes or len(set(item_codes)) != len(item_codes):
        raise ValueError('Supply exactly one next-month feature row per item')
    tensors={name:tf.convert_to_tensor(value) for name,value in inputs.items()}
    tensors={name:(t if t.dtype==tf.string else tf.cast(t,tf.float32)) for name,t in tensors.items()}
    if any(len(t)!=len(item_codes) for t in tensors.values()):
        raise ValueError('Feature lengths do not match item codes')
    specs={name:tf.TensorSpec([None,*tensor.shape[1:]],tensor.dtype,name=name)
           for name,tensor in tensors.items()}
    # The input dict names must match the Keras model input names.
    @tf.function(input_signature=[specs])
    def serving(features):
        return {'probability':model(features,training=False)}
    folder=Path(output_dir)/kind
    folder.mkdir(parents=True,exist_ok=True)
    tf.saved_model.save(model,str(folder/'saved_model'),signatures={'serving_default':serving})
    manifest={'model':kind,'version':version,'feature_schema_version':1,
              'trained_through':trained_through,'prediction_month':prediction_month,
              'signature':'serving_default','output':'probability',
              'decision_threshold':decision_threshold,'diagnostics':diagnostics,
              'inputs':{n:{'dtype':'string' if t.dtype==tf.string else 'float32'} for n,t in tensors.items()}}
    def serial(value):
        if hasattr(value,'tolist'):return serial(value.tolist())
        if isinstance(value,bytes):return value.decode('utf-8')
        if isinstance(value,list):return [serial(v) for v in value]
        return value
    rows=[{'item':item,'inputs':{n:serial(t[i].numpy()) for n,t in tensors.items()}}
          for i,item in enumerate(item_codes)]
    (folder/'manifest.json').write_text(json.dumps(manifest,allow_nan=False))
    (folder/'features.json').write_text(json.dumps({'prediction_month':prediction_month,'rows':rows},allow_nan=False))
