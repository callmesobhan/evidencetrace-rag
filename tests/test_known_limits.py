"""Known limitations, written as strict xfail tests (docs/known-issues.md).

Each documents behaviour that is WRONG today. ``strict=True`` means the suite fails the day one of them starts passing,
which is the signal to delete the xfail marker and the matching entry in docs/known-issues.md.
"""

from __future__ import annotations

import pytest

from evidencetrace.extraction.candidates import find_effect_candidates
from evidencetrace.ingest.document import Document
from evidencetrace.pipeline import EvidencePipeline
from evidencetrace.schemas import AnswerStatus


def _ask(tmp_path, text: str, question: str):
    pipe = EvidencePipeline(tmp_path / "ws")
    pipe.ingest_documents([Document.from_text("d", text)])
    return pipe.ask(question)


@pytest.mark.xfail(strict=True, reason="B9: lexical retrieval cannot bind roles; the placebo arm's MI effect answers a question about the drug")
def test_a_finding_about_another_arm_does_not_answer_a_question_about_the_drug(tmp_path):
    text = ("Drug Zeta did not change stroke risk, whereas placebo increased myocardial infarction "
            "(hazard ratio 1.40, 95% CI 1.10 to 1.78).")
    assert _ask(tmp_path, text, "What is the effect of Drug Zeta on myocardial infarction?").status is AnswerStatus.ABSTAINED


@pytest.mark.xfail(strict=True, reason="B10: a heart rate written 'HR 72 (95% CI 70-74)' with no unit or context word is indistinguishable from a hazard ratio")
def test_bare_heart_rate_is_not_a_hazard_ratio():
    assert find_effect_candidates("Resting HR 72 (95% CI 70-74) at baseline.") == []


@pytest.mark.xfail(strict=True, reason="B7: estimates written 'COR/p = 6.30/0.01' (no interval, unusual notation) are not recognised")
def test_odds_ratio_written_cor_slash_p():
    assert [c.value for c in find_effect_candidates("Smoking (COR/p = 6.30/0.01) and age (COR/p = 1.20/0.03) were associated.")] == [6.3, 1.2]
