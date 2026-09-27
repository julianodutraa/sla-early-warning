"""Generate the dataset, train the baselines and the model, evaluate on the held out future split.

Usage:
    python train.py --out artifacts --data data
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from slawarn.generate import generate, temporal_split
from slawarn.model import (
    FEATURES, TARGET, build_features, day_block_bootstrap, heuristic_score, make_gbm, make_logreg,
    operating_point, score_metrics, threshold_for_precision,
)

DATA_SEED = 7
ROBUSTNESS_SEEDS = [11, 23, 42, 101, 202]


def fit_and_score(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame, seed: int = 0) -> dict:
    Xtr, Xva, Xte = build_features(train), build_features(val), build_features(test)
    ytr, yva, yte = train[TARGET].to_numpy(), val[TARGET].to_numpy(), test[TARGET].to_numpy()

    gbm = make_gbm(seed).fit(Xtr, ytr)
    lr = make_logreg().fit(Xtr, ytr)

    scores_val = {
        "heuristic": heuristic_score(val),
        "logreg": lr.predict_proba(Xva)[:, 1],
        "gbm": gbm.predict_proba(Xva)[:, 1],
    }
    scores_test = {
        "heuristic": heuristic_score(test),
        "logreg": lr.predict_proba(Xte)[:, 1],
        "gbm": gbm.predict_proba(Xte)[:, 1],
    }
    res = {}
    for name in scores_test:
        m = score_metrics(yte, scores_test[name], is_prob=name != "heuristic")
        thr = threshold_for_precision(yva, scores_val[name], 0.8)
        m["operating_point_test"] = operating_point(yte, scores_test[name], thr)
        # The literal rule "alert when delay plus p95 exceeds slack" at threshold 1.0.
        if name == "heuristic":
            m["rule_at_1"] = operating_point(yte, scores_test[name], 1.0)
        res[name] = m
    return {"metrics": res, "gbm": gbm, "scores_test": scores_test, "y_test": yte}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="artifacts")
    ap.add_argument("--data", default="data")
    ap.add_argument("--n-boot", type=int, default=500)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.data, exist_ok=True)

    df = generate(seed=DATA_SEED)
    train, val, test = temporal_split(df)
    for name, part in [("train", train), ("validation", val), ("test", test)]:
        part.to_parquet(os.path.join(args.data, f"{name}.parquet"), index=False)

    main_run = fit_and_score(train, val, test)
    y = main_run["y_test"]
    days = test["scheduled_at"].dt.normalize().to_numpy()
    ci = {}
    for name, s in main_run["scores_test"].items():
        ci[name] = day_block_bootstrap(y, s, days, average_precision_score, n_boot=args.n_boot)
    diff_ci = day_block_bootstrap(
        y,
        np.stack([main_run["scores_test"]["gbm"], main_run["scores_test"]["logreg"]], axis=1),
        days,
        lambda yy, ss: average_precision_score(yy, ss[:, 0]) - average_precision_score(yy, ss[:, 1]),
        n_boot=args.n_boot,
    )

    # Robustness: regenerate the world with other seeds and retrain from scratch.
    robust = {k: [] for k in ["heuristic", "logreg", "gbm"]}
    for s in ROBUSTNESS_SEEDS:
        tr, va, te = temporal_split(generate(seed=s))
        r = fit_and_score(tr, va, te, seed=s)
        for k in robust:
            robust[k].append(r["metrics"][k]["pr_auc"])

    # Per root cause recall at the gbm operating point, diagnostics only.
    thr = main_run["metrics"]["gbm"]["operating_point_test"]["threshold"]
    alert = main_run["scores_test"]["gbm"] >= thr
    by_cause = {}
    for c, g in test[test[TARGET] == 1].groupby("root_cause"):
        by_cause[c] = {"n": int(len(g)), "recall": float(alert[g.index].mean())}

    # Equal alert budget comparison: give every scorer as many alerts as the gbm raised.
    budget = main_run["metrics"]["gbm"]["operating_point_test"]["alerts"]
    equal_budget = {}
    for name, s in main_run["scores_test"].items():
        top = np.argsort(-s, kind="stable")[:budget]
        caught = int(y[top].sum())
        equal_budget[name] = {"alerts": int(budget), "caught": caught, "precision": caught / max(budget, 1), "recall": caught / int(y.sum())}

    import skops.io as sio
    sio.dump(main_run["gbm"], os.path.join(args.out, "model.skops"))

    summary = {
        "data_seed": DATA_SEED,
        "rows": {"train": len(train), "validation": len(val), "test": len(test)},
        "positive_rate": {"train": float(train[TARGET].mean()), "validation": float(val[TARGET].mean()), "test": float(test[TARGET].mean())},
        "features": FEATURES,
        "test_metrics": main_run["metrics"],
        "pr_auc_ci95_day_bootstrap": ci,
        "gbm_minus_logreg_pr_auc_ci95": diff_ci,
        "robustness_pr_auc": {k: {"values": v, "mean": float(np.mean(v)), "std": float(np.std(v, ddof=1))} for k, v in robust.items()},
        "gbm_recall_by_root_cause": by_cause,
        "equal_alert_budget_test": equal_budget,
        "test_days": int(len(np.unique(days))),
    }
    with open(os.path.join(args.out, "metrics.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps({k: summary[k] for k in ["test_metrics", "pr_auc_ci95_day_bootstrap", "gbm_minus_logreg_pr_auc_ci95", "robustness_pr_auc", "gbm_recall_by_root_cause", "equal_alert_budget_test", "test_days", "rows", "positive_rate"]}, indent=1))


if __name__ == "__main__":
    main()
