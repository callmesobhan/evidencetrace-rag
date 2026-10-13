"""Regression tests for the problems an independent red-team review found (docs/known-issues.md)."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET

import pytest

from evidencetrace.cli import main
from evidencetrace.config import Config, ConfigError
from evidencetrace.errors import IngestError
from evidencetrace.extraction.candidates import find_effect_candidates
from evidencetrace.extraction.extractor import extract_findings
from evidencetrace.ingest.document import Document, detect_sections
from evidencetrace.ingest.parsers import classify_section, parse_file
from evidencetrace.pipeline import EvidencePipeline
from evidencetrace.schemas import Finding, Interval
from evidencetrace.store import Workspace
from evidencetrace.textnorm import canonical_text
from evidencetrace.verification.conflicts import comparable, detect_conflicts
from evidencetrace.verification.provenance import Verifier, numbers_in

SENT = "Drug Zeta reduced systolic blood pressure (mean difference -8.2 mmHg, 95% CI -10.1 to -6.3; p<0.001; n = 412)."


def _one(text: str = SENT) -> tuple[Document, Finding]:
    doc = Document.from_text("d", text)
    (f,) = extract_findings(doc)
    return doc, f


def _ok(doc: Document, f: Finding) -> dict[str, bool]:
    return Verifier({doc.doc_id: doc}).verify(f).checks


# ------------------------------------------------------------------ R-02: provenance is positional
def test_untampered_finding_verifies():
    doc, f = _one()
    assert all(_ok(doc, f).values())


@pytest.mark.parametrize(
    "tamper",
    [
        {"value": -10.1},  # the CI's lower bound read as the estimate: the number IS in the sentence
        {"ci": Interval(low=-6.3, high=-6.3)},  # swapped / collapsed interval, both numbers present
        {"p_operator": ">"},  # p<0.001 reported as p>0.001
        {"p_value": 0.412},
    ],
)
def test_wrong_slot_is_caught_although_every_number_is_in_the_sentence(tamper):
    doc, f = _one()
    bad = f.model_copy(update=tamper)
    checks = _ok(doc, bad)
    assert checks["estimate_reproduced"] is False


def test_edited_document_is_detected_even_if_the_stored_hash_is_left_alone():
    doc, f = _one()
    edited = doc.model_copy(update={"text": doc.text.replace("-8.2", "-9.2")})  # stored sha256 untouched
    assert _ok(edited, f)["document_unchanged"] is False


# ------------------------------------------------------------------ R-06: finding ids identify one finding
def test_ids_are_unique_when_only_the_interval_differs():
    text = "The odds ratio was 0.99 (95% CI 0.80 to 1.22) overall and the odds ratio was 0.99 (95% CI 0.80 to 1.23) adjusted."
    ids = [f.finding_id for f in extract_findings(Document.from_text("d", text))]
    assert len(ids) == 2 and len(set(ids)) == 2


def test_exact_repeats_without_dedupe_still_get_distinct_ids():
    text = "The hazard ratio was 0.80 (95% CI 0.70 to 0.91). The hazard ratio was 0.80 (95% CI 0.70 to 0.91)."
    fs = extract_findings(Document.from_text("d", text), dedupe_findings=False)
    assert len(fs) == 2 and len({f.finding_id for f in fs}) == 2


def test_identical_estimates_for_different_arms_in_one_sentence_are_all_kept():
    text = "The odds ratios were 0.99 (95% CI 0.80-1.22) in arm 3 and 0.99 (95% CI 0.80-1.22) in arm 5."
    fs = extract_findings(Document.from_text("d", text))
    assert [f.value for f in fs] == [0.99, 0.99] and len({f.finding_id for f in fs}) == 2


def test_a_restatement_in_another_sentence_still_collapses():
    text = "The hazard ratio was 0.80 (95% CI 0.70 to 0.91). Later, the hazard ratio was 0.80 (95% CI 0.70 to 0.91) again."
    assert len(extract_findings(Document.from_text("d", text))) == 1


# ------------------------------------------------------------------ R-08 / R-09 / R-16: number reading
def test_middle_dot_decimals_are_decimals():
    (c,) = find_effect_candidates(canonical_text("mean difference 2·5 (95% CI 1·2 to 3·8)"))
    assert (c.value, c.ci_low, c.ci_high) == (2.5, 1.2, 3.8)
    (h,) = find_effect_candidates(canonical_text("HR 0·78 (95% CI 0·65–0·93; p=0·006)"))
    assert (h.value, h.ci_low, h.ci_high, h.p_value) == (0.78, 0.65, 0.93, 0.006)


def test_middle_dot_in_a_chemical_formula_is_left_alone():
    assert "Cl12·24H2O" in canonical_text("Mg4K(NH4)3Cl12·24H2O") and "4.4 million" in canonical_text("4·4 million")


@pytest.mark.parametrize(
    ("p_text", "expected", "op"),
    [("p = 3.1e-4", 3.1e-4, "="), ("p = 1.2 x 10^-5", 1.2e-5, "="), ("P < 10-4", 1e-4, "<"), ("p=1.02 × 10−6", 1.02e-6, "=")],
)
def test_scientific_notation_p_values(p_text, expected, op):
    (c,) = find_effect_candidates(f"The hazard ratio was 0.75 (95% CI 0.60 to 0.93; {p_text}).")
    assert c.p_value == pytest.approx(expected, rel=1e-9) and c.p_operator == op
    assert any(abs(x - expected) < expected * 1e-9 for x in numbers_in(p_text))


@pytest.mark.parametrize("s", ["mean RR interval was 850 ms (95% CI 800-900)", "HR 72 beats/min (95% CI 70-74)"])
def test_heart_rate_and_rr_interval_are_not_ratios(s):
    assert find_effect_candidates(s) == []


def test_real_hazard_and_risk_ratios_survive_the_guards():
    assert [c.value for c in find_effect_candidates("The HR was 0.78 (95% CI 0.65-0.93) and the RR was 0.81 (95% CI 0.70-0.95).")] == [0.78, 0.81]


# ------------------------------------------------------------------ R-17: conflicts
def _mk(doc_id, value, lo, hi, p, op, metric="MD", unit="mmHg"):
    return Finding.model_validate({
        "finding_id": f"f_{doc_id}", "doc_id": doc_id, "doc_sha256": "x", "metric": metric, "value": value,
        "ci": {"low": lo, "high": hi} if lo is not None else None, "p_value": p, "p_operator": op, "unit": unit,
        "intervention": "drug zeta", "outcome": "systolic blood pressure", "attribution": "own", "confidence": 0.9, "extractor": "test",
        "span": {"doc_id": doc_id, "start": 0, "end": 3, "text": "abc"},
    })


def test_p_less_than_alpha_counts_as_significant():
    a, b = _mk("a", -8.0, None, None, 0.05, "<"), _mk("b", 6.0, None, None, 0.01, "<")
    assert [c.kind.value for c in detect_conflicts([a, b])] == ["direction"]


def test_unit_and_scale_mismatches_are_not_conflicts():
    cfg = Config().conflicts
    assert not comparable(_mk("a", -8, -10, -6, None, None, unit="mmHg"), _mk("b", 6, 4, 8, None, None, unit="kPa"), cfg)
    assert not comparable(_mk("a", -8, -10, -6, None, None, metric="MD"), _mk("b", 0.5, 0.3, 0.7, None, None, metric="SMD", unit=None), cfg)


# ------------------------------------------------------------------ R-18 / R-19 / R-20 / R-25: parsing and input handling
@pytest.mark.parametrize(
    ("title", "expected"),
    [("Results of the nutritional supplement trial", "results"), ("Consent rates and efficacy results", "results"),
     ("Results", "results"), ("Funding", None), ("Acknowledgements", None), ("Conflict of interest", None)],
)
def test_results_sections_with_back_matter_words_are_kept(title, expected):
    sec = ET.fromstring(f"<sec><title>{title}</title><p>x</p></sec>")
    assert classify_section(sec) == expected


def test_bom_and_control_characters(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes("﻿Results\nThe hazard ratio was 0.8 (95% CI 0.7 to 0.9)\x1b[2J\x1b]0;pwn\x07.".encode())
    doc = parse_file(p)
    assert "\x1b" not in doc.text and "\x07" not in doc.text and not doc.text.startswith("﻿")
    assert detect_sections(doc.text)[0].name == "results"


def test_malformed_xml_non_utf8_and_entities_are_one_line_errors(tmp_path, capsys):
    (tmp_path / "bad.xml").write_text("<article><p>unclosed")
    (tmp_path / "latin.txt").write_bytes("caf\xe9".encode("latin-1"))
    (tmp_path / "ent.xml").write_text('<!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>')
    for name in ("bad.xml", "latin.txt", "ent.xml"):
        with pytest.raises(IngestError):
            parse_file(tmp_path / name)
        assert main(["ingest", str(tmp_path / name), "--workspace", str(tmp_path / "ws")]) == 2
        assert capsys.readouterr().err.startswith("error:")


def test_same_stem_inputs_are_refused_and_nothing_is_written(tmp_path):
    for d in ("a", "b"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "paper.txt").write_text("The hazard ratio was 0.8 (95% CI 0.7 to 0.9).")
    ws = tmp_path / "ws"
    with pytest.raises(IngestError, match="same file name stem|document id"):
        EvidencePipeline(ws).ingest_paths([tmp_path / "a", tmp_path / "b"])
    assert not list((ws / "docs").glob("*.json")) and not (ws / "findings.jsonl").exists()


def test_unsafe_document_ids_cannot_escape_the_workspace(tmp_path):
    doc = Document.from_text("../../evil", "x")
    with pytest.raises(IngestError):
        Workspace(tmp_path / "ws").save_document(doc)


def test_config_values_are_type_checked(tmp_path):
    bad = tmp_path / "c.toml"
    bad.write_text('[retrieval]\ntop_k = "eight"\n')
    with pytest.raises(ConfigError, match="top_k"):
        Config.load(bad)


# ------------------------------------------------------------------ R-15: no quadratic blow-up on hostile input
def test_pathological_input_is_fast():
    t0 = time.perf_counter()
    assert find_effect_candidates("HR 1.0 (95% CI " * 8000) == []  # 120 kB "sentence"
    detect_sections("A" + " " * 30000 + "!")
    assert time.perf_counter() - t0 < 3.0


def test_abstention_names_the_users_words_not_stems(tmp_path):
    from evidencetrace.render import render_answer

    pipe = EvidencePipeline(tmp_path / "ws")
    pipe.ingest_documents([Document.from_text("d", "Drug Zeta reduced systolic blood pressure (mean difference -8.2 mmHg, 95% CI -10.1 to -6.3).")])
    out = render_answer(pipe.ask("What is the effect of Drug Zeta on stroke?"))
    assert "strok" not in out.replace("stroke", "")  # a bare stem would remain after removing the real word
