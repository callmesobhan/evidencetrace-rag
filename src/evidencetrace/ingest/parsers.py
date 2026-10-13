"""File -> canonical :class:`Document`.

Supported: plain text / markdown, JATS XML (PubMed Central OA), PDF (optional ``pdf`` extra).
All parsers must emit paragraphs separated by blank lines and section headings on their own line.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from evidencetrace.errors import IngestError
from evidencetrace.ingest.document import Document, Section
from evidencetrace.textnorm import canonical_text

SUPPORTED = {".txt", ".md", ".xml", ".pdf"}


def doc_id_for(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem)


def parse_file(path: str | Path) -> Document:
    path = Path(path)
    suffix = path.suffix.lower()
    doc_id = doc_id_for(path)
    if suffix not in SUPPORTED:
        raise IngestError(f"unsupported file type: {path} (supported: {', '.join(sorted(SUPPORTED))})")
    if suffix == ".pdf":
        return Document.from_text(doc_id, _pdf_to_text(path), source=str(path))
    try:
        raw = path.read_text(encoding="utf-8-sig")  # tolerate a byte-order mark
    except UnicodeDecodeError as exc:
        raise IngestError(f"{path}: not UTF-8 text ({exc.reason}); re-save it as UTF-8") from None
    if suffix == ".xml":
        return parse_jats(doc_id, raw, source=str(path))
    return Document.from_text(doc_id, raw, source=str(path))


# Containers whose <p> children are not running prose (tables are out of scope for now; see roadmap M4).
_SKIP_TAGS = {
    "table-wrap", "table-wrap-group", "fig", "fig-group", "boxed-text", "supplementary-material",
    "ack", "ref-list", "fn-group", "app", "app-group", "glossary", "notes", "bio",
}  # fmt: skip
_DESCEND = {"sec", "list", "list-item", "disp-quote", "statement"}
_DROP_TEXT = {
    "tex-math", "inline-graphic", "graphic", "media", "label",
    "table-wrap", "table", "fig", "boxed-text", "supplementary-material", "disp-formula",
}  # fmt: skip
_SKIP_SECTION_WORDS = (
    "supplement", "supporting", "author contribution", "conflict", "competing", "funding", "financial",
    "acknowledg", "ethic", "data availability", "availability of data", "disclos", "abbreviation",
    "declaration", "consent", "trial registration", "registration", "references",
)  # fmt: skip
_SEC_TYPES = {
    "intro": "introduction", "introduction": "introduction", "background": "introduction",
    "methods": "methods", "materials": "methods", "materials-and-methods": "methods",
    "subjects": "methods", "results": "results", "discussion": "discussion",
    "conclusion": "conclusion", "conclusions": "conclusion",
}  # fmt: skip
_ADMIN_SECTION_STARTS = (
    "acknowledg", "funding", "conflict", "competing", "disclos", "declaration", "data availability",
    "availability of data", "author contribution", "abbreviation", "references", "supporting",
)  # fmt: skip
_SKIP_SEC_TYPES = {"supplementary-material", "coi-statement", "data-availability", "disclaimer"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _jats_text(el: ET.Element) -> str:
    """Flatten an element. Bibliography refs become ``[n]`` so citations stay visible; LaTeX
    preambles and images are dropped, MathML token text is kept (that is where p-values hide)."""
    parts = [el.text or ""]
    for child in el:
        tag = _local(child.tag)
        if tag in _DROP_TEXT:
            parts.append(child.tail or "")
            continue
        inner = _jats_text(child)
        if tag == "xref" and child.get("ref-type") == "bibr":
            inner = f"[{inner.strip()}]"
        parts.append(inner)
        parts.append(child.tail or "")
    return "".join(parts)


def classify_section(sec: ET.Element) -> str | None:
    """Canonical section name for a top-level <sec>, or None to skip it (back matter etc.)."""
    sec_type = (sec.get("sec-type") or "").lower()
    if sec_type in _SKIP_SEC_TYPES:
        return None
    for token in sec_type.replace("|", " ").split():
        if token in _SEC_TYPES:
            return _SEC_TYPES[token]
    title_el = sec.find("title")
    title = " ".join(_jats_text(title_el).split()).lower() if title_el is not None else ""
    title = re.sub(r"^\d+(\.\d+)*\.?\s*", "", title).strip(" :")
    # "Results of the nutritional supplement trial" contains a back-matter word but is the Results section;
    # only titles that BEGIN with a purely administrative word are skipped before the results test
    if "result" in title and not title.startswith(_ADMIN_SECTION_STARTS):
        return "results"
    if any(w in title for w in _SKIP_SECTION_WORDS):
        return None
    if title.startswith("finding"):
        return "results"
    if any(w in title for w in ("introduction", "background", "objective")):
        return "introduction"
    if any(w in title for w in ("method", "material", "study design", "participants", "subjects")):
        return "methods"
    if any(w in title for w in ("discussion", "limitation", "strength")):
        return "discussion"
    if "conclusion" in title:
        return "conclusion"
    return "other"


def _paragraphs(el: ET.Element) -> list[str]:
    out: list[str] = []
    for child in el:
        tag = _local(child.tag)
        if tag in _SKIP_TAGS:
            continue
        if tag == "p":
            text = " ".join(_jats_text(child).split())
            if text:
                out.append(text)
        elif tag in _DESCEND:
            out += _paragraphs(child)
    return out


def jats_blocks(xml: str) -> tuple[str, list[tuple[str, str]]]:
    """(title, [(section_name, paragraph_text), ...]) in reading order."""
    root = ET.fromstring(xml)
    title_el = root.find(".//article-meta//article-title")
    title = " ".join(_jats_text(title_el).split()) if title_el is not None else ""
    blocks: list[tuple[str, str]] = [("front", title)] if title else []
    for ab in root.findall(".//article-meta/abstract"):
        if ab.get("abstract-type") in {"graphical", "toc", "teaser"}:
            continue
        blocks += [("abstract", t) for t in _paragraphs(ab)]
    body = root.find(".//body")
    if body is not None:
        blocks += [("other", t) for t in _paragraphs_direct(body)]
        for sec in body.findall("sec"):
            name = classify_section(sec)
            if name is not None:
                blocks += [(name, t) for t in _paragraphs(sec)]
    return title, blocks


def _paragraphs_direct(body: ET.Element) -> list[str]:
    """Paragraphs that sit directly in <body> rather than inside a <sec>."""
    return [
        " ".join(_jats_text(c).split()) for c in body if _local(c.tag) == "p" and "".join(c.itertext()).strip()
    ]


def parse_jats(doc_id: str, xml: str, *, source: str | None = None) -> Document:
    if "<!ENTITY" in xml:  # same rule as the downloader: no entity declarations (entity-expansion attacks)
        raise IngestError(f"{source or doc_id}: the XML declares entities; refusing to parse")
    try:
        title, blocks = jats_blocks(xml)
    except ET.ParseError as exc:
        raise IngestError(f"{source or doc_id}: not valid XML ({exc})") from None
    except RecursionError:
        raise IngestError(f"{source or doc_id}: XML is nested too deeply to parse") from None
    parts: list[str] = []
    marks: list[tuple[str, int]] = []  # (section name, start offset), merged for consecutive blocks
    pos = 0
    for name, raw in blocks:
        text = canonical_text(raw).strip()
        if not text:
            continue
        if parts:
            pos += 2  # "\n\n" separator
        if not marks or marks[-1][0] != name:
            marks.append((name, pos))
        parts.append(text)
        pos += len(text)
    full = "\n\n".join(parts)
    sections = [
        Section(name=n, start=s, end=marks[i + 1][1] if i + 1 < len(marks) else len(full))
        for i, (n, s) in enumerate(marks)
    ]
    return Document.from_text(
        doc_id, full, title=title or None, source=source, sections=sections or None
    )


@dataclass(frozen=True)
class PdfBlock:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str


@dataclass(frozen=True)
class PdfPage:
    width: float
    height: float
    blocks: list[PdfBlock]


_PAGE_NUMBER = re.compile(r"(?:page\s+)?\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?", re.I)
_MARGIN = 0.08  # share of the page height treated as header / footer zone
_FULL_WIDTH = 0.62  # a block wider than this share of the page spans both columns (title, abstract, wide tables)


def _dehyphenate(text: str) -> str:
    """Join words broken at a line end ("compar-\ntment") and numeric ranges ("0.65-\n0.93"); drop soft hyphens.

    A real compound split at a line end ("long-\nterm") is joined too ("longterm"): without the line break there is no way
    to tell the two cases apart, and an unjoined word fragment breaks retrieval for the whole word.
    """
    text = text.replace("\u00ad", "")
    text = re.sub(r"(?<=\d)-[ \t]*\n[ \t]*(?=\d)", "-", text)
    return re.sub(r"(?<=[A-Za-z])-[ \t]*\n[ \t]*(?=[a-z])", "", text)


def _in_margin(b: PdfBlock, page: PdfPage) -> bool:
    return b.y1 < _MARGIN * page.height or b.y0 > (1 - _MARGIN) * page.height


def _signature(text: str) -> str:
    return re.sub(r"\d+", "#", " ".join(text.split())).lower()


def _reading_order(blocks: list[PdfBlock], width: float) -> list[PdfBlock]:
    """Top-to-bottom, and within each run of narrow blocks the left column before the right one."""
    out: list[PdfBlock] = []
    band: list[PdfBlock] = []

    def flush() -> None:
        left = sorted((b for b in band if (b.x0 + b.x1) / 2 < width / 2), key=lambda b: b.y0)
        right = sorted((b for b in band if (b.x0 + b.x1) / 2 >= width / 2), key=lambda b: b.y0)
        out.extend(left + right)
        band.clear()

    for b in sorted(blocks, key=lambda b: (b.y0, b.x0)):
        if (b.x1 - b.x0) > _FULL_WIDTH * width:
            flush()
            out.append(b)
        else:
            band.append(b)
    flush()
    return out


def layout_pdf(pages: list[PdfPage]) -> str:
    """Reading-order text of a PDF's pages: running headers/footers and page numbers removed, columns un-interleaved."""
    counts: dict[str, int] = {}
    for page in pages:
        for sig in {_signature(b.text) for b in page.blocks if _in_margin(b, page)}:
            counts[sig] = counts.get(sig, 0) + 1
    min_pages = max(2, (len(pages) + 1) // 2)
    repeated = {sig for sig, n in counts.items() if len(pages) >= 3 and n >= min_pages}
    ordered: list[tuple[int, PdfBlock]] = []  # (page number, block) in reading order
    for n, page in enumerate(pages):
        keep = []
        for b in page.blocks:
            t = b.text.strip()
            if _in_margin(b, page) and (_PAGE_NUMBER.fullmatch(t) or _signature(t) in repeated):
                continue
            keep.append(PdfBlock(b.x0, b.y0, b.x1, b.y1, " ".join(_dehyphenate(b.text).split())))
        ordered += [(n, b) for b in _reading_order(keep, page.width) if b.text]
    return "\n\n".join(_join_continuations(ordered))


_SENTENCE_END = re.compile(r"[.?!:;][)\]\"'\u2019\u201d]*$")


_NUMBERED_HEADING = re.compile(r"\d+(?:\.\d+)*\.?\s+[A-Z]")


def _continues(text: str) -> bool:
    """Does this block continue the previous sentence rather than start a new one? A capital letter or a numbered heading
    ("2.1 Methods") starts one; anything else (lowercase, "95% CI ...", "-5.0 to 0.8", a bracket) continues it."""
    first = text[0]
    return not first.isupper() and not (first.isdigit() and _NUMBERED_HEADING.match(text))


def _join_continuations(blocks: list[tuple[int, PdfBlock]]) -> list[str]:
    """Re-join a paragraph that a column or page break cut in the middle of a sentence.

    Three things must hold: the next block continues a sentence (see ``_continues``), the previous one does not end in
    sentence-final punctuation, and the next block starts *higher on the page* than the previous one (or on a later
    page): a wrap from the bottom of one column or page to the top of the next. A heading and its body run downward, so
    they never qualify. A hyphen that falls exactly on the cut ("compar-" / "tment") is removed. Without this a sentence
    split across two columns loses its interval and p-value.
    """
    out: list[str] = []
    prev: tuple[int, PdfBlock] | None = None
    for n, b in blocks:
        wraps = prev is not None and (n != prev[0] or b.y0 <= prev[1].y0)
        if out and wraps and _continues(b.text) and not _SENTENCE_END.search(out[-1]):
            if re.search(r"[A-Za-z]-$", out[-1]) and b.text[0].islower():
                out[-1] = out[-1][:-1] + b.text
            else:
                out[-1] = f"{out[-1]} {b.text}"
        else:
            out.append(b.text)
        prev = (n, b)
    return out


def _pdf_to_text(path: Path) -> str:
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf  # older PyMuPDF
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("PDF support needs the `pdf` extra: pip install 'evidencetrace-rag[pdf]'") from exc
    try:
        with pymupdf.open(path) as pdf:
            pages = [
                PdfPage(page.rect.width, page.rect.height,
                        [PdfBlock(x0, y0, x1, y1, text) for x0, y0, x1, y1, text, _no, kind in page.get_text("blocks")
                         if kind == 0 and text.strip()])
                for page in pdf
            ]
    except Exception as exc:  # PyMuPDF raises several unrelated types for unreadable files
        raise IngestError(f"{path}: cannot read this PDF ({exc})") from None
    text = layout_pdf(pages)
    if len(text.strip()) < 200:
        raise IngestError(f"{path}: the PDF has no extractable text (a scan? OCR is not supported)")
    return text
