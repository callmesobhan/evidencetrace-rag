"""The PDF parser: layout logic on hand-built blocks, and real PDFs (two columns, running headers, hyphenated line breaks)."""

from __future__ import annotations

import random
import re
import textwrap
from pathlib import Path

import pytest

from evidencetrace.errors import IngestError
from evidencetrace.extraction.extractor import extract_findings
from evidencetrace.ingest.document import Document
from evidencetrace.ingest.parsers import PdfBlock, PdfPage, _dehyphenate, layout_pdf, parse_file

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples" / "papers"


def _paragraphs() -> list[str]:
    text = "\n\n".join(p.read_text(encoding="utf-8") for p in sorted(SAMPLES.glob("*.txt"))).replace("−", "-")
    return [" ".join(p.split()) for p in text.split("\n\n") if p.strip()]


def _keys(doc: Document) -> set[tuple]:
    return {(f.metric.value, f.value, (f.ci.low, f.ci.high) if f.ci else None, f.p_value) for f in extract_findings(doc)}


# ------------------------------------------------------------------ pure layout logic
def test_dehyphenate_joins_broken_words_and_ranges_only():
    assert _dehyphenate("a compar-\ntment model") == "a compartment model"
    assert _dehyphenate("HR 0.65-\n0.93") == "HR 0.65-0.93"
    assert _dehyphenate("a long-term plan and well-being") == "a long-term plan and well-being"  # no line break: untouched
    assert _dehyphenate("re-\nAnalysis") == "re-\nAnalysis"  # an uppercase continuation is not a split word
    assert _dehyphenate("hos­pital") == "hospital"  # soft hyphen


def _page(blocks, w=600, h=800):
    return PdfPage(w, h, [PdfBlock(*b) for b in blocks])


def test_columns_are_read_left_then_right_and_full_width_blocks_stay_in_place():
    pages = [_page([
        (40, 100, 560, 130, "Title spanning both columns."),
        (320, 150, 560, 200, "Right top."), (40, 150, 280, 200, "Left top."),
        (40, 210, 280, 260, "Left bottom."), (320, 210, 560, 260, "Right bottom."),
        (40, 300, 560, 330, "Wide abstract."),
        (40, 340, 280, 390, "Left two."), (320, 340, 560, 390, "Right two."),
    ])]
    assert layout_pdf(pages).split("\n\n") == ["Title spanning both columns.", "Left top.", "Left bottom.", "Right top.", "Right bottom.",
                                              "Wide abstract.", "Left two.", "Right two."]


def test_running_headers_footers_and_page_numbers_are_removed_but_body_text_is_kept():
    def page(n):
        return _page([(40, 20, 400, 40, f"Journal of Fictional Medicine 2026;12:e{n:04d}"), (40, 100, 560, 160, f"Body paragraph {n}."),
                      (280, 770, 320, 790, str(n))])
    out = layout_pdf([page(1), page(2), page(3), page(4)])
    assert out.split("\n\n") == ["Body paragraph 1.", "Body paragraph 2.", "Body paragraph 3.", "Body paragraph 4."]


def test_a_sentence_cut_by_a_column_break_is_rejoined_but_a_clean_break_is_not():
    cut = [_page([(40, 100, 280, 700, "The effect was not significant (mean difference -2.1 mmHg,"), (320, 100, 560, 200, "95% CI -5.0 to 0.8; p = 0.15) in this trial."),
                  (320, 220, 560, 260, "Results"), (320, 270, 560, 330, "Next paragraph starts here.")])]
    assert layout_pdf(cut).split("\n\n") == ["The effect was not significant (mean difference -2.1 mmHg, 95% CI -5.0 to 0.8; p = 0.15) in this trial.",
                                              "Results", "Next paragraph starts here."]
    # a break that falls between two sentences ("... trial." / "Next ...") leaves two paragraphs
    clean = [_page([(40, 100, 280, 700, "First paragraph ends here."), (320, 100, 560, 200, "Second paragraph begins here.")])]
    assert layout_pdf(clean).split("\n\n") == ["First paragraph ends here.", "Second paragraph begins here."]


def test_a_margin_block_that_is_real_text_on_a_short_document_is_kept():
    # fewer than 3 pages: nothing is "repeated", so only bare page numbers go
    out = layout_pdf([_page([(40, 20, 400, 40, "Funding statement near the top."), (40, 100, 560, 160, "Body."), (290, 780, 310, 795, "7")])])
    assert out.split("\n\n") == ["Funding statement near the top.", "Body."]


# ------------------------------------------------------------------ real PDFs
try:
    import pymupdf
except ImportError:  # the `pdf` extra is optional: only the real-PDF tests need it
    pymupdf = None
needs_pdf = pytest.mark.skipif(pymupdf is None, reason="PyMuPDF not installed (pip install -e '.[pdf]')")


def make_pdf(paragraphs, out: Path, *, cols=2, hyphenate=0.4, seed=1, lines_per_col=13, right_column_first=False, width=44) -> Path:
    """A journal-like PDF: ``cols`` columns, running header and page number on every page, hyphenated line breaks."""
    rng = random.Random(seed)
    doc = pymupdf.open()
    xs = [40, 310] if cols == 2 else [60]
    items = []  # (page, column, y, text) in reading order
    page = col = line = 0
    for para in paragraphs:
        lines = textwrap.wrap(para, width=width, break_long_words=False)
        for i, ln in enumerate(lines):
            if i < len(lines) - 1 and rng.random() < hyphenate:
                words = ln.split(" ")
                last = words[-1]
                if len(last) > 7 and last.isalpha():
                    cut = rng.randint(3, len(last) - 3)
                    words[-1] = last[:cut] + "-"
                    lines[i + 1] = last[cut:] + " " + lines[i + 1]
                    ln = " ".join(words)
            if line >= lines_per_col:
                col, line = col + 1, 0
                if col >= len(xs):
                    page, col = page + 1, 0
            items.append((page, col, 80 + line * 11.5 + (5 if line == 0 and items and items[-1][3] is None else 0), ln))
            line += 1
        line += 1  # paragraph gap
    n_pages = items[-1][0] + 1
    order = sorted(items, key=lambda t: (t[0], -t[1] if right_column_first else t[1], t[2]))  # content-stream order
    for n in range(n_pages):  # build and fill one page at a time: PyMuPDF invalidates earlier Page objects
        pg = doc.new_page(width=595, height=842)
        pg.insert_text((40, 40), f"Journal of Fictional Medicine  2026;12:e{n + 1:04d}", fontsize=8)
        pg.insert_text((290, 820), str(n + 1), fontsize=8)
        for p, c, y, ln in order:
            if p == n:
                pg.insert_text((xs[c], y), ln, fontsize=9)
    doc.save(out)
    return out


@needs_pdf
@pytest.mark.parametrize("cols", [1, 2])
def test_pdf_text_matches_the_plain_text_path(tmp_path, cols):
    paras = _paragraphs()
    pdf = make_pdf(paras, tmp_path / "p.pdf", cols=cols)
    got = parse_file(pdf)
    assert not re.findall(r"[a-z]- [a-z]", got.text), "line-end hyphen breaks were left in the text"
    assert "Journal of Fictional Medicine" not in got.text
    assert not any(re.fullmatch(r"\d{1,2}", p) for p in got.text.split("\n\n")), "page numbers were kept"
    assert _keys(got) == _keys(Document.from_text("ref", "\n\n".join(paras)))


@needs_pdf
def test_content_stream_in_the_wrong_column_order_is_repaired(tmp_path):
    paras = _paragraphs()
    pdf = make_pdf(paras, tmp_path / "p.pdf", cols=2, right_column_first=True, hyphenate=0.0)
    got = parse_file(pdf)
    assert _keys(got) == _keys(Document.from_text("ref", "\n\n".join(paras)))
    # reading order: a sentence from the end of the left column precedes the start of the right column of the same page
    assert got.text.find("Drug Zeta") < got.text.find("Drug Omega")


@needs_pdf
def test_scanned_and_corrupt_pdfs_are_one_line_errors(tmp_path):
    doc = pymupdf.open()
    doc.new_page()
    doc.save(tmp_path / "blank.pdf")
    with pytest.raises(IngestError, match="no extractable text"):
        parse_file(tmp_path / "blank.pdf")
    (tmp_path / "bad.pdf").write_bytes(b"not a pdf at all")
    with pytest.raises(IngestError, match="cannot read this PDF"):
        parse_file(tmp_path / "bad.pdf")
