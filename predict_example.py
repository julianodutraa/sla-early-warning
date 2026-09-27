"""Score upcoming runs with the published model.

    pip install huggingface_hub skops scikit-learn==1.6.1 pandas pyarrow
    python predict_example.py
"""
import pandas as pd
import skops.io as sio
from huggingface_hub import hf_hub_download

from slawarn.model import build_features

path = hf_hub_download("julianoxdd/sla-breach-early-warning", "model.skops")
model = sio.load(path, trusted=sio.get_untrusted_types(file=path))

test = pd.read_parquet("hf://datasets/julianoxdd/batch-sla-runs/data/test.parquet")
test["breach_risk"] = model.predict_proba(build_features(test))[:, 1]
print(test.sort_values("breach_risk", ascending=False)[["run_id", "job_id", "scheduled_at", "breach_risk", "sla_breach"]].head(10))
