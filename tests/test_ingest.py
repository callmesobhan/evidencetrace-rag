import textwrap

from evidencetrace.ingest import Document, chunk_document, parse_file, split_sentences
from evidencetrace.ingest.parsers import parse_jats


def test_sentence_spans_round_trip():
    doc = Document.from_text("d", "Results\n\nDrug A helped (p=0.03). Drug B did not. Fig. 3 shows it.")
    sents = split_sentences(doc)
    assert [s.text for s in sents] == [
        "Drug A helped (p=0.03).",
        "Drug B did not.",
        "Fig. 3 shows it.",  # abbreviation must not split
    ]
    for s in sents:
        assert doc.text[s.start : s.end] == s.text


def test_heading_is_not_glued_to_first_sentence():
    doc = Document.from_text("d", "Results\nDrug Zeta reduced pressure.\n")
    assert [s.text for s in split_sentences(doc)] == ["Drug Zeta reduced pressure."]


def test_et_al_and_initials_do_not_split():
    doc = Document.from_text("d", "Introduction\n\nHartmann et al. [3] reported a trial by J. Smith. It was small.")
    texts = [s.text for s in split_sentences(doc)]
    assert texts == ["Hartmann et al. [3] reported a trial by J. Smith.", "It was small."]


def test_sections_and_section_at():
    doc = Document.from_text("d", "Title\n\nAbstract\n\nA.\n\nResults\n\nB.\n")
    assert [s.name for s in doc.sections] == ["front", "abstract", "results"]
    assert doc.section_at(doc.text.index("B.")) == "results"


def test_sha256_pins_canonical_text():
    a = Document.from_text("d", "x\r\ny")
    b = Document.from_text("d", "x\ny")
    assert a.text == b.text and a.sha256 == b.sha256


def test_chunks_are_exact_slices(samples):
    doc = parse_file(samples / "papers" / "paper_a.txt")
    chunks = chunk_document(doc, max_chars=300)
    assert len(chunks) > 1
    for c in chunks:
        assert doc.text[c.start : c.end] == c.text


JATS = textwrap.dedent(
    """\
    <article xmlns:mml="http://www.w3.org/1998/Math/MathML"><front><article-meta>
    <title-group><article-title>T</article-title></title-group>
    <abstract><sec><title>Results</title><p>HR 0.7 overall.</p></sec></abstract></article-meta></front>
    <body>
    <sec sec-type="intro"><title>Introduction</title>
      <p>Earlier work found HR 0.5 <xref ref-type="bibr" rid="b1">3</xref>.</p></sec>
    <sec><title>2. Materials and Methods</title><p>We randomised 40 adults.</p>
      <sec><title>Statistics</title><p>Cox models were used.</p></sec></sec>
    <sec><title>3. Results</title>
      <p>Treatment lowered risk (HR 0.8, 95% CI 0.7 to 0.9; <inline-formula><alternatives>
         <tex-math>\\documentclass{article}</tex-math><mml:math><mml:mi>P</mml:mi><mml:mo>&lt;</mml:mo>
         <mml:mn>0.05</mml:mn></mml:math></alternatives></inline-formula>).</p>
      <table-wrap><caption><p>Table 1 should not appear.</p></caption></table-wrap>
      <sec><title>Subgroups</title><p>Effects were similar.</p></sec></sec>
    <sec><title>Funding</title><p>Funded by nobody.</p></sec>
    <sec sec-type="conclusions"><title>Conclusions</title><p>It works.</p></sec>
    </body></article>"""
)


def test_jats_sections_come_from_structure_not_text_guessing():
    doc = parse_jats("d", JATS)
    names = [s.name for s in doc.sections]
    assert names == ["front", "abstract", "introduction", "methods", "results", "conclusion"]
    # nested <sec> stays inside its parent; back matter and tables are dropped
    assert doc.section_at(doc.text.index("Cox models")) == "methods"
    assert doc.section_at(doc.text.index("Effects were similar")) == "results"
    assert "Funded by" not in doc.text and "Table 1" not in doc.text


def test_jats_keeps_citations_and_mathml_but_drops_latex():
    doc = parse_jats("d", JATS)
    assert "[3]" in doc.text
    assert "P<0.05" in doc.text.replace(" ", "") and "documentclass" not in doc.text


def test_jats_findings_get_the_right_section_and_attribution():
    from evidencetrace.extraction import extract_findings
    from evidencetrace.schemas import Attribution

    findings = extract_findings(parse_jats("d", JATS))
    by_value = {f.value: f for f in findings}
    assert by_value[0.5].attribution is Attribution.CITED and by_value[0.5].span.section == "introduction"
    assert by_value[0.8].attribution is Attribution.OWN and by_value[0.8].span.section == "results"


def test_table_nested_inside_a_paragraph_does_not_leak_into_text():
    xml = (
        "<article><body><sec><title>Results</title>"
        "<p>HR 0.8 (95% CI 0.7 to 0.9). <table-wrap><table><tr><td>SMD-0.08 [-0.31,0.15]</td></tr></table></table-wrap>"
        " Done.</p></sec></body></article>"
    )
    doc = parse_jats("d", xml)
    assert "SMD" not in doc.text and "Done." in doc.text
