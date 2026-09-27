# SLA Early Warning for Batch Pipelines

Predict, at the moment a batch job is released, the probability that it will finish after its SLA deadline. The alert fires with the full slack still ahead, which is exactly when an on call engineer can still act: add executors, reorder the queue, page the upstream owner or warn the downstream consumer.

Model: [julianoxdd/sla-breach-early-warning](https://huggingface.co/julianoxdd/sla-breach-early-warning)
Dataset: [julianoxdd/batch-sla-runs](https://huggingface.co/datasets/julianoxdd/batch-sla-runs)
Article in Portuguese with the full story, methodology and findings: [docs/artigo-pt-br.md](docs/artigo-pt-br.md)

## Executive summary

Most data platforms guard SLAs with a static rule of the form "upstream delay plus the job's p95 runtime exceeds the slack". On a held out month of 2,920 runs with 594 real breaches, that rule raises 1,319 alerts and only 29% of them are real, so the team learns to ignore it. A gradient boosted classifier that sees the same history plus input volume, cluster pressure and schedule context raises 388 alerts at 87% precision and catches 337 breaches before they happen. Given the same budget of 388 alerts, the rule catches 161.

The honest part: a well featured logistic regression gets most of the way there (PR AUC 0.804 against 0.819 for the boosted model). The gain of the boosted model is statistically real but small, so the value comes mostly from framing the problem as learned risk scoring on release time features, not from model complexity. Breaches caused by data skew and spot preemption stay largely unpredictable at release time (recall around 15%), which is the expected ceiling for any model that only sees information available before the run starts.

## Results on the future test split

Test split: the last 27 days of a 180 day simulation, strictly after train and validation. Operating thresholds are chosen on validation for 80% precision and then applied unchanged to test. Confidence intervals come from a bootstrap that resamples whole days, because runs on the same day share cluster state.

| Scorer | PR AUC (95% CI) | ROC AUC | Recall at 80% precision | Brier | ECE |
|---|---|---|---|---|---|
| p95 rule baseline | 0.384 (0.355 to 0.416) | 0.679 | 0.054 | n/a | n/a |
| Logistic regression | 0.804 (0.768 to 0.835) | 0.914 | 0.621 | 0.081 | 0.018 |
| Gradient boosting (published) | **0.819** (0.781 to 0.850) | **0.918** | **0.643** | **0.078** | 0.024 |

Paired day bootstrap of the PR AUC difference between gradient boosting and logistic regression: 0.002 to 0.026, so the improvement is positive but modest.

Robustness across five independently regenerated worlds (seeds 11, 23, 42, 101, 202), each retrained from scratch: gradient boosting 0.826 (std 0.007), logistic regression 0.811 (std 0.017), p95 rule 0.442 (std 0.030).

Recall of the published operating point by root cause of the breach: upstream delay 89%, volume spike 65%, cluster contention 41%, data skew 15%, spot preemption 15%.

## How the data is generated

Every row is one scheduled run of one of 60 jobs over 180 days, around 19 thousand runs. Runtime is multiplicative: base runtime times input volume raised to a job specific elasticity, times a contention factor that grows once shared cluster CPU passes 70%, times lognormal noise. Hidden events are injected with labels: volume spikes (4% of runs, 1.8x to 4x), upstream lateness (12% of runs, gamma distributed), data skew (rare, more likely on skew prone jobs and after upstream schema changes), and spot preemption (more likely under high CPU, adds rerun time). Volume follows weekly and month end seasonality and cluster load follows a daily cycle with slow capacity erosion. A run breaches when upstream delay plus queue wait plus runtime exceeds its slack. History features are trailing statistics over strictly previous runs of the same job. Details live in `slawarn/generate.py` and in the dataset card.

## Repository layout

`slawarn/generate.py` holds the seeded generator and the temporal split. `slawarn/model.py` holds feature construction, the baselines, metrics and the day block bootstrap. `train.py` regenerates the data, trains everything, evaluates, runs the robustness sweep and writes `artifacts/metrics.json` and `artifacts/model.skops`. `predict_example.py` scores the published test split with the published model. `tests/` contains the automated checks: determinism, label consistency, no temporal leakage in splits or history features, exclusion of post hoc columns, metric helpers, a performance floor against the rule baseline and a skops round trip.

## Reproduce

```bash
pip install -r requirements.txt
python -m pytest -q
python train.py --out artifacts --data data
```

Training runs on a single CPU in well under a minute.

## Use the published model

```python
import pandas as pd
import skops.io as sio
from huggingface_hub import hf_hub_download
from slawarn.model import build_features

path = hf_hub_download("julianoxdd/sla-breach-early-warning", "model.skops")
model = sio.load(path, trusted=sio.get_untrusted_types(file=path))
runs = pd.read_parquet("hf://datasets/julianoxdd/batch-sla-runs/data/test.parquet")
runs["breach_risk"] = model.predict_proba(build_features(runs))[:, 1]
```

Inspect the list returned by `get_untrusted_types` before trusting it; for this model it contains only scikit-learn gradient boosting internals.

## Limitations

The data is synthetic. The generator encodes plausible mechanisms, but the absolute numbers say nothing about your platform, and the gap between the rule and the model depends on how badly the rule's assumptions fail in your environment. History features assume the previous run of the same job has finished at release time, which is not always true for jobs that run four times a day and occasionally overrun. The model scores each run independently and does not reason about cascades across the DAG. Retrain on your own orchestrator history before using any threshold from this repository.

## License

Code and model: MIT. Dataset: CC BY 4.0.
