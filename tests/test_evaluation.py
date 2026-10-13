import json

import pytest

from evidencetrace.evaluation.gold import load_gold_findings
from evidencetrace.evaluation.metrics import aurc, prf, risk_coverage, token_f1
from evidencetrace.evaluation.runner import run_evaluation, to_markdown, write_reports
from evidencetrace.ingest import Document


def test_prf():
    assert prf(2, 0, 2)["recall"] == 0.5
    assert prf(0, 0, 0)["f1"] == 1.0
    assert prf(0, 3, 0)["precision"] == 0.0


def test_token_f1():
    assert token_f1(None, None) == 1.0
    assert token_f1("a", None) == 0.0
    assert token_f1("systolic blood pressure", "blood pressure") == pytest.approx(0.8)


def test_aurc_rewards_good_confidence_ordering():
    good = [(0.9, True), (0.8, True), (0.2, False), (0.1, False)]
    bad = [(0.9, False), (0.8, False), (0.2, True), (0.1, True)]
    # risk at coverage 1/4..4/4 is 0, 0, 1/3, 1/2 -> mean 5/24
    assert aurc(good) == pytest.approx(5 / 24)
    assert aurc(bad) > aurc(good)
    assert risk_coverage(good)[-1] == (1.0, 0.5)
    assert aurc([(0.9, True), (0.1, True)]) == 0.0
    assert aurc([]) == 0.0


def test_gold_loader_fails_loudly_on_missing_quote(tmp_path):
    p = tmp_path / "g.jsonl"
    p.write_text(json.dumps({"gold_id": "g", "doc_id": "d", "quote": "not there", "metric": "HR", "value": 1}))
    with pytest.raises(ValueError, match="quote not found"):
        load_gold_findings(p, {"d": Document.from_text("d", "Results\n\nsomething else")})


def test_smoke_evaluation_on_bundled_corpus(samples, tmp_path):
    """Regression guard for the whole stack. The numbers are NOT a claim about real papers."""
    r = run_evaluation(samples / "papers", samples / "gold")
    assert r["extraction"]["value_ci"]["f1"] == 1.0
    assert r["provenance"]["verification_pass_rate"] == 1.0
    assert r["abstention"]["false_answer_rate"] == 0.0
    assert r["abstention"]["over_abstention_rate"] == 0.0
    assert r["conflicts"]["overall"]["f1"] == 1.0
    assert r["abstention"]["status_accuracy"] == 1.0

    jp, mp = write_reports(r, tmp_path)
    assert json.loads(jp.read_text())["sizes"]["queries"] == 9
    assert "| abstention |" in to_markdown(r) and mp.exists()
