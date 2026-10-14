"""Corrected accuracy from human verdicts: the arithmetic, on a case small enough to check by hand."""

from __future__ import annotations

import json

import pytest

from evidencetrace.evaluation.adjudication import POLICIES, adjudicate, item_id, load_decisions, tally

# paper A: 10 gold, 8 predicted, 7 matched.  paper B: 4 gold, 5 predicted, 4 matched.
PER_PAPER = [{"pmcid": "A", "gold": 10, "pred": 8, "tp": 7}, {"pmcid": "B", "gold": 4, "pred": 5, "tp": 4}]
DIS = [
    {"type": "system_only", "pmcid": "A", "metric": "HR", "value": 0.8, "ci": [0.7, 0.9]},  # system extracted, annotator did not
    {"type": "annotator_only", "pmcid": "A", "metric": "OR", "value": 1.2, "ci": None},
    {"type": "annotator_only", "pmcid": "A", "metric": "MD", "value": -2.0, "ci": [-3, -1]},
    {"type": "annotator_only", "pmcid": "A", "metric": "RR", "value": 0.5, "ci": None},
    {"type": "system_only", "pmcid": "B", "metric": "SMD", "value": 0.3, "ci": None},
]


def _dec(by_index: dict[int, str]) -> dict[str, dict]:
    return {item_id(DIS[i]): {"id": item_id(DIS[i]), "decision": v} for i, v in by_index.items()}


def _counts(clusters):
    return {k: sum(c[k] for c in clusters) for k in ("tp", "fp", "fn")}


def test_item_ids_are_stable_and_distinct():
    assert len({item_id(r) for r in DIS}) == len(DIS)
    assert item_id(DIS[0]) == item_id(dict(DIS[0]))


def test_system_was_right_and_annotator_over_included():
    # item0: system_only in scope -> TP (A: tp 8, gold 11); item1: annotator_only not in scope -> gold shrinks (A gold 10);
    # item4: system_only not in scope -> stays a false positive
    cl = adjudicate(PER_PAPER, DIS, _dec({0: "yes", 1: "no", 4: "no"}), "exclude")
    assert cl[0] == {"tp": 8, "fp": 0, "fn": 2}  # A: gold 10 +1 -1 = 10, pred 8, tp 8
    assert cl[1] == {"tp": 4, "fp": 1, "fn": 0}  # B untouched


def test_genuine_miss_and_genuine_false_positive_change_nothing():
    cl = adjudicate(PER_PAPER, DIS, _dec({1: "yes", 4: "no"}), "exclude")
    assert _counts(cl) == {"tp": 11, "fp": 2, "fn": 3}  # same as as-scored: 7+4 tp, (1+1) fp, (3+0) fn


def test_undecided_items_keep_their_status():
    assert _counts(adjudicate(PER_PAPER, DIS, {}, "exclude")) == {"tp": 11, "fp": 2, "fn": 3}


def test_unsure_is_bounded_by_the_three_policies():
    dec = _dec({0: "unk", 1: "unk"})
    excl = _counts(adjudicate(PER_PAPER, DIS, dec, "exclude"))       # system_only dropped from preds, annotator_only from gold
    fav = _counts(adjudicate(PER_PAPER, DIS, dec, "favour_system"))   # system_only counts as TP, annotator_only removed
    against = _counts(adjudicate(PER_PAPER, DIS, dec, "against_system"))
    assert excl == {"tp": 11, "fp": 1, "fn": 2}
    assert fav == {"tp": 12, "fp": 1, "fn": 2}
    assert against == {"tp": 11, "fp": 2, "fn": 3}
    f1 = lambda c: 2 * c["tp"] / (2 * c["tp"] + c["fp"] + c["fn"])  # noqa: E731
    assert f1(against) <= f1(excl) <= f1(fav)


def test_tally_counts_verdicts():
    t = tally(DIS, _dec({0: "yes", 1: "no", 2: "unk"}))
    assert t["system_only"] == {"items": 2, "decided": 1, "in_scope": 1, "not_in_scope": 0, "unsure": 0}
    assert t["annotator_only"] == {"items": 3, "decided": 2, "in_scope": 0, "not_in_scope": 1, "unsure": 1}


def test_unknown_policy_and_decision_are_errors(tmp_path):
    with pytest.raises(ValueError):
        adjudicate(PER_PAPER, DIS, {}, "optimistic")
    f = tmp_path / "d.jsonl"
    f.write_text(json.dumps({"id": "x", "decision": "maybe"}) + "\n")
    with pytest.raises(ValueError):
        load_decisions(f)
    assert POLICIES == ("exclude", "favour_system", "against_system")


def test_review_page_context_uses_the_whole_quote_not_its_first_words():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("make_adjudication_page", Path(__file__).resolve().parents[1] / "scripts" / "make_adjudication_page.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from evidencetrace.ingest.document import Document

    doc = Document.from_text("d", "In the mediation model the OR was 0.97 (95% CI 0.64, 1.46) for a sibling with diabetes. "
                                 "Per SD of education the OR was 0.97 (95% CI 0.96, 0.98) for a first-degree relative.")
    _, before, after = mod._context(doc, "the OR was 0.97 (95% CI 0.96, 0.98)", 0.97)
    assert "first-degree" not in before + after and before == "In the mediation model the OR was 0.97 (95% CI 0.64, 1.46) for a sibling with diabetes."
    # whole-quote match wins even when an earlier sentence starts with the same words
    _, before2, _ = mod._context(doc, "the OR was 0.97 (95% CI 0.64, 1.46)", 0.97)
    assert before2 == ""
