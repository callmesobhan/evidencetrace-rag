"""Unit tests for the M1 evaluation machinery (not the real corpus, which is fetched, not committed)."""

import importlib.util
from pathlib import Path

import pytest

from evidencetrace.evaluation.gold import GoldFinding
from evidencetrace.evaluation.m1 import cluster_bootstrap, nearmiss_scope, prf_ci, score_matching
from evidencetrace.evaluation.m1_queries import ABSENT_OUTCOME_POOL, build_queries
from evidencetrace.ingest import Document
from evidencetrace.schemas import Metric
from helpers import make_finding

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cluster_bootstrap_is_deterministic_and_brackets_the_point_estimate():
    clusters = [{"v": float(v)} for v in (0, 0, 1, 1, 1, 0, 1, 1)]

    def stat(cs):
        return sum(c["v"] for c in cs) / len(cs) if cs else None

    a = cluster_bootstrap(clusters, stat, reps=400, seed=3)
    b = cluster_bootstrap(clusters, stat, reps=400, seed=3)
    assert a == b and a[1] <= a[0] <= a[2]
    assert cluster_bootstrap([{"v": 1.0}] * 5, stat, reps=100) == (1.0, 1.0, 1.0)
    assert cluster_bootstrap([], stat, reps=10) == (None, None, None)


def _gold(gid, doc, value, ci=(-2.0, -1.0), metric=Metric.MD):
    return GoldFinding(gold_id=gid, doc_id=doc, quote="q", metric=metric, value=value, ci=ci)


def test_matching_counts_false_positives_and_misses_per_paper():
    pred = [make_finding(doc_id="a", value=-1.5, ci=(-2.0, -1.0)), make_finding(doc_id="b", value=9.0, ci=(8.0, 10.0))]
    gold = [_gold("g1", "a", -1.5), _gold("g2", "b", 1.0, ci=(0.0, 2.0))]
    clusters, mapping = score_matching(pred, gold, ["a", "b"])
    assert clusters == [{"tp": 1, "fp": 0, "fn": 0}, {"tp": 0, "fp": 1, "fn": 1}]
    assert prf_ci(clusters, reps=50)["counts"] == {"tp": 1, "fp": 1, "fn": 1}
    # CI mismatch is a miss under value+CI but a hit when the CI is ignored
    wrong_ci = [make_finding(doc_id="a", value=-1.5, ci=(-3.0, 0.0))]
    assert score_matching(wrong_ci, [_gold("g1", "a", -1.5)], ["a"])[0][0]["tp"] == 0
    assert score_matching(wrong_ci, [_gold("g1", "a", -1.5)], ["a"], ignore_ci=True)[0][0]["tp"] == 1


def test_nearmiss_scope_separates_scope_limits_from_audited_candidates():
    rows = [{"sentence": s} for s in (
        "The win ratio was 1.17 (95% CI 0.85-1.63).",
        "Canagliflozin increased hemoglobin by 7.3 g/L (95% CI 6.2, 8.5).",
        "The adjusted risk ratio was 1.4 (95% CI 1.0 to 1.9) in the subgroup.",
        "A significance level of P < 0.05 was used.",
    )]
    t = nearmiss_scope(rows)
    assert t["win_ratio"] == 1 and t["unnamed_estimate_with_ci"] == 1
    assert t["needs_manual_look_(audited)"] == 1 and t["no_effect_estimate"] == 1


def test_cross_queries_are_provably_absent_and_absent_outcomes_are_not_in_the_corpus():
    d1 = Document.from_text("p1", "Results\n\nDrug Alpha lowered blood sugar (MD -1.0, 95% CI -2.0 to -0.5).")
    d2 = Document.from_text("p2", "Results\n\nDrug Beta reduced stroke risk (HR 0.8, 95% CI 0.6 to 0.9).")
    docs = {"p1": d1, "p2": d2}
    gold = []
    for gid, doc, i, o in (("g1", "p1", "Drug Alpha", "blood sugar"), ("g2", "p2", "Drug Beta", "stroke risk")):
        g = _gold(gid, doc, -1.0)
        g.intervention, g.outcome, g.fields_annotated = i, o, True
        gold.append(g)
    corpus = d1.text + " " + d2.text + " glaucoma"  # 'glaucoma' occurs somewhere, so it must not be used as 'absent'
    qs = build_queries(gold, docs, corpus, {}, split="dev", n_absent=6)
    cross = [q for q in qs if q["kind"] == "cross"]
    assert {q["query"] for q in cross} == {
        "What is the effect of Drug Alpha on stroke risk?", "What is the effect of Drug Beta on blood sugar?",
    }
    absent = [q for q in qs if q["kind"] == "absent"]
    assert absent and all("glaucoma" not in q["query"] for q in absent)
    assert all(any(o in q["query"] for o in ABSENT_OUTCOME_POOL) for q in absent)
    assert [q["qid"] for q in qs] == sorted(q["qid"] for q in qs) and len({q["qid"] for q in qs}) == len(qs)


def test_gold_builder_selectors_refuse_to_guess():
    build = _load_script("build_gold")
    rows = [
        {"cand_id": "x1", "metric": "HR", "value": 0.8, "ci": [0.5, 0.9], "sentence": "alpha HR 0.8"},
        {"cand_id": "x2", "metric": "HR", "value": 0.8, "ci": [0.6, 0.9], "sentence": "beta HR 0.8"},
    ]
    assert build.select(rows, {"metric": "HR", "value": 0.8, "ci": [0.5, 0.9]})["cand_id"] == "x1"
    with pytest.raises(SystemExit, match="matched 2"):
        build.select(rows, {"metric": "HR", "value": 0.8})          # ambiguous
    with pytest.raises(SystemExit, match="matched 0"):
        build.select(rows, {"metric": "HR", "value": 0.7})          # nothing
