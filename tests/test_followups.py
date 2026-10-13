"""Follow-up fixes: covariate-balance SMDs, role-aware retrieval, hard negatives (docs/known-issues.md)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidencetrace.evaluation.gold import GoldFinding
from evidencetrace.evaluation.m1_queries import build_hard_negatives
from evidencetrace.extraction.candidates import find_effect_candidates
from evidencetrace.extraction.clauses import comparator_spans, effect_clause, split_roles
from evidencetrace.ingest.design import classify_design, parse_publication_types
from evidencetrace.ingest.document import Document
from evidencetrace.ingest.parsers import parse_file
from evidencetrace.pipeline import EvidencePipeline
from evidencetrace.retrieval.query import parse_slots
from evidencetrace.schemas import AnswerStatus

ROOT = Path(__file__).resolve().parents[1]


def _ask(tmp_path, text: str, question: str):
    pipe = EvidencePipeline(tmp_path / "ws")
    pipe.ingest_documents([Document.from_text("d", text)])
    return pipe.ask(question)


# ------------------------------------------------------------------ #4: covariate-balance SMDs are not effects
@pytest.mark.parametrize(
    "sentence",
    [
        "higher prevalence of circulatory diseases (93.6% vs. 83.8%, P < 0.001, SMD = 0.312), hypertensive diseases (89.4% vs. 80.6%, P < 0.001, SMD = 0.248).",
        "After inverse probability weighting the covariates were balanced (SMD = 0.031).",
        "Cerebrovascular disease showed the largest remaining standardized difference (SMD = 0.162), though below 0.2.",
    ],
)
def test_balance_diagnostics_are_not_effects(sentence):
    assert find_effect_candidates(sentence) == []


@pytest.mark.parametrize(
    "sentence",
    [
        "The SMD was -0.66 (95% CI -0.89 to -0.44) favouring the intervention.",  # has an interval
        "The standardized mean difference was 0.52 (p = 0.01) for depression scores.",  # no cue
        "with mean difference 0.25% (95% CI -0.01 to 0.51; Cohen's d = 0.16; p = 0.03).",  # Cohen's d is never gated
    ],
)
def test_real_standardized_effects_survive_the_balance_guard(sentence):
    assert any(c.metric.value == "SMD" for c in find_effect_candidates(sentence))


# ------------------------------------------------------------------ #3: clauses, reference arms, query slots
WHEREAS = "Drug Zeta did not change stroke risk, whereas placebo increased myocardial infarction (hazard ratio 1.40, 95% CI 1.10 to 1.78)."


def test_clause_is_the_part_that_holds_the_estimate():
    i = WHEREAS.index("hazard")
    assert effect_clause(WHEREAS, i, i + 30).startswith("placebo increased myocardial infarction")


def test_semicolon_splits_only_between_two_estimates():
    two = "Zeta lowered SBP (MD -5 mmHg, 95% CI -7 to -3); Omega lowered LDL (MD -20 mg/dL, 95% CI -25 to -15)."
    starts = [two.index("MD -5"), two.index("MD -20")]
    assert effect_clause(two, starts[1], starts[1] + 6, starts) .startswith("Omega lowered LDL")
    # a semicolon that merely separates statistics, or introduces the statistic of the previous statement, is no boundary
    stat = "improved s' with low-dose digoxin; adjusted mean difference 1.45 cm/s (95% CI 1.22-1.73; p = 0.002)."
    i = stat.index("adjusted")
    assert effect_clause(stat, i, i + 40, [i]) == stat


def test_reference_arm_spans_and_control_words():
    main, ref = split_roles("Zeta reduced SBP compared with placebo in adults (MD -8.2)")
    assert "placebo" in ref and "placebo" not in main and "Zeta" in main
    main, ref = split_roles("Identical proportions in the ESAX and placebo groups had any AEs")
    assert "placebo" in ref and "ESAX" in main
    main, ref = split_roles("Better blood pressure control was seen with Zeta")
    assert "control" in main and ref == ""  # "control" alone is an outcome word, not an arm
    assert comparator_spans("no comparator here") == []


@pytest.mark.parametrize(
    ("query", "slots"),
    [
        ("What is the effect of Drug Zeta on systolic blood pressure?", ("Drug Zeta", "systolic blood pressure")),
        ("Does Drug Omega reduce MI?", ("Drug Omega", "MI")),
        ("how is the weather", None),
    ],
)
def test_query_slots(query, slots):
    assert parse_slots(query) == slots


def test_a_finding_about_another_arm_does_not_answer_a_question_about_the_drug(tmp_path):
    # was a strict xfail (B9): the placebo arm's MI hazard ratio answered a question about Drug Zeta and MI
    assert _ask(tmp_path, WHEREAS, "What is the effect of Drug Zeta on myocardial infarction?").status is AnswerStatus.ABSTAINED
    assert _ask(tmp_path, WHEREAS, "What is the effect of Drug Zeta on stroke?").status is AnswerStatus.ABSTAINED


def test_fields_come_from_the_estimates_own_clause():
    from evidencetrace.extraction.extractor import extract_findings

    (f,) = extract_findings(Document.from_text("d", WHEREAS))
    assert f.intervention != "Drug Zeta" and f.outcome != "stroke risk"


def test_synthetic_hard_negative_corpus_end_to_end(tmp_path):
    papers = ROOT / "data" / "samples_hardneg"
    pipe = EvidencePipeline(tmp_path / "ws")
    pipe.ingest_documents(parse_file(p) for p in sorted((papers / "papers").glob("*.txt")))
    queries = [json.loads(ln) for ln in (papers / "gold" / "gold_queries.jsonl").read_text().splitlines()]
    wrong = [q["qid"] for q in queries
             if (pipe.ask(q["query"]).status is AnswerStatus.ABSTAINED) != (q["expected_status"] == "abstained")]
    assert not wrong, f"role-binding regressions: {wrong}"


def test_ordinary_queries_still_answered_with_the_drug_as_subject(tmp_path):
    text = "Drug Zeta reduced systolic blood pressure compared with placebo (mean difference -8.2 mmHg, 95% CI -10.1 to -6.3)."
    assert _ask(tmp_path, text, "What is the effect of Drug Zeta on systolic blood pressure?").status is not AnswerStatus.ABSTAINED
    assert _ask(tmp_path, text, "What is the effect of placebo on systolic blood pressure?").status is AnswerStatus.ABSTAINED


# ------------------------------------------------------------------ #2: hard-negative query generation
def _g(gid, inter, comp, out, **kw):
    return GoldFinding(gold_id=gid, doc_id="P1", quote="q", metric="MD", value=1.0, intervention=inter, comparator=comp,
                       outcome=out, fields_annotated=True, **kw)


def test_hard_negatives_ask_about_the_reference_arm_and_are_deduplicated():
    gold = [_g("g1", "dapagliflozin", "placebo", "body weight"), _g("g2", "empagliflozin", "placebo", "body weight"),
            _g("g3", "exercise", "usual care", "6-minute walk distance"), _g("g4", "digoxin", "beta-blockers", "heart rate")]
    qs = build_hard_negatives(gold, split="dev")
    assert [q["query"] for q in qs] == ["What is the effect of placebo on body weight?",
                                        "What is the effect of usual care on 6-minute walk distance?"]
    assert all(q["expected"] == "unanswerable" and q["target"] is None for q in qs)


def test_hard_negative_dropped_when_the_gold_reports_the_control_as_an_intervention():
    gold = [_g("g1", "dapagliflozin", "placebo", "body weight"), _g("g2", "placebo", None, "body weight")]
    assert build_hard_negatives(gold, split="dev") == []


# ------------------------------------------------------------------ #1: study-design screening (real PubMed/title cases)
@pytest.mark.parametrize(
    ("types", "title", "design"),
    [
        (["Journal Article", "Randomized Controlled Trial"], "Effect of drug X on blood pressure: a randomized trial", "trial"),
        (["Journal Article", "Meta-Analysis", "Systematic Review"], "Statins and stroke", "evidence_synthesis"),
        (["Journal Article"], "Hypertension in CKD: a systematic review and meta-analysis", "evidence_synthesis"),
        # a pooled analysis of the trials' own patient data is a trial report when PubMed says so ...
        (["Journal Article", "Randomized Controlled Trial"], "Semaglutide in HFpEF: a pooled analysis of two trials", "trial"),
        # ... and an evidence synthesis when it does not
        (["Journal Article"], "Salt and blood pressure: a pooled analysis of 12 cohorts", "evidence_synthesis"),
        (["Clinical Trial Protocol", "Journal Article"], "Effect of a nurse-led intervention on blood pressure", "protocol"),
        (["Journal Article", "Randomized Controlled Trial"], "Periodontitis and hypertension: evidence from Mendelian randomization", "observational"),
        (["Journal Article", "Observational Study"], "Biomarkers in hypertension", "observational"),
        (["Journal Article"], "Cost-effectiveness of polypill therapy", "economic_evaluation"),
        (["Journal Article", "Practice Guideline"], "Management of hypertension in diabetic kidney disease", "other"),
    ],
)
def test_design_classification(types, title, design):
    assert classify_design(types, title)[0] == design


def test_disagreement_between_pubmed_and_title_is_flagged_for_a_human():
    assert classify_design(["Randomized Controlled Trial"], "Evidence from Mendelian randomization")[2] is True
    assert classify_design(["Randomized Controlled Trial"], "A randomized trial of X")[2] is False


def test_publication_types_are_read_from_pubmed_xml():
    xml = ("<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article><PublicationTypeList>"
           "<PublicationType UI='D016428'>Journal Article</PublicationType><PublicationType UI='D016449'>Randomized "
           "Controlled Trial</PublicationType></PublicationTypeList></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>")
    assert parse_publication_types(xml) == {"1": ["Journal Article", "Randomized Controlled Trial"]}
    with pytest.raises(ValueError, match="entities"):
        parse_publication_types('<!DOCTYPE a [<!ENTITY x "y">]><a/>')
