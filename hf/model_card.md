---
license: mit
library_name: sklearn
pipeline_tag: tabular-classification
tags:
- tabular-classification
- sklearn
- skops
- data-engineering
- devops
- observability
- sla
- batch-processing
datasets:
- julianoxdd/batch-sla-runs
metrics:
- average_precision
- roc_auc
- brier_score
model-index:
- name: sla-breach-early-warning
  results:
  - task:
      type: tabular-classification
      name: SLA breach early warning
    dataset:
      type: julianoxdd/batch-sla-runs
      name: Batch SLA Runs
      split: test
    metrics:
    - type: average_precision
      value: 0.819
      name: PR AUC
    - type: roc_auc
      value: 0.918
      name: ROC AUC
    - type: brier_score
      value: 0.078
      name: Brier score
    - type: recall
      value: 0.643
      name: Recall at 80% precision
---

# SLA Breach Early Warning

A small gradient boosted classifier that estimates, at the moment a batch job is released, the probability that it will finish after its SLA deadline. It uses only information the orchestrator has before the run starts, so the alert arrives with the whole slack still available for action.

Dataset: [julianoxdd/batch-sla-runs](https://huggingface.co/datasets/julianoxdd/batch-sla-runs)
Code, training, evaluation and tests: [github.com/julianodutraa/sla-early-warning](https://github.com/julianodutraa/sla-early-warning)

## Executive summary

The usual guard in data platforms is a static rule: alert when upstream delay plus the job's trailing p95 runtime exceeds the slack. On a held out month with 594 breaches, that rule raises 1,319 alerts at 29% precision. This model raises 388 alerts at 87% precision and catches 337 breaches ahead of time. With the same budget of 388 alerts, the rule catches 161. A logistic regression on the same features is close behind, so most of the value comes from learned risk scoring on release time features rather than from model capacity.

## Model details

Scikit-learn 1.6.1 `HistGradientBoostingClassifier` with learning rate 0.06, 400 iterations, 31 leaves, at least 40 samples per leaf and L2 regularisation 1.0. Input is 27 numeric features: 15 raw release time signals from the dataset, 4 engineered ratios (slack over trailing p50, upstream delay over slack, expected finish over slack using p50 times the volume ratio, and p95 finish over slack) and a one hot encoding of the job family. Serialised with skops; no pickle file is shipped. The model file is about 3 MB and scores thousands of runs per second on one CPU.

## Evaluation

Temporal split: trained on the first 70% of the timeline, threshold chosen on the next 15% for 80% precision, evaluated once on the last 15% (27 days, 2,920 runs). Confidence intervals come from a bootstrap that resamples whole days.

| Scorer | PR AUC (95% CI) | ROC AUC | Recall at 80% precision | Brier | ECE |
|---|---|---|---|---|---|
| p95 rule baseline | 0.384 (0.355 to 0.416) | 0.679 | 0.054 | n/a | n/a |
| Logistic regression baseline | 0.804 (0.768 to 0.835) | 0.914 | 0.621 | 0.081 | 0.018 |
| This model | 0.819 (0.781 to 0.850) | 0.918 | 0.643 | 0.078 | 0.024 |

The paired day bootstrap interval for the PR AUC gain over logistic regression is 0.002 to 0.026: positive, but small. Across five independently regenerated datasets the model scores 0.826 PR AUC with standard deviation 0.007, against 0.811 (0.017) for logistic regression and 0.442 (0.030) for the rule. At the chosen operating point (threshold 0.664) test precision is 86.9% and recall 56.7%.

Recall by root cause at that operating point: upstream delay 89%, volume spike 65%, cluster contention 41%, data skew 15%, spot preemption 15%. The last two are mostly invisible before the run starts, so a low recall there is the expected ceiling, not a defect to tune away.

## How to use

```python
import pandas as pd
import skops.io as sio
from huggingface_hub import hf_hub_download

FAMILIES = ["ingest", "transform", "export", "feature"]
RAW = ["scheduled_hour", "day_of_week", "is_month_end", "input_rows_log10", "volume_ratio_vs_7d",
       "upstream_delay_min", "upstream_schema_changed", "cluster_cpu_util", "queue_depth", "concurrent_jobs",
       "hist_p50_runtime_min", "hist_p95_runtime_min", "prev_run_duration_ratio", "breaches_last_7_runs",
       "sla_slack_min"]

def build_features(df):
    X = df[RAW].astype(float).copy()
    X["slack_over_p50"] = df.sla_slack_min / df.hist_p50_runtime_min
    X["delay_over_slack"] = df.upstream_delay_min / df.sla_slack_min
    X["expected_finish_ratio"] = (df.upstream_delay_min + df.hist_p50_runtime_min * df.volume_ratio_vs_7d) / df.sla_slack_min
    X["p95_finish_ratio"] = (df.upstream_delay_min + df.hist_p95_runtime_min) / df.sla_slack_min
    for f in FAMILIES:
        X[f"family_{f}"] = (df.job_family == f).astype(float)
    return X

path = hf_hub_download("julianoxdd/sla-breach-early-warning", "model.skops")
print(sio.get_untrusted_types(file=path))  # review before trusting
model = sio.load(path, trusted=sio.get_untrusted_types(file=path))

runs = pd.read_parquet("hf://datasets/julianoxdd/batch-sla-runs/data/test.parquet")
runs["breach_risk"] = model.predict_proba(build_features(runs))[:, 1]
alerts = runs[runs.breach_risk >= 0.664]
print(len(alerts), alerts.sla_breach.mean())
```

Requires `scikit-learn==1.6.1`, `skops`, `pandas`, `pyarrow` and `huggingface_hub`.

## Limitations

Trained only on synthetic data, so the threshold and the absolute metrics do not transfer to a real platform; retrain on your own orchestrator history. The model scores runs independently and does not model cascades across a DAG. It assumes the previous run of the same job has finished when history features are computed. Because cluster capacity drifts in the simulation, the probability calibration will degrade over time without retraining, and the same is true in production.

## Intended use

Decision support for on call data engineers and platform teams: ranking at risk runs, sizing an alert budget, and as a reference implementation of temporal validation and leakage control on operational data. Not intended for automated remediation without a human or a policy layer in between.

## Author

Juliano Dutra de Almeida. MIT license.
