---
license: cc-by-4.0
task_categories:
- tabular-classification
language:
- en
size_categories:
- 10K<n<100K
pretty_name: Batch SLA Runs
tags:
- data-engineering
- devops
- observability
- sla
- batch-processing
- orchestration
- synthetic
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train.parquet
  - split: validation
    path: data/validation.parquet
  - split: test
    path: data/test.parquet
---

# Batch SLA Runs

A synthetic but mechanistic dataset of 19,440 batch job runs from a simulated data platform, built to study one operational question: can we tell, at the moment a job is released, whether it will miss its SLA deadline?

Model trained on it: [julianoxdd/sla-breach-early-warning](https://huggingface.co/julianoxdd/sla-breach-early-warning)
Code, generator and tests: [github.com/julianodutraa/sla-early-warning](https://github.com/julianodutraa/sla-early-warning)

## Why it exists

SLA misses in data platforms are usually detected after the deadline, when a dashboard is already stale. Real orchestrator logs rarely leave a company, and when they do they lack labelled causes. This dataset provides a reproducible benchmark with known mechanisms and labelled root causes, so that early warning methods can be compared against simple rules under a controlled, documented process.

## Generating process

The simulation covers 60 jobs over 180 days starting on 2026-01-05, generated with a fixed seed (7). Each job has a family (ingest, transform, export, feature), a lognormal base runtime between 5 and 240 minutes, one, two or four runs per day, a volume elasticity between 0.55 and 1.05 and an SLA slack between 1.5 and 2.8 times its base runtime.

Runtime of a run is the base runtime multiplied by the input volume ratio raised to the job elasticity, by a contention factor that grows linearly once shared cluster CPU passes 70% and with queue depth, and by lognormal noise with sigma 0.12. Injected events: volume spikes on 4% of runs multiply volume by 1.8 to 4; upstream lateness on 12% of runs adds a gamma distributed delay; data skew multiplies runtime by 1.8 to 3.5, happens on 6% of runs for skew prone jobs and 0.8% otherwise, and on half the runs that follow an upstream schema change; spot preemption adds 0.5 to 1.2 base runtimes of rerun time, more often under high CPU. Seasonality: month end volume is 25% higher, Mondays 15% higher, weekends 30% lower; cluster load follows a nightly batch peak and a business hours peak, with a slow upward drift that mimics capacity erosion.

A run breaches when upstream delay plus queue wait plus runtime exceeds its slack. The overall breach rate is 19.5%.

## Schema

Features known at release time: `job_id`, `job_family`, `scheduled_at`, `scheduled_hour`, `day_of_week`, `is_month_end`, `input_rows_log10`, `volume_ratio_vs_7d`, `upstream_delay_min`, `upstream_schema_changed`, `cluster_cpu_util`, `queue_depth`, `concurrent_jobs`, `hist_p50_runtime_min` and `hist_p95_runtime_min` (trailing 14 previous runs of the same job), `prev_run_duration_ratio`, `breaches_last_7_runs`, `sla_slack_min`.

Outcome and diagnostics, known only after the run ends and never to be used as inputs: `queue_wait_min`, `actual_duration_min`, `finish_offset_min`, `root_cause` (one of none, volume_spike, contention, upstream_delay, data_skew, preemption; the dominant contributor for breached runs) and the label `sla_breach`.

## Splits

Splits are temporal, so validation and test are strictly in the future of train.

| Split | Runs | Breach rate |
|---|---|---|
| train | 13,604 | 18.4% |
| validation | 2,916 | 23.9% |
| test | 2,920 | 20.3% |

The breach rate rises over time because the generator erodes cluster capacity slowly, which makes the test split a mild distribution shift test.

## Intended use

Benchmarking SLA breach early warning, calibration and alert budget analysis; teaching temporal validation and leakage control on operational data; testing root cause attribution methods against known labels.

## Limitations

The data is synthetic and every relationship in it was written by hand. It is useful for comparing methods under known mechanisms, not for estimating how often your own jobs breach. Jobs are independent: there is no explicit DAG, so cascading failures appear only through the upstream delay variable. Root cause labels pick a single dominant cause even when several contributed. History features assume the previous run finished before the current release.

## Reproduce

```bash
git clone https://github.com/julianodutraa/sla-early-warning
cd sla-early-warning && pip install -r requirements.txt
python train.py --data data
```

## License

CC BY 4.0. Created by Juliano Dutra de Almeida.
