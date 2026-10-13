from dataclasses import asdict

import pytest

from evidencetrace.config import Config
from evidencetrace.pipeline import EvidencePipeline
from evidencetrace.render import render_answer
from evidencetrace.schemas import AbstainReason, Answer, AnswerStatus, ConflictKind


def test_conflicting_answer_with_all_three_conflict_kinds_resolved(pipeline):
    ans = pipeline.ask("What is the effect of Drug Zeta on systolic blood pressure compared with placebo?")
    assert ans.status is AnswerStatus.CONFLICTING
    assert {f.doc_id for f in ans.findings} == {"paper_a", "paper_c", "paper_d"}
    assert sorted(c.kind.value for c in ans.conflicts) == ["magnitude", "significance"]


def test_direction_conflict_excludes_the_cited_result(pipeline):
    ans = pipeline.ask("Does Drug Zeta reduce hospitalization?")
    assert ans.status is AnswerStatus.CONFLICTING
    assert sorted(f.value for f in ans.findings) == [0.78, 1.12]  # 0.55 is cited, not paper_b's
    assert [c.kind for c in ans.conflicts] == [ConflictKind.DIRECTION]


def test_cited_findings_can_be_opted_in(tmp_path, samples):
    cfg = Config()
    cfg.retrieval.include_cited = True
    cfg.abstention.min_confidence = 0.0
    pipe = EvidencePipeline(tmp_path / "ws", cfg)
    pipe.ingest_paths([samples / "papers"])
    ans = pipe.ask("Does Drug Zeta reduce hospitalization?")
    assert 0.55 in {f.value for f in ans.findings}


def test_plain_answer_and_synonym_expansion(pipeline):
    ans = pipeline.ask("Does Drug Omega reduce MI?")
    assert ans.status is AnswerStatus.ANSWERED
    (f,) = ans.findings
    assert (f.metric.value, f.value) == ("OR", 0.71)


@pytest.mark.parametrize(
    "query",
    [
        "What is the effect of Drug Zeta on stroke?",           # only mentioned next to a figure
        "Does Drug Omega lower blood pressure?",               # right topic, wrong drug
        "What is the effect of Drug Zeta on systolic blood pressure in children?",
        "What is the effect of Drug Zeta on mortality?",
        "What is the effect of Drug Zeta on dizziness?",       # qualitative only
    ],
)
def test_abstains_when_evidence_is_missing(pipeline, query):
    ans = pipeline.ask(query)
    assert ans.status is AnswerStatus.ABSTAINED
    assert ans.findings == [] and ans.conflicts == []
    assert ans.abstain_reasons == [AbstainReason.LOW_COVERAGE]
    assert "NOT an answer" in render_answer(ans) or not ans.nearest_evidence


def test_every_returned_number_is_traceable_to_its_span(pipeline):
    docs = pipeline.ws.load_documents()
    ans = pipeline.ask("What is the effect of Drug Zeta on systolic blood pressure?")
    assert ans.findings
    for f in ans.findings:
        assert docs[f.doc_id].text[f.span.start : f.span.end] == f.span.text
        assert str(abs(f.value)).rstrip("0").rstrip(".") in f.span.text.replace("−", "")


def test_edited_source_text_blocks_the_answer(pipeline):
    path = pipeline.ws.docs_dir / "paper_e.json"
    path.write_text(path.read_text().replace("−32.5", "−33.5"), encoding="utf-8")
    ans = pipeline.ask("What is the effect of Drug Omega on LDL cholesterol?")
    assert ans.status is AnswerStatus.ABSTAINED
    assert ans.abstain_reasons == [AbstainReason.UNVERIFIED_PROVENANCE]


def test_conflict_mode_abstain(tmp_path, samples):
    cfg = Config()
    cfg.abstention.conflict_mode = "abstain"
    pipe = EvidencePipeline(tmp_path / "ws", cfg)
    pipe.ingest_paths([samples / "papers"])
    ans = pipe.ask("Does Drug Zeta reduce hospitalization?")
    assert ans.status is AnswerStatus.ABSTAINED
    assert ans.abstain_reasons == [AbstainReason.UNRESOLVED_CONFLICT]


def test_min_verified_threshold(tmp_path, samples):
    cfg = Config()
    cfg.abstention.min_verified = 2
    pipe = EvidencePipeline(tmp_path / "ws", cfg)
    pipe.ingest_paths([samples / "papers"])
    ans = pipe.ask("Does Drug Omega reduce MI?")
    assert ans.abstain_reasons == [AbstainReason.INSUFFICIENT_SUPPORT]


def test_reingest_is_idempotent(pipeline, samples):
    before = len(pipeline.ws.load_findings())
    pipeline.ingest_paths([samples / "papers"])
    assert len(pipeline.ws.load_findings()) == before


def test_answer_json_round_trip(pipeline):
    ans = pipeline.ask("Does Drug Zeta reduce hospitalization?")
    assert Answer.model_validate_json(ans.model_dump_json()) == ans


def test_default_toml_matches_dataclass_defaults(samples):
    loaded = Config.load(samples.parents[1] / "configs" / "default.toml")
    assert asdict(loaded) == asdict(Config())


def test_unknown_config_key_is_rejected(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("[abstention]\nmin_covrage = 0.5\n")
    with pytest.raises(ValueError, match="min_covrage"):
        Config.load(bad)
