import pytest

from evidencetrace.extraction.extractor import extract_findings
from evidencetrace.ingest import Document, parse_file
from evidencetrace.schemas import Interval
from evidencetrace.verification import Verifier, number_in_text, numbers_in


@pytest.mark.parametrize(
    "text, expected",
    [
        ("0.65-0.93", [0.65, 0.93]),                 # hyphen is a range separator, not a sign
        ("−10.1 to −6.3", [-10.1, -6.3]),
        ("(–5.0, 0.8)", [-5.0, 0.8]),                # en dash as minus
        ("n = 1,234", [1234.0]),
        ("p=.006", [0.006]),
    ],
)
def test_numbers_in(text, expected):
    assert numbers_in(text) == expected


def test_number_in_text_is_exact_not_substring():
    assert number_in_text(0.78, "HR 0.78 (95% CI 0.65 to 0.93)")
    assert not number_in_text(0.7, "HR 0.78")
    assert not number_in_text(8.0, "mean difference −8.2")


@pytest.fixture()
def paper_a(samples):
    doc = parse_file(samples / "papers" / "paper_a.txt")
    return doc, extract_findings(doc)


def test_genuine_findings_verify(paper_a):
    doc, findings = paper_a
    v = Verifier({doc.doc_id: doc})
    assert findings and all(v.verify(f).ok for f in findings)


def test_tampered_value_is_caught(paper_a):
    doc, (f, *_) = paper_a
    bad = f.model_copy(update={"value": f.value - 1.0})
    res = Verifier({doc.doc_id: doc}).verify(bad)
    assert not res.ok and "value_in_span" in res.failures


def test_tampered_ci_p_and_n_are_caught(paper_a):
    doc, (f, *_) = paper_a
    v = Verifier({doc.doc_id: doc})
    assert "ci_in_span" in v.verify(f.model_copy(update={"ci": Interval(low=-11.0, high=-6.3)})).failures
    assert "p_in_span" in v.verify(f.model_copy(update={"p_value": 0.5})).failures
    assert "n_in_span" in v.verify(f.model_copy(update={"n": 999})).failures


def test_fabricated_field_is_caught(paper_a):
    doc, (f, *_) = paper_a
    res = Verifier({doc.doc_id: doc}).verify(f.model_copy(update={"intervention": "Drug Omega"}))
    assert "intervention_in_span" in res.failures


def test_edited_document_is_caught(paper_a):
    doc, (f, *_) = paper_a
    edited = Document.from_text(doc.doc_id, doc.text.replace("−8.2", "−9.2"))
    res = Verifier({doc.doc_id: edited}).verify(f)
    assert not res.ok
    assert "document_unchanged" in res.failures and "span_text_matches" in res.failures


def test_missing_document_fails_closed(paper_a):
    _, (f, *_) = paper_a
    assert not Verifier({}).verify(f).ok


@pytest.mark.parametrize(
    "text, expected",
    [
        ("\u2212 6.0ml (95% CI: -8.07 -\u22123.87", [-6.0, -8.07, -3.87]),   # spaced true minus; hyphen+minus
        ("(SMD -0.12, \u2212 0.21 to \u2212 0.03)", [-0.12, -0.21, -0.03]),
    ],
)
def test_spaced_minus_signs_are_read_as_signs(text, expected):
    got = numbers_in(text)
    for x in expected:
        assert x in got, (x, got)


def test_spaced_range_is_readable_but_a_flipped_sign_is_still_caught():
    assert number_in_text(0.93, "CI 0.65 - 0.93") and number_in_text(0.65, "CI 0.65 - 0.93")
    assert number_in_text(-6.0, "was \u2212 6.0 ml")
    assert not number_in_text(6.0, "was \u2212 6.0 ml")        # sign flip must fail
    assert not number_in_text(6.0, "was \u22126.0 ml")


def test_percent_range_is_a_range_not_a_negative_number():
    assert number_in_text(7.3, "between-group difference of 3.8% (95% CI, 0.3%-7.3%)")
    assert number_in_text(0.3, "between-group difference of 3.8% (95% CI, 0.3%-7.3%)")
    assert not number_in_text(-7.3, "(95% CI, 0.3%-7.3%)")


def test_scientific_notation_verifies_exactly_not_approximately():
    text = "heart failure (OR = 0.62; p = 2.01 \u00d7 10\u22125)"
    assert number_in_text(2.01e-5, text)
    assert not number_in_text(2.02e-5, text)       # tiny p-values need relative, not absolute, tolerance
    assert not number_in_text(2.01e-10, text)


def test_paper_level_rarity_stops_a_big_paper_from_hiding_a_wrong_drug():
    from evidencetrace.retrieval import LexicalFindingRetriever
    from helpers import make_finding

    # one meta-analysis contributes 14 findings about esaxerenone; 14 other papers each report one finding
    big = [
        make_finding(doc_id="meta", value=-i - 1.0, ci=(-i - 2.0, -i), start=i * 100,
                     intervention="esaxerenone", outcome=f"outcome{i}")
        for i in range(14)
    ]
    others = [make_finding(doc_id=f"p{i}", intervention=f"drug{i}", outcome=f"endpoint{i}") for i in range(14)]
    wrong_drug = others[3]  # reports endpoint3, never mentions esaxerenone
    q = "effect of esaxerenone on endpoint3"

    by_findings = LexicalFindingRetriever(big + others, rarity_unit="findings").score_finding(q, wrong_drug.finding_id)
    by_papers = LexicalFindingRetriever(big + others, rarity_unit="papers").score_finding(q, wrong_drug.finding_id)
    # by findings, esaxerenone is 50% of the corpus -> "common" -> its absence is forgiven (the bug) ...
    assert by_findings.missing_terms == ["esaxerenon"] and by_findings.missing_rare == [] and by_findings.coverage > 0.9
    # ... by papers it lives in 1 of 15 papers -> rare -> a finding that lacks it is not an answer
    assert by_papers.missing_rare == ["esaxerenon"]
