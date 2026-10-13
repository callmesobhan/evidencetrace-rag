"""File -> canonical :class:`Document`.

Supported: plain text / markdown, JATS XML (PubMed Central OA), PDF (optional ``pdf`` extra).
All parsers must emit paragraphs separated by blank lines and section headings on their own line.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
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


def _pdf_to_text(path: Path) -> str:
    try:
        import fitz  # pymupdf
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("PDF support needs the `pdf` extra: pip install 'evidencetrace-rag[pdf]'") from exc
    blocks: list[str] = []
    with fitz.open(path) as pdf:
        for page in pdf:
            for _x0, _y0, _x1, _y1, text, _no, kind in page.get_text("blocks"):
                if kind == 0 and text.strip():  # text block
                    blocks.append(" ".join(text.split()))
    return "\n\n".join(blocks)
