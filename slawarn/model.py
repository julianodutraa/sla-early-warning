"""Features, baselines, model training and evaluation for SLA breach early warning."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, precision_recall_curve, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .generate import FAMILIES

TARGET = "sla_breach"

# Columns that only exist after the run finished. They are in the dataset for
# diagnostics and must never be used as model inputs.
POST_HOC = ["queue_wait_min", "actual_duration_min", "finish_offset_min", "root_cause"]

RAW_FEATURES = [
    "scheduled_hour", "day_of_week", "is_month_end", "input_rows_log10", "volume_ratio_vs_7d",
    "upstream_delay_min", "upstream_schema_changed", "cluster_cpu_util", "queue_depth", "concurrent_jobs",
    "hist_p50_runtime_min", "hist_p95_runtime_min", "prev_run_duration_ratio", "breaches_last_7_runs",
    "sla_slack_min",
]
ENGINEERED = ["slack_over_p50", "delay_over_slack", "expected_finish_ratio", "p95_finish_ratio"]
FAMILY_COLS = [f"family_{f}" for f in FAMILIES]
FEATURES = RAW_FEATURES + ENGINEERED + FAMILY_COLS


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return the model input matrix. Uses only information available at release time."""
    X = df[RAW_FEATURES].astype(float).copy()
    slack = df["sla_slack_min"].astype(float)
    p50 = df["hist_p50_runtime_min"].astype(float)
    p95 = df["hist_p95_runtime_min"].astype(float)
    delay = df["upstream_delay_min"].astype(float)
    X["slack_over_p50"] = slack / p50
    X["delay_over_slack"] = delay / slack
    X["expected_finish_ratio"] = (delay + p50 * df["volume_ratio_vs_7d"].astype(float)) / slack
    X["p95_finish_ratio"] = (delay + p95) / slack
    for f in FAMILIES:
        X[f"family_{f}"] = (df["job_family"] == f).astype(float)
    return X[FEATURES]


def heuristic_score(df: pd.DataFrame) -> np.ndarray:
    """The rule an on call engineer would write: upstream delay plus trailing p95 runtime versus slack."""
    return ((df["upstream_delay_min"] + df["hist_p95_runtime_min"]) / df["sla_slack_min"]).to_numpy()


def make_logreg() -> object:
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))


def make_gbm(seed: int = 0, **kw) -> HistGradientBoostingClassifier:
    params = dict(
        learning_rate=0.06,
        max_iter=400,
        max_leaf_nodes=31,
        min_samples_leaf=40,
        l2_regularization=1.0,
        early_stopping=False,
        random_state=seed,
    )
    params.update(kw)
    return HistGradientBoostingClassifier(**params)


def expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    ece = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            ece += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(ece)


def recall_at_precision(y: np.ndarray, s: np.ndarray, target: float = 0.8) -> float:
    prec, rec, _ = precision_recall_curve(y, s)
    ok = prec >= target
    return float(rec[ok].max()) if ok.any() else 0.0


def threshold_for_precision(y: np.ndarray, s: np.ndarray, target: float = 0.8) -> float:
    """Smallest threshold on validation whose precision reaches the target."""
    prec, rec, thr = precision_recall_curve(y, s)
    ok = np.where(prec[:-1] >= target)[0]
    return float(thr[ok[0]]) if len(ok) else float(thr[-1])


def score_metrics(y: np.ndarray, s: np.ndarray, is_prob: bool) -> dict:
    out = {
        "pr_auc": float(average_precision_score(y, s)),
        "roc_auc": float(roc_auc_score(y, s)),
        "recall_at_p80": recall_at_precision(y, s, 0.8),
    }
    if is_prob:
        out["brier"] = float(brier_score_loss(y, s))
        out["ece"] = expected_calibration_error(y, s)
    return out


def operating_point(y: np.ndarray, s: np.ndarray, thr: float) -> dict:
    pred = s >= thr
    tp = int((pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum())
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    return {"threshold": float(thr), "precision": precision, "recall": recall, "alerts": tp + fp, "caught": tp, "missed": fn}


def day_block_bootstrap(y, s, days, fn, n_boot: int = 500, seed: int = 0):
    """Percentile CI resampling whole days, which respects the correlation of runs on the same day."""
    rng = np.random.default_rng(seed)
    uniq = np.unique(days)
    groups = {d: np.where(days == d)[0] for d in uniq}
    vals = []
    for _ in range(n_boot):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([groups[d] for d in pick])
        if y[idx].min() == y[idx].max():
            continue
        vals.append(fn(y[idx], s[idx]))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))
