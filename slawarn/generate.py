"""Synthetic generator for batch job runs with SLA deadlines.

Every row is one scheduled run of a batch job, described only by what an
orchestrator knows at the moment the run is released: its schedule, its input
volume, the state of the shared cluster, how late its upstream dependencies
were, and trailing history of the same job. The label says whether the run
finished after its SLA deadline.

The process is fully seeded, so the same seed always produces the same data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FAMILIES = ["ingest", "transform", "export", "feature"]
ROOT_CAUSES = [
    "none",
    "volume_spike",
    "contention",
    "upstream_delay",
    "data_skew",
    "preemption",
]


def _job_catalog(rng: np.random.Generator, n_jobs: int) -> pd.DataFrame:
    fam = rng.choice(FAMILIES, size=n_jobs, p=[0.3, 0.35, 0.15, 0.2])
    base = rng.lognormal(mean=np.log(35), sigma=0.6, size=n_jobs)
    base = np.clip(base, 5, 240)
    runs_per_day = rng.choice([1, 2, 4], size=n_jobs, p=[0.55, 0.3, 0.15])
    # SLA slack: the time budget between release and deadline, sized by the
    # team at onboarding as a multiple of the typical runtime.
    slack_mult = rng.uniform(1.5, 2.8, size=n_jobs)
    vol_elasticity = rng.uniform(0.55, 1.05, size=n_jobs)
    skew_prone = rng.random(n_jobs) < 0.2
    return pd.DataFrame(
        {
            "job_id": [f"job_{i:03d}" for i in range(n_jobs)],
            "job_family": fam,
            "base_runtime_min": base,
            "runs_per_day": runs_per_day,
            "slack_mult": slack_mult,
            "vol_elasticity": vol_elasticity,
            "skew_prone": skew_prone,
            "base_rows_log10": rng.uniform(5.0, 8.5, size=n_jobs),
        }
    )


def _cluster_load(hour: np.ndarray, dow: np.ndarray, day: np.ndarray, rng) -> np.ndarray:
    """Shared cluster CPU utilisation with a daily cycle, weekday effect and slow drift."""
    daily = 0.18 * np.exp(-((hour - 2.0) % 24 - 4.0) ** 2 / 8.0)  # nightly batch window
    daily += 0.12 * np.exp(-((hour - 14.0) ** 2) / 10.0)  # business hours
    weekday = np.where(dow < 5, 0.06, -0.08)
    drift = 0.05 * np.sin(2 * np.pi * day / 60.0) + 0.0006 * day  # capacity erodes
    return np.clip(0.42 + daily + weekday + drift + rng.normal(0, 0.07, size=hour.shape), 0.05, 0.99)


def generate(n_jobs: int = 60, n_days: int = 180, seed: int = 7, start: str = "2026-01-05") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    jobs = _job_catalog(rng, n_jobs)
    t0 = pd.Timestamp(start)

    rows = []
    for j in jobs.itertuples(index=False):
        k = int(j.runs_per_day)
        first_hour = rng.integers(0, 24 // k)
        hours = [(first_hour + i * (24 // k)) % 24 for i in range(k)]
        for d in range(n_days):
            for h in hours:
                rows.append((j.job_id, d, h))
    df = pd.DataFrame(rows, columns=["job_id", "day", "scheduled_hour"])
    df = df.merge(jobs, on="job_id", how="left")
    n = len(df)

    ts = t0 + pd.to_timedelta(df["day"], unit="D") + pd.to_timedelta(df["scheduled_hour"], unit="h")
    df["scheduled_at"] = ts
    df["day_of_week"] = ts.dt.dayofweek.astype(int)
    dom = ts.dt.day
    dim = ts.dt.days_in_month
    df["is_month_end"] = ((dim - dom) < 2).astype(int)

    # Input volume: weekly and month end seasonality, heavy tailed spikes.
    season = 1.0 + 0.25 * df["is_month_end"] + np.where(df["day_of_week"] == 0, 0.15, 0.0)
    season = season * np.where(df["day_of_week"] >= 5, 0.7, 1.0)
    spike = rng.random(n) < 0.04
    vol_ratio = season * rng.lognormal(0, 0.18, size=n) * np.where(spike, rng.uniform(1.8, 4.0, n), 1.0)
    df["volume_ratio_vs_7d"] = vol_ratio
    df["input_rows_log10"] = df["base_rows_log10"] + np.log10(vol_ratio)

    # Upstream lateness: mostly zero, sometimes long.
    late = rng.random(n) < 0.12
    df["upstream_delay_min"] = np.where(late, rng.gamma(1.4, 22.0, size=n), 0.0)

    # Shared cluster state at release time.
    cpu = _cluster_load(df["scheduled_hour"].to_numpy(), df["day_of_week"].to_numpy(), df["day"].to_numpy(), rng)
    df["cluster_cpu_util"] = cpu
    df["queue_depth"] = rng.poisson(1.0 + 14.0 * np.maximum(cpu - 0.55, 0))
    df["concurrent_jobs"] = rng.poisson(4 + 10 * cpu)
    df["upstream_schema_changed"] = (rng.random(n) < 0.015).astype(int)

    # Hidden events.
    skew = (rng.random(n) < np.where(df["skew_prone"], 0.06, 0.008)) | (
        (df["upstream_schema_changed"] == 1) & (rng.random(n) < 0.5)
    )
    preempt = rng.random(n) < 0.015 + 0.02 * np.maximum(cpu - 0.8, 0) / 0.2

    contention = 1.0 + 1.6 * np.maximum(cpu - 0.7, 0) / 0.3 + 0.03 * df["queue_depth"]
    dur = (
        df["base_runtime_min"]
        * vol_ratio ** df["vol_elasticity"]
        * contention
        * np.where(skew, rng.uniform(1.8, 3.5, n), 1.0)
        * rng.lognormal(0, 0.12, size=n)
    )
    dur = dur + np.where(preempt, df["base_runtime_min"] * rng.uniform(0.5, 1.2, n), 0.0)
    queue_wait = rng.gamma(1.2, 1.0 + 3.5 * df["queue_depth"])
    df["actual_duration_min"] = dur
    df["queue_wait_min"] = queue_wait

    df["sla_slack_min"] = df["base_runtime_min"] * df["slack_mult"]
    finish_offset = df["upstream_delay_min"] + queue_wait + dur
    df["finish_offset_min"] = finish_offset
    df["sla_breach"] = (finish_offset > df["sla_slack_min"]).astype(int)
    df["_skew"] = np.asarray(skew, dtype=bool)
    df["_preempt"] = np.asarray(preempt, dtype=bool)
    df["_contention"] = np.asarray(contention, dtype=float)

    # Trailing history features, computed strictly from past runs of the same job.
    df = df.sort_values(["job_id", "scheduled_at"]).reset_index(drop=True)
    g = df.groupby("job_id")["actual_duration_min"]
    df["hist_p50_runtime_min"] = g.transform(lambda s: s.shift(1).rolling(14, min_periods=3).median())
    df["hist_p95_runtime_min"] = g.transform(lambda s: s.shift(1).rolling(14, min_periods=3).quantile(0.95))
    df["prev_run_duration_ratio"] = g.transform(lambda s: s.shift(1)) / df["hist_p50_runtime_min"]
    df["breaches_last_7_runs"] = df.groupby("job_id")["sla_breach"].transform(
        lambda s: s.shift(1).rolling(7, min_periods=1).sum()
    )
    df = df.dropna(subset=["hist_p50_runtime_min", "hist_p95_runtime_min", "prev_run_duration_ratio"])

    # Root cause label: dominant contributor for breached runs, for diagnostics only.
    cause = np.full(len(df), "none", dtype=object)
    b = df["sla_breach"].to_numpy() == 1
    cand = np.stack(
        [
            np.log(df["volume_ratio_vs_7d"].clip(lower=1)).to_numpy(),
            np.log(df["_contention"]).to_numpy(),
            (df["upstream_delay_min"] / df["sla_slack_min"]).to_numpy(),
            np.where(df["_skew"], 0.9, 0.0),
            np.where(df["_preempt"], 0.8, 0.0),
        ],
        axis=1,
    )
    cause[b] = np.array(ROOT_CAUSES[1:])[cand[b].argmax(axis=1)]
    df["root_cause"] = cause

    df = df.sort_values(["scheduled_at", "job_id"]).reset_index(drop=True)
    df.insert(0, "run_id", [f"run_{i:06d}" for i in range(len(df))])
    cols = [
        "run_id", "job_id", "job_family", "scheduled_at", "scheduled_hour", "day_of_week", "is_month_end",
        "input_rows_log10", "volume_ratio_vs_7d", "upstream_delay_min", "upstream_schema_changed",
        "cluster_cpu_util", "queue_depth", "concurrent_jobs",
        "hist_p50_runtime_min", "hist_p95_runtime_min", "prev_run_duration_ratio", "breaches_last_7_runs",
        "sla_slack_min", "queue_wait_min", "actual_duration_min", "finish_offset_min", "root_cause", "sla_breach",
    ]
    df = df[cols]
    num = df.select_dtypes("float").columns
    df[num] = df[num].round(4)
    return df


def temporal_split(df: pd.DataFrame, val_frac: float = 0.15, test_frac: float = 0.15):
    """Split by time so that validation and test are strictly in the future of train."""
    t = df["scheduled_at"].sort_values().to_numpy()
    q1 = t[int(len(t) * (1 - val_frac - test_frac))]
    q2 = t[int(len(t) * (1 - test_frac))]
    train = df[df["scheduled_at"] < q1]
    val = df[(df["scheduled_at"] >= q1) & (df["scheduled_at"] < q2)]
    test = df[df["scheduled_at"] >= q2]
    return train.reset_index(drop=True), val.reset_index(drop=True), test.reset_index(drop=True)
