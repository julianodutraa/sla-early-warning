import numpy as np
import pandas as pd
import pytest

from slawarn.generate import ROOT_CAUSES, generate, temporal_split
from slawarn.model import (
    FEATURES, POST_HOC, TARGET, build_features, expected_calibration_error, heuristic_score, make_gbm,
    operating_point, recall_at_precision, threshold_for_precision,
)


@pytest.fixture(scope="module")
def small():
    return generate(n_jobs=20, n_days=60, seed=3)


def test_generation_is_deterministic():
    a = generate(n_jobs=8, n_days=20, seed=5)
    b = generate(n_jobs=8, n_days=20, seed=5)
    pd.testing.assert_frame_equal(a, b)


def test_different_seeds_differ():
    a = generate(n_jobs=8, n_days=20, seed=5)
    b = generate(n_jobs=8, n_days=20, seed=6)
    assert not a["actual_duration_min"].equals(b["actual_duration_min"])


def test_label_matches_process(small):
    expected = (small["finish_offset_min"] > small["sla_slack_min"]).astype(int)
    # Values are rounded to 4 decimals, so allow ties at the boundary.
    close = np.isclose(small["finish_offset_min"], small["sla_slack_min"], atol=1e-3)
    assert (expected[~close] == small[TARGET][~close]).all()


def test_positive_rate_is_realistic(small):
    assert 0.05 < small[TARGET].mean() < 0.4


def test_root_cause_consistent_with_label(small):
    assert set(small["root_cause"]).issubset(set(ROOT_CAUSES))
    assert (small.loc[small[TARGET] == 0, "root_cause"] == "none").all()
    assert (small.loc[small[TARGET] == 1, "root_cause"] != "none").all()


def test_temporal_split_has_no_overlap(small):
    tr, va, te = temporal_split(small)
    assert tr["scheduled_at"].max() < va["scheduled_at"].min()
    assert va["scheduled_at"].max() < te["scheduled_at"].min()
    assert len(tr) + len(va) + len(te) == len(small)


def test_history_features_do_not_use_current_run(small):
    # hist_p50 of a run must equal the rolling median of strictly previous runs of the same job.
    job = small[small["job_id"] == small["job_id"].iloc[0]].sort_values("scheduled_at").reset_index(drop=True)
    assert len(job) > 30
    for k in (20, 25, 30):
        expected = job["actual_duration_min"].iloc[k - 14 : k].median()
        assert job["hist_p50_runtime_min"].iloc[k] == pytest.approx(expected, abs=1e-3)
        assert job["hist_p50_runtime_min"].iloc[k] != pytest.approx(
            job["actual_duration_min"].iloc[k - 13 : k + 1].median(), abs=1e-6
        ) or job["actual_duration_min"].iloc[k] == job["actual_duration_min"].iloc[k - 14]


def test_features_exclude_post_hoc_columns(small):
    X = build_features(small)
    assert list(X.columns) == FEATURES
    for c in POST_HOC + [TARGET]:
        assert c not in X.columns
    assert np.isfinite(X.to_numpy()).all()


def test_heuristic_score_monotone_in_delay(small):
    row = small.iloc[[0]].copy()
    s0 = heuristic_score(row)[0]
    row["upstream_delay_min"] += 30
    assert heuristic_score(row)[0] > s0


def test_metric_helpers():
    y = np.array([0, 0, 1, 1, 1, 0])
    s = np.array([0.1, 0.2, 0.9, 0.8, 0.3, 0.4])
    assert recall_at_precision(y, s, 1.0) == pytest.approx(2 / 3)
    thr = threshold_for_precision(y, s, 1.0)
    op = operating_point(y, s, thr)
    assert op["precision"] == 1.0 and op["caught"] == 2
    assert expected_calibration_error(np.array([0, 1]), np.array([0.0, 1.0])) == 0.0


def test_gbm_beats_heuristic_on_future_split():
    from sklearn.metrics import average_precision_score

    tr, va, te = temporal_split(generate(n_jobs=30, n_days=90, seed=9))
    m = make_gbm(0, max_iter=150).fit(build_features(tr), tr[TARGET])
    ap_model = average_precision_score(te[TARGET], m.predict_proba(build_features(te))[:, 1])
    ap_rule = average_precision_score(te[TARGET], heuristic_score(te))
    assert ap_model > ap_rule + 0.1


def test_skops_roundtrip(tmp_path, small):
    import skops.io as sio

    m = make_gbm(0, max_iter=30).fit(build_features(small), small[TARGET])
    p = tmp_path / "m.skops"
    sio.dump(m, p)
    loaded = sio.load(p, trusted=sio.get_untrusted_types(file=p))
    X = build_features(small.head(50))
    np.testing.assert_allclose(loaded.predict_proba(X), m.predict_proba(X))
