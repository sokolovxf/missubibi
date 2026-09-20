"""September Tabular Transformer rev8 inference adapter."""
from app.services.classifier_runtime import predict


def predict_items(item=None):
    return predict('tr', item)
