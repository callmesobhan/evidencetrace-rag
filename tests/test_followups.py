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


# ------------------------------------------------------------------ dense index is rebuilt when its inputs change
def test_persisted_dense_index_is_invalidated_when_a_document_changes(tmp_path):
    pytest.importorskip("llama_index.core")
    from llama_index.core.embeddings import MockEmbedding

    from evidencetrace.retrieval.llama_index_store import LlamaIndexChunkIndex

    a = Document.from_text("a", "Drug Zeta reduced hospitalization (hazard ratio 0.78, 95% CI 0.65 to 0.93).")
    kw = {"embed_model": MockEmbedding(embed_dim=8), "persist_dir": tmp_path / "idx", "chunk_chars": 400}
    first = LlamaIndexChunkIndex({"a": a}, **kw)
    assert {h.doc_id for h in first.retrieve_chunks("Zeta", 20)} == {"a"}
    # unchanged inputs: the persisted index is reused (the stamp matches)
    assert (tmp_path / "idx" / "fingerprint.txt").exists()
    b = Document.from_text("b", "Drug Omega lowered LDL cholesterol (mean difference -22 mg/dL, 95% CI -27 to -17).")
    second = LlamaIndexChunkIndex({"a": a, "b": b}, **kw)  # a new paper: the old index must not be served
    assert {h.doc_id for h in second.retrieve_chunks("Omega", 20)} == {"a", "b"}
    edited = Document.from_text("a", "Drug Zeta did not change hospitalization (hazard ratio 1.01, 95% CI 0.90 to 1.13).")
    third = LlamaIndexChunkIndex({"a": edited}, **kw)  # same id, different text
    assert {h.doc_id for h in third.retrieve_chunks("Zeta", 20)} == {"a"}
    texts = [n.node.get_content() for n in third._index.as_retriever(similarity_top_k=20).retrieve("Zeta")]
    assert texts and all("did not change" in t for t in texts)


# ------------------------------------------------------------------ notation fixes verified on real misses / false positives
def _est(sentence):
    return [(c.metric.value, c.value, (c.ci_low, c.ci_high) if c.ci_low is not None else None) for c in find_effect_candidates(sentence)]


def test_posterior_interval_is_an_interval():
    s = "HbA1c was associated with the hazard for DR (hazard ratio 1.4; 95% posterior interval, 1.02-1.88, adjusted for group)."
    assert _est(s) == [("HR", 1.4, (1.02, 1.88))]


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("did not alter the results (HRadjusted = 0.95; 95% CI = 0.72, 1.24).", [("HR", 0.95, (0.72, 1.24))]),
        ("the ORunadjusted was 2.0 (95% CI 1.1-3.6)", [("OR", 2.0, (1.1, 3.6))]),
        ("adjusted HR 0.80 (95% CI 0.66-0.97)", [("HR", 0.8, (0.66, 0.97))]),  # the ordinary word order still works
    ],
)
def test_qualifier_glued_to_the_abbreviation(sentence, expected):
    assert _est(sentence) == expected


def test_change_from_their_own_baseline_is_not_a_between_group_estimate():
    assert _est("Compared to their baseline, males in the MBSR group improved in stress (MD, 3.08; 95% CI, 0.30 to 5.86).") == []
    # ... but a pooled pre/post change that the gold accepts ("the baseline moment") and a real between-group difference are kept
    assert _est("decreased compared to the baseline moment (mean difference = -9.52; 95% CI -12.89 to -6.14; p<0.001)") != []
    assert _est("a between-group difference in changes from baseline of -0.59 points (95% CI, -0.96 to -0.21; P = .002)") != []


def test_mean_difference_with_an_sd_label_is_not_an_estimate():
    assert _est("The mean difference (SD) of waist circumference was -0.23 (9.1) cm in the usual care group.") == []
    assert _est("The mean difference was -0.23 (95% CI -0.9 to 0.4) cm.") != []


# ------------------------------------------------------------------ design lookup: PubMed re-indexing is not a classification change
def _design_row(pmcid="PMC1", types=("Journal Article", "Randomized Controlled Trial"), design="trial"):
    return {"pmcid": pmcid, "pmid": "1", "split": "dev", "pubmed_types": sorted(types), "design": design, "basis": "pubmed", "disagree": False}


def test_design_compare_accepts_a_new_publication_type_with_the_same_classification():
    from evidencetrace.ingest.design import compare_design

    now = [_design_row(types=("Journal Article", "Randomized Controlled Trial", "Research Support, Non-U.S. Gov't"))]
    d = compare_design(now, [_design_row()])
    assert d["classification"] == d["missing"] == d["added"] == []
    assert d["types_only"] == [{"pmcid": "PMC1", "added": ["Research Support, Non-U.S. Gov't"], "removed": []}]


def test_design_compare_reports_a_changed_classification_and_missing_or_added_papers():
    from evidencetrace.ingest.design import compare_design

    d = compare_design([_design_row(types=("Journal Article",), design="other")], [_design_row()])
    assert d["classification"] == [{"pmcid": "PMC1", "fields": {"design": ["trial", "other"]}}] and d["types_only"] == []
    d = compare_design([_design_row("PMC2")], [_design_row("PMC1")])
    assert d["missing"] == ["PMC1"] and d["added"] == ["PMC2"]
    assert compare_design([_design_row()], [_design_row()]) == {"missing": [], "added": [], "classification": [], "types_only": []}

